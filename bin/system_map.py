import json
from copy import deepcopy


MAP_SCHEMA_VERSION = 3

BODY_EVENT_TYPES = {
    "Scan",
    "ScanBaryCentre",
    "FSSBodySignals",
    "SAASignalsFound",
    "SAAScanComplete",
    "CodexEntry",
    "ScanOrganic",
}
ACCUMULATING_BODY_EVENT_TYPES = {"CodexEntry", "ScanOrganic"}
SYSTEM_EVENT_TYPES = {
    "FSDJump",
    "DiscoveryScan",
    "FSSDiscoveryScan",
    "FSSAllBodiesFound",
    "NavBeaconScan",
}


def new_system_map(system_address, system_name=""):
    return {
        "schema_version": MAP_SCHEMA_VERSION,
        "system_address": int(system_address),
        "system_name": system_name or f"System {system_address}",
        "first_seen": None,
        "last_updated": None,
        "last_event_id": 0,
        "visits": 0,
        "known_complete": False,
        "current_visit_complete": False,
        "body_count": None,
        "non_body_count": None,
        "fss_progress": None,
        "nodes": {},
        "system_events": {},
        "signals": {},
    }


def _merge_dict(original, update):
    result = deepcopy(original) if isinstance(original, dict) else {}
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_dict(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _event_system_name(event):
    return event.get("SystemName") or event.get("StarSystem") or ""


def _body_id(event):
    value = event.get("BodyID")
    if value is None and event.get("event") == "ScanOrganic":
        value = event.get("Body")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _new_node(body_id):
    return {
        "body_id": int(body_id),
        "name": f"Body {body_id}",
        "kind": "Unknown body",
        "body_type": "Unknown",
        "distance_ls": None,
        "parent_id": None,
        "parent_known": False,
        "parent_chain": [],
        "event_data": {},
    }


def _node(model, body_id):
    key = str(int(body_id))
    if key not in model["nodes"]:
        model["nodes"][key] = _new_node(body_id)
    return model["nodes"][key]


def _parent_chain(parents):
    result = []
    if isinstance(parents, dict):
        parents = [parents]
    if not isinstance(parents, list):
        return result
    for item in parents:
        if not isinstance(item, dict):
            continue
        for kind, value in item.items():
            try:
                result.append({"kind": str(kind), "id": int(value)})
            except (TypeError, ValueError):
                pass
    return result


def _link_id(link):
    if not link or (link["kind"] == "Null" and link["id"] == 0):
        return None
    return link["id"]


def _kind_from_parent_label(label):
    return {
        "Star": "Star",
        "Planet": "Planet",
        "Ring": "Ring",
        "Null": "Barycentre",
    }.get(label, "Unknown body")


def _apply_parent_chain(model, node, parents):
    chain = _parent_chain(parents)
    node["parent_chain"] = chain
    node["parent_id"] = _link_id(chain[0]) if chain else None
    node["parent_known"] = True

    meaningful = [link for link in chain if _link_id(link) is not None]
    for index, link in enumerate(meaningful):
        ancestor = _node(model, link["id"])
        inferred_kind = _kind_from_parent_label(link["kind"])
        if ancestor["kind"] == "Unknown body":
            ancestor["kind"] = inferred_kind
            ancestor["body_type"] = inferred_kind
        next_id = _link_id(meaningful[index + 1]) if index + 1 < len(meaningful) else None
        if not ancestor["parent_known"]:
            ancestor["parent_id"] = next_id


def _classify_node(node, event):
    name = event.get("BodyName") or node["name"]
    node["name"] = name
    if event.get("StarType"):
        node["kind"] = "Star"
        node["body_type"] = f"{event['StarType']} star"
    elif event.get("PlanetClass"):
        has_planet_ancestor = any(
            link.get("kind") == "Planet" for link in node.get("parent_chain", [])
        )
        node["kind"] = "Moon" if has_planet_ancestor else "Planet"
        node["body_type"] = event["PlanetClass"]
    elif str(name).endswith(" Ring"):
        node["kind"] = "Ring"
        node["body_type"] = event.get("RingClass") or "Planetary ring"
    elif "Belt Cluster" in str(name):
        node["kind"] = "Belt cluster"
        node["body_type"] = "Asteroid belt cluster"


def _store_body_event(node, event):
    event_type = event.get("event", "Unknown")
    if event_type in ACCUMULATING_BODY_EVENT_TYPES:
        values = node["event_data"].setdefault(event_type, [])
        encoded = json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        if not any(
            json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":")) == encoded
            for item in values
        ):
            values.append(deepcopy(event))
    else:
        previous = node["event_data"].get(event_type, {})
        node["event_data"][event_type] = _merge_dict(previous, event)


def _signal_key(event):
    parts = (
        event.get("SignalName"),
        event.get("SignalType"),
        event.get("USSType"),
        bool(event.get("IsStation")),
    )
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))


