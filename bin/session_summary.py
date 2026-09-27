"""Bounded session reduction. Journal field provenance: Frontier manual v32.

Counts describe observed events, not unique bodies, kills or inventory balances.
"""
import copy
import hashlib
import json
import math
from datetime import datetime, timezone

SESSION_SCHEMA_VERSION = 1
DETAIL_LIMIT = 20

INCOME = {"MarketSell": "TotalSale", "MissionCompleted": "Reward",
          "RedeemVoucher": "Amount", "ModuleSell": "SellPrice",
          "ShipyardSell": "ShipPrice", "SellDrones": "TotalSale",
          "SearchAndRescue": "Reward", "SellMicroResources": "Price"}
EXPENSE = {"MarketBuy": "TotalCost", "BuyDrones": "TotalCost",
           "RefuelAll": "Cost", "RefuelPartial": "Cost", "Repair": "Cost",
           "RepairAll": "Cost", "RestockVehicle": "Cost", "Resurrect": "Cost",
           "ShipyardBuy": "ShipPrice", "ModuleBuy": "BuyPrice",
           "PayFines": "Amount", "PayBounties": "Amount", "PayLegacyFines": "Amount"}


def utc_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except ValueError:
        return None


def timestamp(value):
    parsed = utc_time(value)
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z") if parsed else None


def warn(model, message):
    if message not in model["warnings"]:
        model["warnings"].append(message)


