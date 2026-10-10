"""Ordered, independent curiosity detectors for merged system maps.

Rules must return formatted strings in deterministic order and never mutate
their input. Distances are orbital estimates, never current positions.
"""

from collections import defaultdict
import math


# Edit this single value to tune all proximity checks (strictly less than).
CLOSE_DISTANCE_KM = 2000.0
METRES_PER_KM = 1000.0
BINARY_REL_TOL = 1e-5


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return float(value) if math.isfinite(value) else None
    except (OverflowError, ValueError):
        return None


def _id(value):
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
        return result if str(result) == str(value) and result >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def _nodes(model):
    return {body_id: node for key, node in model.get("nodes", {}).items()
            if isinstance(node, dict)
            and (body_id := _id(node.get("body_id", key))) is not None}


def _scan(node):
    events = node.get("event_data", {})
    value = events.get("Scan", {}) if isinstance(events, dict) else {}
    return value if isinstance(value, dict) else {}


def _parent(node):
    chain = node.get("parent_chain") or []
    if chain:
        link = chain[0]
        if not isinstance(link, dict):
            return None, None
        kind, body_id = link.get("kind"), _id(link.get("id"))
        if kind == "Null" and body_id == 0:
            return None, None  # Journal root sentinel, not a shared barycentre.
        explicit = _id(node.get("parent_id"))
        if explicit is not None and explicit != body_id:
            return None, None
        return kind, body_id
    return None, _id(node.get("parent_id"))


def _orbit(scan):
    a, e = _number(scan.get("SemiMajorAxis")), _number(scan.get("Eccentricity"))
    if a is None or a <= 0 or e is None or not 0 <= e < 1:
        return None
    low, high = a * (1 - e), a * (1 + e)
    return (low, high) if math.isfinite(high) else None


def _radius(scan):
    value = _number(scan.get("Radius"))
    return value if value is not None and value > 0 else None


def _name(node):
    return str(_scan(node).get("BodyName") or node.get("name") or f"Body {node.get('body_id')}")


def _viewpoint(node):
    scan = _scan(node)
    landable = scan.get("Landable")
    label = "landable" if landable is True else "not landable" if landable is False else "landability unknown"
    return f"{_name(node)} ({label}{', ringed' if _rings(scan) else ''})"


def _close(distance):
    threshold = _number(CLOSE_DISTANCE_KM)
    return (threshold is not None and threshold > 0 and math.isfinite(distance)
            and 0 <= distance < threshold * METRES_PER_KM)


def _km(distance):
    return f"{distance / METRES_PER_KM:,.3f} km"


def _rings(scan):
    """Embedded parent ring geometry is authoritative; standalone copies add nothing."""
    rings = {}
    conflicts = set()
    values = scan.get("Rings", [])
    for ring in values if isinstance(values, list) else []:
        if not isinstance(ring, dict):
            continue
        name = ring.get("Name")
        if not isinstance(name, str) or not name or name.endswith(" Belt"):
            continue
        inner, outer = _number(ring.get("InnerRad")), _number(ring.get("OuterRad"))
        if inner is None or outer is None or not 0 < inner < outer:
            continue
        if name in rings and rings[name] != (inner, outer):
            conflicts.add(name)
        rings[name] = (inner, outer)
    for name in conflicts:
        del rings[name]
    return [(name, *radii) for name, radii in sorted(rings.items(), key=lambda item: (item[1], item[0]))]


def _binary_compatible(first, second):
    """Require matching periods/eccentricities for the two-body barycentre model."""
    for field in ("OrbitalPeriod", "Eccentricity"):
        a, b = _number(first.get(field)), _number(second.get(field))
        if a is None or b is None or not math.isclose(a, b, rel_tol=BINARY_REL_TOL, abs_tol=1e-7):
            return False
        if field == "OrbitalPeriod" and (a <= 0 or b <= 0):
            return False
    inclinations = [_number(scan.get("OrbitalInclination")) for scan in (first, second)]
    if None in inclinations or not math.isclose(*inclinations, abs_tol=0.01):
        return False
    # Eccentric components must have opposing periapsides about the barycentre.
    # Circular orbits have no meaningful periapsis direction.
    if first["Eccentricity"] > 1e-7:
        angles = [_number(scan.get("Periapsis")) for scan in (first, second)]
        if None in angles or abs((angles[0] - angles[1]) % 360 - 180) > 0.01:
            return False
    return True