def apply_event(model, event, event_id=0):
    """Merge one indexed journal event into a persistent system map model."""
    if not isinstance(event, dict):
        return model
    event_type = event.get("event")
    timestamp = event.get("timestamp")
    if timestamp:
        if model.get("first_seen") is None or timestamp < model["first_seen"]:
            model["first_seen"] = timestamp
        if model.get("last_updated") is None or timestamp > model["last_updated"]:
            model["last_updated"] = timestamp
    model["last_event_id"] = max(int(model.get("last_event_id", 0)), int(event_id or 0))

    name = _event_system_name(event)
    if name:
        model["system_name"] = name

    if event_type == "FSDJump":
        model["visits"] = int(model.get("visits", 0)) + 1
        model["current_visit_complete"] = False
        arrival_id = _body_id(event)
        if arrival_id is not None:
            arrival = _node(model, arrival_id)
            arrival["name"] = event.get("Body") or arrival["name"]
            arrival["kind"] = event.get("BodyType") or "Star"
            if arrival["kind"] == "Star":
                arrival["body_type"] = "Star"
            arrival["distance_ls"] = 0.0
            arrival["parent_id"] = None
            arrival["parent_known"] = True

    if event_type in SYSTEM_EVENT_TYPES:
        model["system_events"][event_type] = deepcopy(event)

    if event_type == "FSSDiscoveryScan":
        if event.get("BodyCount") is not None:
            model["body_count"] = int(event["BodyCount"])
        if event.get("NonBodyCount") is not None:
            model["non_body_count"] = int(event["NonBodyCount"])
        if event.get("Progress") is not None:
            model["fss_progress"] = event["Progress"]
    elif event_type == "NavBeaconScan" and event.get("NumBodies") is not None:
        model["body_count"] = int(event["NumBodies"])
    elif event_type == "FSSAllBodiesFound":
        model["known_complete"] = True
        model["current_visit_complete"] = True
        model["fss_progress"] = 1.0
        if event.get("Count") is not None:
            model["body_count"] = max(int(event["Count"]), int(model.get("body_count") or 0))
    elif event_type == "FSSSignalDiscovered":
        model["signals"][_signal_key(event)] = deepcopy(event)

    if event_type in BODY_EVENT_TYPES:
        body_id = _body_id(event)
        if body_id is not None:
            node = _node(model, body_id)
            if event.get("BodyName"):
                node["name"] = event["BodyName"]
            if event_type == "Scan":
                _apply_parent_chain(model, node, event.get("Parents"))
                if event.get("DistanceFromArrivalLS") is not None:
                    node["distance_ls"] = event["DistanceFromArrivalLS"]
                _classify_node(node, event)
            elif event_type == "ScanBaryCentre":
                node["kind"] = "Barycentre"
                node["body_type"] = "Barycentre"
                if node["name"].startswith("Body "):
                    node["name"] = f"Barycentre {body_id}"
            elif str(node.get("name", "")).endswith(" Ring"):
                node["kind"] = "Ring"
                node["body_type"] = "Planetary ring"
            _store_body_event(node, event)
    return model


def _attach_named_rings(model):
    ring_parents = {}
    for candidate in model["nodes"].values():
        scan = candidate.get("event_data", {}).get("Scan", {})
        for ring in scan.get("Rings", []) if isinstance(scan, dict) else []:
            if isinstance(ring, dict) and ring.get("Name"):
                ring_parents[ring["Name"]] = candidate["body_id"]
    for node in model["nodes"].values():
        parent_id = ring_parents.get(node.get("name"))
        if parent_id is not None and not node.get("parent_known"):
            node["parent_id"] = parent_id
            node["kind"] = "Ring"
            node["body_type"] = "Planetary ring"


def _hierarchy(model):
    _attach_named_rings(model)
    nodes = model["nodes"]
    children = {key: [] for key in nodes}
    roots = []
    for key, node in nodes.items():
        parent_key = str(node.get("parent_id")) if node.get("parent_id") is not None else None
        if parent_key in nodes and parent_key != key:
            children[parent_key].append(key)
        else:
            roots.append(key)

    distance_cache = {}

    def effective_distance(key, visiting=None):
        if key in distance_cache:
            return distance_cache[key]
        visiting = set(visiting or ())
        if key in visiting:
            return float("inf")
        visiting.add(key)
        node = nodes[key]
        values = []
        if isinstance(node.get("distance_ls"), (int, float)):
            values.append(float(node["distance_ls"]))
        values.extend(effective_distance(child, visiting) for child in children[key])
        value = min(values) if values else float("inf")
        distance_cache[key] = value
        return value

    def sort_key(key):
        node = nodes[key]
        return (effective_distance(key), int(node.get("body_id", 0)), str(node.get("name", "")))

    roots.sort(key=sort_key)
    for values in children.values():
        values.sort(key=sort_key)
    return roots, children


