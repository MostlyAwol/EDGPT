"""Pure compact overview derived solely from a merged system map."""
from collections import Counter
from copy import deepcopy

import curiosities

SUMMARY_SCHEMA_VERSION = 1


def _text(value):
    return str(value).replace("\n", " ").replace("\r", " ").replace("|", "\\|")


def _groups(values):
    return [{"type": name, "count": count}
            for name, count in sorted(Counter(values).items())]


def build_system_summary(system_map):
    """Return unavailable until the map retains an FSSAllBodiesFound event."""
    if "FSSAllBodiesFound" not in system_map.get("system_events", {}):
        return None
    stars, planets, rings = [], [], {}
    known = 0
    bio_signals, bio_bodies, genera, species = 0, set(), set(), set()
    for node in system_map.get("nodes", {}).values():
        events = node.get("event_data", {})
        scan = events.get("Scan", {})
        # Inferred hierarchy parents, rings, belts and barycentres are not bodies.
        if scan.get("StarType"):
            stars.append(f"{scan['StarType']} star")
            known += 1
        elif scan.get("PlanetClass"):
            planets.append(scan["PlanetClass"])
            known += 1
        for ring in scan.get("Rings", []):
            name = ring.get("Name", "")
            if name and not name.endswith(" Belt"):
                rings[name] = ring.get("RingClass") or "Unknown"
        if node.get("kind") == "Ring" and scan.get("RingClass"):
            rings[node["name"]] = scan["RingClass"]

        # FSS and SAA describe the same signals; never add both observations.
        counts = []
        for event_type in ("FSSBodySignals", "SAASignalsFound"):
            for signal in events.get(event_type, {}).get("Signals", []):
                if signal.get("Type") == "$SAA_SignalType_Biological;":
                    count = signal.get("Count")
                    if isinstance(count, int) and not isinstance(count, bool) and count > 0:
                        counts.append(count)
            for genus in events.get(event_type, {}).get("Genuses", []):
                name = genus.get("Genus_Localised") or genus.get("Genus")
                if name:
                    genera.add(name)
                    bio_bodies.add(node["body_id"])
        if counts:
            bio_signals += max(counts)
            bio_bodies.add(node["body_id"])
        for organic in events.get("ScanOrganic", []):
            bio_bodies.add(node["body_id"])
            genus = organic.get("Genus_Localised") or organic.get("Genus")
            organism = organic.get("Species_Localised") or organic.get("Species")
            if genus:
                genera.add(genus)
            if organism:
                species.add(organism)

    expected = system_map.get("body_count")
    # Conflicting retained counts cannot support a reliable completion line.
    counts = {event[field] for event_type, field in (
        ("FSSDiscoveryScan", "BodyCount"), ("NavBeaconScan", "NumBodies"),
        ("FSSAllBodiesFound", "Count"))
        if isinstance((event := system_map.get("system_events", {}).get(event_type, {})).get(field), int)
        and not isinstance(event[field], bool) and event[field] >= 0}
    if (not isinstance(expected, int) or isinstance(expected, bool)
            or expected < known or len(counts) > 1):
        expected = None
    result = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "system_address": system_map["system_address"],
        "system_name": system_map["system_name"],
        "bodies_known": known,
        "expected_body_count": expected,
        "stars": _groups(stars), "planets": _groups(planets),
        "rings": _groups({"eRingClass_Rocky": "Rocky", "eRingClass_MetalRich": "Metal Rich",
                          "eRingClass_Metalic": "Metallic", "eRingClass_Icy": "Icy"}.get(value, value)
                         for value in rings.values()),
        # Isolate detector code from the source of truth, even for future rules.
        "curiosities": curiosities.find_curiosities(deepcopy(system_map)),
    }
    if bio_bodies:
        result["exobiology"] = {"bodies": len(bio_bodies), "biological_signals": bio_signals,
                                "genera": sorted(genera), "species": sorted(species)}
    result["summary_text"] = render_system_summary(result)
    return result


def render_system_summary(summary):
    lines = [f"# {_text(summary['system_name'])}"]
    if summary["expected_body_count"] is not None:
        lines.extend(["", f"{summary['bodies_known']} of {summary['expected_body_count']} bodies known"])
    for key, title in (("stars", "Stars"), ("planets", "Planets"), ("rings", "Rings")):
        if summary[key]:
            lines.extend(["", f"## {title}", "", "| Type | Count |", "| --- | ---: |"])
            lines.extend(f"| {_text(row['type'])} | {row['count']} |" for row in summary[key])
    if summary.get("exobiology"):
        bio = summary["exobiology"]
        lines.extend(["", "## Exobiology", ""])
        if bio["biological_signals"]:
            lines.append(f"- {bio['biological_signals']} biological signals recorded")
        lines.append(f"- Biological information on {bio['bodies']} bodies")
        for key, label in (("genera", "Known genera"), ("species", "Known species")):
            if bio[key]:
                lines.append(f"- {label}: " + ", ".join(_text(name) for name in bio[key]))
    if summary["curiosities"]:
        lines.extend(["", "## Curiosities", ""])
        lines.extend(f"- {_text(value)}" for value in summary["curiosities"])
    return "\n".join(lines)
