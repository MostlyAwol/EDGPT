"""Transport-neutral current-state ingestion, reduction and response selection."""
import json
import time
from pathlib import Path

import history_store as history
from status_flags import decode_status_flags
from system_map_store import get_current_system_map

STATE_EVENT_TYPES = (
    "Location", "FSDJump", "CarrierJump", "Docked", "Undocked",
    "LoadGame", "Loadout", "FuelScoop", "Touchdown", "Liftoff",
)


def read_json_file(filename, journal_dir=None):
    path = Path(journal_dir or history.ELITE_DIR) / filename
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return decode_status_flags(value) if filename.lower() == "status.json" else value
    except (OSError, ValueError):
        return None


def list_live_json(journal_dir=None):
    try:
        return sorted(p.name for p in Path(journal_dir or history.ELITE_DIR).glob("*.json") if p.is_file())
    except OSError:
        return []


def all_live_json_files(journal_dir=None):
    return {name: value for name in list_live_json(journal_dir)
            if (value := read_json_file(name, journal_dir)) is not None}


def reduce_state(replay, status_file=None, navroute_file=None):
    """Reduce ordered source events; live coordinates/fuel take precedence. No I/O."""
    state = {
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
    }
    for e in replay:
        event = e.get("event")
        if event in ("Location", "FSDJump", "CarrierJump"):
            state["system"] = e.get("StarSystem", state["system"])
            state["system_address"] = e.get("SystemAddress", state["system_address"])
            state["star_position"] = e.get("StarPos", state["star_position"])
            state["body"] = e.get("Body", state["body"])
            state["body_type"] = e.get("BodyType", state["body_type"])
            if event in ("FSDJump", "CarrierJump"):
                state["docked"] = False
                state["station"] = None
            if e.get("Docked") is not None:
                state["docked"] = bool(e.get("Docked"))
                state["station"] = e.get("StationName") if state["docked"] else None

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

    return state


def build_state(include_history_summary=False, recent_event_count=None,
                include_loadout=False, include_live_files=False, *,
                journal_dir=None, mcp_profile=False):
    """Synchronize once, gather inputs, reduce, then select transport context."""
    history.sync_journals()
    live_files = all_live_json_files(journal_dir) if include_live_files else None
    status = (live_files.get("Status.json") if live_files is not None
              else read_json_file("Status.json", journal_dir))
    route = (live_files.get("NavRoute.json") if live_files is not None
             else read_json_file("NavRoute.json", journal_dir))
    events = history.latest_state_events(STATE_EVENT_TYPES, sync=False)
    state = reduce_state(events, status, route)
    state["generated_at"] = time.time()
    state["system_map"] = get_current_system_map(include_full=False, sync_history=False)
    if include_history_summary:
        state["history_summary"] = history.history_summary(sync=False)
    if recent_event_count is not None:
        state["recent_events"] = (history.recent_events(recent_event_count, sync=False)
                                  if recent_event_count else [])
    if include_loadout:
        state["loadout"] = next((e for e in reversed(events) if e.get("event") == "Loadout"), None)
    if include_live_files:
        state["live_files"] = live_files
    if mcp_profile:
        state["location_event"] = next((e for e in reversed(events)
                                        if e.get("event") in ("Location", "FSDJump", "CarrierJump")), None)
        state["live_json_files"] = list_live_json(journal_dir)
    return state
