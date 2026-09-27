from diagnostics import health, capabilities, version, start_indexer
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from history_store import history_summary, latest_event, recent_events, search_events, sync_journals
from status_flags import decode_status_flags
from system_map_store import get_current_system_map, get_system_map, list_system_maps

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_ELITE_DIR = Path.home() / "Saved Games" / "Frontier Developments" / "Elite Dangerous"
ELITE_DIR = Path(os.environ.get("ELITE_JOURNAL_DIR", str(DEFAULT_ELITE_DIR))).expanduser()
PORT = int(os.environ.get("EDGPT_STATE_PORT", "8080"))

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def read_json_file(filename):
    path = ELITE_DIR / filename
    if not path.exists() or not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            value = json.load(f)
            return decode_status_flags(value) if filename.lower() == "status.json" else value
    except Exception:
        return None


def all_live_json_files():
    result = {}
    try:
        for path in sorted(ELITE_DIR.glob("*.json")):
            value = read_json_file(path.name)
            if value is not None:
                result[path.name] = value
    except Exception:
        pass
    return result


def parse_state_options(query):
    """Parse strict, independent /state output-selection options."""

    def optional_bool(name):
        if name not in query:
            return False
        values = query[name]
        if len(values) != 1:
            raise ValueError(f"{name} must be specified once.")
        value = values[0].strip().lower()
        if value in TRUE_VALUES:
            return True
        if value in FALSE_VALUES:
            return False
        raise ValueError(f"{name} must be true or false.")

    recent_event_count = None
    if "recent_events" in query:
        values = query["recent_events"]
        if len(values) != 1:
            raise ValueError("recent_events must be specified once.")
        try:
            recent_event_count = int(values[0].strip())
        except (TypeError, ValueError):
            raise ValueError("recent_events must be an integer from 0 to 5000.") from None
        if not 0 <= recent_event_count <= 5000:
            raise ValueError("recent_events must be an integer from 0 to 5000.")

    return {
        "include_history_summary": optional_bool("history_summary"),
        "recent_event_count": recent_event_count,
        "include_loadout": optional_bool("loadout"),
        "include_live_files": optional_bool("live_files"),
    }


def build_state(
    include_history_summary=False,
    recent_event_count=None,
    include_loadout=False,
    include_live_files=False,
):
    sync_journals()
    if include_live_files:
        live_files = all_live_json_files()
        status_file = live_files.get("Status.json")
        navroute_file = live_files.get("NavRoute.json")
    else:
        live_files = None
        status_file = read_json_file("Status.json")
        navroute_file = read_json_file("NavRoute.json")

    requested_event_count = int(recent_event_count or 0)
    replay_events = recent_events(max(250, requested_event_count))

    loadout = latest_event("Loadout")
    location_event = latest_event("Location") or latest_event("FSDJump") or latest_event("CarrierJump")
    load_game = latest_event("LoadGame")
    docked_event = latest_event("Docked")
    undocked_event = latest_event("Undocked")

    state = {
        "generated_at": time.time(),
        "system": None,
        "system_address": None,
        "star_position": None,
        "body": None,
        "body_type": None,
        "station": None,
        "docked": False,
        "ship": None,
        "ship_name": None,
        "ship_ident": None,
        "jump_range": None,
        "fuel": {"main": None, "reservoir": None, "capacity": None},
        "location": {"latitude": None, "longitude": None, "altitude": None, "heading": None},
        "status": status_file,
        "navroute": navroute_file,
        "system_map": get_current_system_map(include_full=False),
    }
    if include_history_summary:
        state["history_summary"] = history_summary()
    if recent_event_count is not None:
        state["recent_events"] = (
            replay_events[-requested_event_count:] if requested_event_count else []
        )
    if include_loadout:
        state["loadout"] = loadout
    if include_live_files:
        state["live_files"] = live_files

    replay = []
    for candidate in (location_event, load_game, loadout):
        if candidate:
            replay.append(candidate)
    replay.extend(replay_events)

    for e in replay:
        event = e.get("event")
        if event in ("Location", "FSDJump", "CarrierJump"):
            state["system"] = e.get("StarSystem", state["system"])
            state["system_address"] = e.get("SystemAddress", state["system_address"])
            state["star_position"] = e.get("StarPos", state["star_position"])
            state["body"] = e.get("Body", state["body"])
            state["body_type"] = e.get("BodyType", state["body_type"])
            if event == "Location" and e.get("Docked") is not None:
                state["docked"] = bool(e.get("Docked"))
                if state["docked"]:
                    state["station"] = e.get("StationName")

        if event == "Docked":
            state["station"] = e.get("StationName")
            state["docked"] = True
        elif event == "Undocked":
            state["station"] = None
            state["docked"] = False

        if event == "LoadGame":
            state["ship"] = e.get("Ship")
            state["ship_name"] = e.get("ShipName")
            state["ship_ident"] = e.get("ShipIdent")

        if event == "Loadout":
            state["ship"] = e.get("Ship", state["ship"])
            state["ship_name"] = e.get("ShipName", state["ship_name"])
            state["ship_ident"] = e.get("ShipIdent", state["ship_ident"])
            state["jump_range"] = e.get("MaxJumpRange", state["jump_range"])
            capacity = e.get("FuelCapacity")
            if isinstance(capacity, dict):
                state["fuel"]["capacity"] = capacity.get("Main")

        if event == "FSDJump":
            if e.get("FuelLevel") is not None:
                state["fuel"]["main"] = e.get("FuelLevel")
        elif event == "FuelScoop":
            if e.get("Total") is not None:
                state["fuel"]["main"] = e.get("Total")

        if event in ("Touchdown", "Liftoff"):
            state["body"] = e.get("Body", state["body"])
            state["location"]["latitude"] = e.get("Latitude")
            state["location"]["longitude"] = e.get("Longitude")

    status = state["status"]
    if isinstance(status, dict):
        state["location"]["latitude"] = status.get("Latitude", state["location"]["latitude"])
        state["location"]["longitude"] = status.get("Longitude", state["location"]["longitude"])
        state["location"]["altitude"] = status.get("Altitude")
        state["location"]["heading"] = status.get("Heading")
        fuel = status.get("Fuel")
        if isinstance(fuel, dict):
            state["fuel"]["main"] = fuel.get("FuelMain", state["fuel"]["main"])
            state["fuel"]["reservoir"] = fuel.get("FuelReservoir")

    if docked_event and undocked_event:
        if str(docked_event.get("timestamp", "")) > str(undocked_event.get("timestamp", "")):
            state["docked"] = True
            state["station"] = docked_event.get("StationName")
    elif docked_event and not undocked_event:
        state["docked"] = True
        state["station"] = docked_event.get("StationName")

    return state