def close_pairs(system_map):
    nodes, children = _nodes(system_map), defaultdict(list)
    for body_id, node in sorted(nodes.items()):
        kind, parent_id = _parent(node)
        parent = nodes.get(parent_id, {})
        if parent_id is not None and (kind == "Null" or parent.get("kind") == "Barycentre"):
            children[parent_id].append(body_id)
    results = []
    for parent_id in sorted(children):
        ids = children[parent_id]
        # Count all direct children, including unscanned bodies: no multi-body sums.
        if len(ids) != 2:
            continue
        first, second = (nodes[body_id] for body_id in ids)
        scans = [_scan(first), _scan(second)]
        if not all(scan.get("PlanetClass") and not scan.get("StarType") for scan in scans):
            continue
        orbits, radii = [_orbit(s) for s in scans], [_radius(s) for s in scans]
        if None in orbits or None in radii or not _binary_compatible(*scans):
            continue
        low = sum(orbit[0] for orbit in orbits) - sum(radii)
        high = sum(orbit[1] for orbit in orbits) - sum(radii)
        if not all(math.isfinite(value) for value in (low, high)):
            continue
        description = f"{_viewpoint(first)} and {_viewpoint(second)}"
        if low < 0:
            results.append(f"Binary pair: {description}; calculated surface-to-surface clearance {_km(low)} at periapsis to {_km(high)} at apoapsis.")
        elif _close(low):
            results.append(f"Close binary pair: {description}; calculated surface-to-surface clearance {_km(low)} at periapsis to {_km(high)} at apoapsis.")
    return results


def close_moons_of_ringed_parents(system_map):
    nodes, results = _nodes(system_map), []
    for body_id, moon in sorted(nodes.items()):
        scan = _scan(moon)
        kind, parent_id = _parent(moon)
        parent = nodes.get(parent_id)
        if parent is None or kind not in (None, "Planet") or not scan.get("PlanetClass"):
            continue
        parent_scan = _scan(parent)
        rings = _rings(parent_scan)
        if not parent_scan.get("PlanetClass") or not rings:
            continue
        orbit, radius, parent_radius = _orbit(scan), _radius(scan), _radius(parent_scan)
        if orbit is None or radius is None:
            continue
        low, high = orbit
        evidence = []
        if parent_radius is not None:
            surface_low, surface_high = low - radius - parent_radius, high - radius - parent_radius
            if not all(math.isfinite(value) for value in (surface_low, surface_high)):
                pass
            elif surface_low < 0:
                evidence.append(f"calculated parent surface-to-surface clearance {_km(surface_low)} at periapsis to {_km(surface_high)} at apoapsis")
            elif _close(surface_low):
                evidence.append(f"calculated parent surface-to-surface clearance {_km(surface_low)} at periapsis to {_km(surface_high)} at apoapsis")
        for ring_name, inner, outer in rings:
            for edge_name, edge in (("inner", inner), ("outer", outer)):
                centre_min = max(low - edge, edge - high, 0)
                distance = max(centre_min - radius, 0)
                if _close(distance):
                    maximum = max(abs(low - edge), abs(high - edge)) - radius
                    evidence.append(f"{ring_name} {edge_name} edge: calculated radial surface-to-edge clearance {_km(distance)} minimum to {_km(max(maximum, 0))} maximum" + ("; radial ranges overlap" if centre_min <= radius else ""))
        if not evidence:
            continue
        if high + radius < rings[0][1]:
            location = "inside innermost ring throughout orbit"
        elif low - radius > max(ring[2] for ring in rings):
            location = "outside outermost ring throughout orbit"
        elif any(low - radius > left[2] and high + radius < right[1]
                 for left, right in zip(rings, rings[1:])):
            location = "between ring bands throughout orbit"
        else:
            location = "radial relationship varies or overlaps ring bands"
        results.append(f"Close moon of ringed parent: {_viewpoint(moon)} near {_name(parent)}; "
                       + f"orbital periapsis {_km(low)}, apoapsis {_km(high)}; "
                       + "; ".join(evidence) + f"; {location}.")
    return results


CURIOSITY_RULES = (close_pairs, close_moons_of_ringed_parents)


def find_curiosities(system_map) -> list[str]:
    results = []
    for rule in CURIOSITY_RULES:
        results.extend(rule(system_map))
    return results
