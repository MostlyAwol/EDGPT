from diagnostics import health, capabilities, version, start_indexer
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from history_store import history_summary, recent_events, search_events
from current_state import build_state
from system_map_store import get_current_system_map, get_system_map, list_system_maps
from session_store import get_current_session_summary, get_game_session, list_game_sessions

if __name__ == "__main__" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if __name__ == "__main__" and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_ELITE_DIR = Path.home() / "Saved Games" / "Frontier Developments" / "Elite Dangerous"
ELITE_DIR = Path(os.environ.get("ELITE_JOURNAL_DIR", str(DEFAULT_ELITE_DIR))).expanduser()
PORT = int(os.environ.get("EDGPT_STATE_PORT", "8080"))

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


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

        if path in ("/sessions", "/sessions/current", "/sessions/get"):
            try:
                allowed = {"/sessions": {"limit", "before", "start", "end"},
                           "/sessions/current": set(), "/sessions/get": {"id"}}[path]
                if any(key not in allowed or len(values) != 1 for key, values in qs.items()):
                    raise ValueError("Unknown or repeated session query parameter.")
                if path == "/sessions/current":
                    result = get_current_session_summary()
                elif path == "/sessions/get":
                    result = get_game_session(qs.get("id", [""])[0])
                    if not result:
                        return send_json(self, {"error": "Session not found."}, 404)
                else:
                    result = list_game_sessions(qs.get("limit", ["20"])[0], qs.get("before", ["0"])[0],
                                                qs.get("start", [""])[0], qs.get("end", [""])[0])
            except ValueError as exc:
                return send_json(self, {"error": str(exc)}, 400)
            return send_json(self, result)

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