def send_json(handler, value, code=200):
    body = json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query, keep_blank_values=True)

        if path == "/health":
            return send_json(self, health())
        if path == "/capabilities":
            return send_json(self, capabilities())
        if path == "/version":
            return send_json(self, version())

        if path == "/state":
            try:
                options = parse_state_options(qs)
            except ValueError as exc:
                return send_json(self, {"error": str(exc)}, 400)
            return send_json(self, build_state(**options))

        if path == "/history/summary":
            return send_json(self, history_summary())

        if path == "/history/recent":
            try:
                count = int(qs.get("count", ["250"])[0])
            except Exception:
                count = 250
            return send_json(self, recent_events(count))

        if path == "/history/search":
            query = qs.get("q", [""])[0]
            event = qs.get("event", [""])[0]
            start = qs.get("start", [""])[0]
            end = qs.get("end", [""])[0]
            try:
                limit = int(qs.get("limit", ["200"])[0])
            except Exception:
                limit = 200
            return send_json(self, search_events(query, event, start, end, limit))

        if path == "/system-map/simple":
            return send_json(self, get_current_system_map(include_full=False) or {})

        if path == "/system-map/full":
            return send_json(self, get_current_system_map(include_full=True) or {})

        if path == "/system-maps":
            query = qs.get("q", [""])[0]
            try:
                limit = int(qs.get("limit", ["100"])[0])
            except Exception:
                limit = 100
            return send_json(self, list_system_maps(query, limit))

        if path == "/system-maps/get":
            identifier = qs.get("system", [""])[0]
            include_full = qs.get("detail", ["simple"])[0].lower() == "full"
            result = get_system_map(identifier, include_full)
            if result is None:
                return send_json(self, {"error": "Saved system map not found."}, 404)
            return send_json(self, result)

        if path == "/":
            html = """<!DOCTYPE html><html><head><meta charset='UTF-8'><title>EDGPT Full Context</title>
<style>body{background:#111;color:#eee;font-family:Consolas,monospace;margin:30px}h1{color:#ff9500}pre{background:#191919;padding:20px;border-radius:8px;white-space:pre-wrap}</style></head>
<body><h1>EDGPT Full Context</h1><p>Current state + complete indexed journal history.</p><pre id='data'>Loading...</pre>
<script>async function update(){try{const r=await fetch('/state?time='+Date.now());const d=await r.json();document.getElementById('data').textContent=JSON.stringify(d,null,2)}catch(e){document.getElementById('data').textContent='ERROR: '+e}}update();setInterval(update,5000)</script></body></html>"""
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def main():
    print("\n======================================")
    print(" EDGPT FULL CONTEXT SERVER")
    print("======================================\n")
    print("Elite folder:")
    print(ELITE_DIR)
    start_indexer()
    print(f"\nDashboard: http://localhost:{PORT}")
    print(f"Raw API:   http://localhost:{PORT}/state")
    print(f"History:   http://localhost:{PORT}/history/summary\n")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