def _format_distance(value):
    if not isinstance(value, (int, float)):
        return "distance unknown"
    if abs(value) < 0.01:
        return "0 ls"
    if abs(value) < 1000:
        return f"{value:.2f} ls"
    return f"{value:,.2f} ls"


def _node_label(node):
    kind = node.get("kind") or "Body"
    body_type = node.get("body_type") or "Unknown"
    type_text = kind if body_type == kind else f"{kind}: {body_type}"
    return f"{node.get('name')} [{type_text}; {_format_distance(node.get('distance_ls'))}]"


def _scan_status(model):
    discovered = sum(
        1 for node in model["nodes"].values() if "Scan" in node.get("event_data", {})
    )
    expected = model.get("body_count")
    if model.get("current_visit_complete"):
        state = "current visit complete"
    elif model.get("known_complete"):
        state = "saved map complete; current revisit not rescanned"
    elif model.get("fss_progress") is not None:
        state = f"in progress ({float(model['fss_progress']) * 100:.0f}%)"
    else:
        state = "in progress"
    count = f"{discovered}/{expected} bodies represented" if expected is not None else f"{discovered} bodies represented"
    return f"{state}; {count}"


def render_simple_map(model):
    if not model:
        return "No saved system map is available."
    roots, children = _hierarchy(model)
    lines = [
        f"System: {model['system_name']} [{model['system_address']}]",
        f"Scan status: {_scan_status(model)}",
    ]
    nodes = model["nodes"]
    visited = set()

    def add_node(key, prefix, is_last):
        connector = "└─ " if is_last else "├─ "
        lines.append(prefix + connector + _node_label(nodes[key]))
        if key in visited:
            lines.append(prefix + ("   " if is_last else "│  ") + "└─ [cycle omitted]")
            return
        visited.add(key)
        branch = prefix + ("   " if is_last else "│  ")
        for index, child in enumerate(children[key]):
            add_node(child, branch, index == len(children[key]) - 1)

    for index, key in enumerate(roots):
        add_node(key, "", index == len(roots) - 1)
    if not roots:
        lines.append("└─ No bodies have been recorded yet")
    return "\n".join(lines)


def render_full_map(model):
    if not model:
        return "No saved system map is available."
    roots, children = _hierarchy(model)
    lines = [
        f"System: {model['system_name']}",
        f"SystemAddress: {model['system_address']}",
        f"Scan status: {_scan_status(model)}",
        f"Visits indexed: {model.get('visits', 0)}",
        f"First seen: {model.get('first_seen') or 'unknown'}",
        f"Last updated: {model.get('last_updated') or 'unknown'}",
        "System event data:",
    ]
    for event_type in sorted(model.get("system_events", {})):
        value = json.dumps(model["system_events"][event_type], ensure_ascii=False, sort_keys=True)
        lines.append(f"  {event_type}: {value}")

    lines.append("Bodies:")
    nodes = model["nodes"]
    visited = set()

    def add_node(key, prefix, is_last):
        connector = "└─ " if is_last else "├─ "
        lines.append(prefix + connector + _node_label(nodes[key]))
        detail_prefix = prefix + ("   " if is_last else "│  ")
        if key in visited:
            lines.append(detail_prefix + "[cycle omitted]")
            return
        visited.add(key)
        for event_type in sorted(nodes[key].get("event_data", {})):
            value = json.dumps(nodes[key]["event_data"][event_type], ensure_ascii=False, sort_keys=True)
            lines.append(detail_prefix + f"{event_type}: {value}")
        for index, child in enumerate(children[key]):
            add_node(child, detail_prefix, index == len(children[key]) - 1)

    for index, key in enumerate(roots):
        add_node(key, "", index == len(roots) - 1)
    if not roots:
        lines.append("└─ No bodies have been recorded yet")

    signals = sorted(
        model.get("signals", {}).values(),
        key=lambda item: (str(item.get("SignalName", "")), str(item.get("timestamp", ""))),
    )
    lines.append("System signals:")
    if signals:
        for index, signal in enumerate(signals):
            connector = "└─ " if index == len(signals) - 1 else "├─ "
            lines.append(connector + json.dumps(signal, ensure_ascii=False, sort_keys=True))
    else:
        lines.append("└─ None recorded")
    return "\n".join(lines)


def map_metadata(model):
    return {
        "system_name": model["system_name"],
        "system_address": model["system_address"],
        "first_seen": model.get("first_seen"),
        "last_updated": model.get("last_updated"),
        "visits": model.get("visits", 0),
        "known_complete": bool(model.get("known_complete")),
        "current_visit_complete": bool(model.get("current_visit_complete")),
        "body_count": model.get("body_count"),
        "bodies_recorded": sum(
            1 for node in model["nodes"].values() if "Scan" in node.get("event_data", {})
        ),
    }