def number(model, value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
        return value
    warn(model, "Some supported activity fields are missing or invalid; totals are partial.")
    return None


def new_session(event, source):
    identity = json.dumps([*source, event.get("timestamp"), event.get("event")])
    model = {
        "schema_version": SESSION_SCHEMA_VERSION,
        "session_id": hashlib.sha256(identity.encode()).hexdigest()[:32],
        "start": timestamp(event.get("timestamp")), "end": None,
        "last_event_at": None, "status": "open", "end_reason": None,
        "commander": None, "profile_id": None, "game_mode": None,
        "source_event_range": {"first_id": None, "last_id": None},
        "event_count": 0, "activities": {},
        "warnings": ["Credits, cargo and materials cover supported explicit transactions only; they are not complete balances."],
        "_ship": None, "_system": None,
    }
    if event.get("event") != "LoadGame":
        warn(model, "LoadGame is missing; session start and identity may be incomplete.")
    return model


def activity(model, name, event_id, **totals):
    group = model["activities"].setdefault(name, {
        "count": 0, "totals": {}, "source_event_range": {"first_id": event_id, "last_id": event_id},
        "examples": [], "examples_omitted": 0,
    })
    group["count"] += 1
    bounds = group["source_event_range"]
    bounds["first_id"] = min(bounds["first_id"], event_id)
    bounds["last_id"] = max(bounds["last_id"], event_id)
    for key, value in totals.items():
        if value is not None:
            group["totals"][key] = group["totals"].get(key, 0) + value
    return group


def example(group, event, event_id, fields):
    if len(group["examples"]) >= DETAIL_LIMIT:
        group["examples_omitted"] += 1
        return
    item = {"event_id": event_id, "event": event.get("event"), "timestamp": event.get("timestamp")}
    for field in fields:
        value = event.get(field)
        if isinstance(value, (str, int, float, bool)):
            item[field] = value[:256] if isinstance(value, str) else value
    group["examples"].append(item)


def apply_event(model, event, event_id):
    model["event_count"] += 1
    bounds = model["source_event_range"]
    bounds["first_id"] = min(bounds["first_id"] or event_id, event_id)
    bounds["last_id"] = max(bounds["last_id"] or event_id, event_id)
    when = timestamp(event.get("timestamp"))
    if when is None:
        warn(model, "Some source timestamps are missing or invalid; duration may be unavailable.")
    elif model["last_event_at"] and utc_time(when) < utc_time(model["last_event_at"]):
        warn(model, "Source timestamps run backwards; duration may be unreliable.")
    model["last_event_at"] = when
    kind = event.get("event")
    if not isinstance(kind, str):
        warn(model, "Some event types are missing or invalid.")
        return
    if kind == "LoadGame":
        model.update(commander=event.get("Commander") or model["commander"],
                     profile_id=event.get("FID") or model["profile_id"], game_mode=event.get("GameMode"))
    if kind == "Commander":
        model["commander"] = event.get("Name") or model["commander"]
        model["profile_id"] = event.get("FID") or model["profile_id"]

    if kind in ("Location", "FSDJump", "CarrierJump"):
        system = event.get("StarSystem")
        if system and system != model["_system"]:
            example(activity(model, "system_visits", event_id), event, event_id, ("StarSystem", "SystemAddress"))
            model["_system"] = system
    if kind == "FSDJump":
        distance = number(model, event.get("JumpDist"))
        activity(model, "jumps", event_id, distance_ly=distance)
    if kind == "CarrierJump":
        activity(model, "carrier_jumps", event_id)
    if kind == "Docked" or (kind == "Location" and event.get("Docked") is True):
        example(activity(model, "docking_locations", event_id), event, event_id, ("StarSystem", "StationName", "StationType"))

    if kind in ("LoadGame", "Loadout", "ShipyardSwap", "ShipyardNew"):
        ship = [event.get("ShipID"), event.get("Ship") or event.get("ShipType")]
        if any(value is not None for value in ship):
            if model["_ship"] is not None and ship != model["_ship"]:
                example(activity(model, "ship_changes", event_id), event, event_id, ("ShipID", "Ship", "ShipType", "ShipName"))
            model["_ship"] = ship
    highlights = {"Died": "deaths", "Resurrect": "rebuys", "Bounty": "bounty_awards",
                  "PVPKill": "pvp_kills", "FactionKillBond": "combat_bonds",
                  "HullDamage": "hull_damage", "UnderAttack": "attacks"}
    if kind in highlights:
        extra = {"cost": number(model, event.get("Cost"))} if kind == "Resurrect" else {}
        example(activity(model, highlights[kind], event_id, **extra), event, event_id,
                ("KillerName", "KillerShip", "Target", "Victim", "Health", "PlayerPilot", "Option", "Cost"))

    exploration = {"Scan": "scans", "SAAScanComplete": "mapped_bodies", "CodexEntry": "codex_entries"}
    if kind in exploration:
        example(activity(model, exploration[kind], event_id), event, event_id,
                ("BodyName", "BodyID", "PlanetClass", "StarType", "Name_Localised", "IsNewEntry"))
    if kind == "ScanOrganic":
        group = "organic_discoveries" if str(event.get("ScanType", "")).lower() == "analyse" else "organic_samples"
        example(activity(model, group, event_id), event, event_id, ("ScanType", "Species", "Genus", "Body", "SystemAddress"))
    if kind == "Scan" and (event.get("PlanetClass") in ("Earthlike body", "Water world", "Ammonia world") or event.get("TerraformState") == "Terraformable"):
        example(activity(model, "notable_finds", event_id), event, event_id,
                ("BodyName", "PlanetClass", "TerraformState", "WasDiscovered", "WasMapped"))
    if kind in ("MissionAccepted", "MissionCompleted", "MissionFailed", "MissionAbandoned"):
        example(activity(model, "missions_" + kind[7:].lower(), event_id), event, event_id,
                ("MissionID", "Name", "LocalisedName", "DestinationSystem", "Reward"))

    earned = number(model, event.get(INCOME[kind])) if kind in INCOME else None
    spent = number(model, event.get(EXPENSE[kind])) if kind in EXPENSE else None
    if kind in ("SellExplorationData", "MultiSellExplorationData"):
        if "TotalEarnings" in event:
            earned = number(model, event["TotalEarnings"])
        else:
            base, bonus = number(model, event.get("BaseValue")), number(model, event.get("Bonus"))
            earned = base + bonus if base is not None and bonus is not None else None
    if kind == "SellOrganicData":
        earned = 0
        records = event.get("BioData")
        if not isinstance(records, list):
            number(model, None)
        else:
            for item in records:
                if isinstance(item, dict):
                    earned += (number(model, item.get("Value")) or 0) + (number(model, item.get("Bonus")) or 0)
    if kind in ("ShipyardBuy", "ModuleBuy") and "SellPrice" in event:
        earned = number(model, event["SellPrice"])
    if earned is not None or spent is not None:
        activity(model, "credits", event_id, earned=earned, spent=spent, net=(earned or 0) - (spent or 0))

    cargo = {"MarketBuy": 1, "MarketSell": -1, "CollectCargo": 1, "EjectCargo": -1, "MiningRefined": 1}
    if kind in cargo:
        count = 1 if kind in ("CollectCargo", "MiningRefined") else number(model, event.get("Count"))
        if count is not None:
            group = activity(model, "cargo_changes", event_id, **{"added" if cargo[kind] > 0 else "removed": count})
            example(group, event, event_id, ("Type", "Count"))
    if kind in ("MaterialCollected", "MaterialDiscarded"):
        count = number(model, event.get("Count"))
        group = activity(model, "material_changes", event_id, **{"added" if kind == "MaterialCollected" else "removed": count})
        example(group, event, event_id, ("Name", "Category", "Count"))
    if kind == "MaterialTrade":
        for field, total in (("Paid", "removed"), ("Received", "added")):
            item = event.get(field)
            if not isinstance(item, dict):
                number(model, None)
                continue
            group = activity(model, "material_changes", event_id, **{total: number(model, item.get("Quantity"))})
            example(group, {**item, "event": kind, "timestamp": event.get("timestamp")}, event_id, ("Material", "Category", "Quantity"))
    if kind in ("Synthesis", "EngineerCraft"):
        ingredients = event.get("Materials") if kind == "Synthesis" else event.get("Ingredients")
        if not isinstance(ingredients, list):
            number(model, None)
        else:
            for item in ingredients:
                if isinstance(item, dict):
                    group = activity(model, "material_changes", event_id, removed=number(model, item.get("Count")))
                    example(group, {**item, "event": kind, "timestamp": event.get("timestamp")}, event_id, ("Name", "Count"))


def close_session(model, reason):
    model["status"] = "completed" if reason == "shutdown" else "incomplete"
    model["end_reason"] = reason
    model["end"] = model["last_event_at"]
    if reason != "shutdown":
        warn(model, "Shutdown is missing; end is the last observed event, not a confirmed logout.")


def render_session(model):
    result = {key: copy.deepcopy(value) for key, value in model.items() if not key.startswith("_")}
    start, end = utc_time(model["start"]), utc_time(model["end"] or model["last_event_at"])
    result["duration_seconds"] = max(0, (end - start).total_seconds()) if start and end else None
    result["duration_basis"] = "observed_events"
    if model["status"] == "open":
        result["warnings"].append("No Shutdown observed; this session may be running or may have crashed.")
    counts = [f"{group['count']} {name.replace('_', ' ')}" for name, group in result["activities"].items()]
    jumps = result["activities"].get("jumps", {}).get("totals", {})
    if "distance_ly" in jumps:
        counts.append(f"{jumps['distance_ly']:g} ly travelled")
    credits = result["activities"].get("credits", {}).get("totals", {})
    if credits:
        counts.append(f"{credits.get('earned', 0):g} credits earned, {credits.get('spent', 0):g} spent (observed)")
    result["summary_text"] = f"{model['status'].capitalize()} session from {model['start'] or 'unknown time'}: " + (", ".join(counts) if counts else "no supported activities observed") + "."
    return result
