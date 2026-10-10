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
# Selection defaults are internal; descriptions report data, never these limits.
CLOSE_PAIR_GAP_RADII = 1.0  # Surface gap / sum of the component radii.
HIGH_INCLINATION_DEG = 15.0
POLAR_TOLERANCE_DEG = 15.0
SHORT_ORBIT_HOURS = 1.0
HIGH_ECCENTRICITY = 0.9
CLOSE_STAR_RADII = 5.0  # Centre distance / stellar radius at periapsis.
WIDE_RING_KM = 1_000_000.0
LARGE_RING_PARENT_RADII = 100.0
SMALL_LANDABLE_RADIUS_KM = 300.0
LARGE_LANDABLE_RADIUS_KM = 10_000.0
HIGH_LANDABLE_GRAVITY_G = 3.0
COLD_LANDABLE_K = 20.0
HOT_LANDABLE_K = 1500.0
FAST_ROTATION_HOURS = 1.0
SLOW_SPIN_ORBIT_RATIO = 10.0
INVERTED_SPIN_DEG = 175.0
EARTH_GRAVITY = 9.80665
EARTH_MASS_KG = 5.97219e24
GGG_CRITERIA_VERSION = "edGGG-temperature-table-2026-10-05"
# (surface temperature lower/upper bounds in K, minimum density in kg/m3).
# Pin the documented table rather than approximating the speculative cloud model.
_WATER_GGG_WINDOWS = (
    (158.0, 158.0, 315.0), (176.666641, 176.666702, 94.0),
    (188.333328, 188.333328, 44.0), (210.0, 210.0, 0.0),
    (217.499985, 217.500015, 6.0), (241.999985, 242.000015, 0.0),
)
_GGG_WINDOWS = {
    "Gas giant with water-based life": _WATER_GGG_WINDOWS,
    "Water giant": _WATER_GGG_WINDOWS,
    "Water giant with life": _WATER_GGG_WINDOWS,
    "Helium gas giant": _WATER_GGG_WINDOWS,
    "Helium-rich gas giant": _WATER_GGG_WINDOWS,
    "Class I gas giant": ((129.999985, 130.000015, 2078.0), (115.0, 115.0, 0.0)),
    "Gas giant with ammonia-based life": ((129.999985, 130.000015, 2078.0), (115.0, 115.0, 0.0)),
    "Class III gas giant": tuple((t, t, 0.0) for t in (370, 520, 550, 580, 610, 640, 670, 700, 780)),
    "Class IV gas giant": ((1149.999878, 1150.0, 0.0),),
}
_RARE_CLASSES = {"Earthlike body", "Helium gas giant", "Helium-rich gas giant"}
_TERRESTRIAL_CLASSES = {"Rocky body", "Rocky ice body", "Icy body", "Metal rich body",
                        "High metal content body", "Earthlike body", "Water world", "Ammonia world"}


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


def _planet_class(scan):
    value = scan.get("PlanetClass")
    if not isinstance(value, str):
        return ""
    return value.removeprefix("Sudarsky ").replace("class ", "Class ").replace(" based life", "-based life").replace("Helium rich", "Helium-rich")


def _viewpoint(node):
    scan = _scan(node)
    landable = scan.get("Landable")
    label = "landable" if landable is True else "not landable" if landable is False else "landability unknown"
    details = [label]
    if _rings(scan):
        details.append("ringed")
    if _planet_class(scan) in _RARE_CLASSES:
        details.append(scan["PlanetClass"])
    biology = _biology(node)
    if biology:
        details.append(biology)
    return f"{_name(node)} ({', '.join(details)})"


def _biology(node):
    counts = []
    events = node.get("event_data", {})
    if not isinstance(events, dict):
        return ""
    for event_type in ("FSSBodySignals", "SAASignalsFound"):
        event = events.get(event_type, {})
        if not isinstance(event, dict):
            continue
        signals = event.get("Signals", [])
        for signal in signals if isinstance(signals, list) else []:
            if isinstance(signal, dict) and signal.get("Type") == "$SAA_SignalType_Biological;":
                count = signal.get("Count")
                if isinstance(count, int) and not isinstance(count, bool) and count > 0:
                    counts.append(count)
    return f"{max(counts)} biological signals" if counts else ""


def _planet_parent(nodes, node):
    kind, parent_id = _parent(node)
    parent = nodes.get(parent_id)
    if kind in (None, "Planet") and parent_id != _id(node.get("body_id")) and parent:
        scan = _scan(parent)
        if scan.get("PlanetClass") and not scan.get("StarType"):
            return parent
    return None


def _nested(nodes, node):
    return len(_planet_ancestors(nodes, node)) >= 2


def _planet_ancestors(nodes, node):
    result, seen = [], {id(node)}
    while (parent := _planet_parent(nodes, node)) is not None:
        if id(parent) in seen:
            return []
        seen.add(id(parent))
        result.append(parent)
        node = parent
    return result


def _inclination(scan):
    value = _number(scan.get("OrbitalInclination"))
    if value is None or abs(value) > 180:
        return ""
    angle = abs(value)
    if min(angle, 180 - angle) < HIGH_INCLINATION_DEG:
        return ""
    labels = [f"orbital inclination {value:.3f} degrees"]
    if abs(angle - 90) <= POLAR_TOLERANCE_DEG:
        labels.append("near-polar orbit")
    if angle > 90:
        labels.append("retrograde orbit")
    return "; ".join(labels)


def _period(seconds):
    return f"{seconds / 3600:,.3f} hours"


def _orbital_details(scan):
    details = []
    period = _number(scan.get("OrbitalPeriod"))
    if period is not None and period > 0 and period <= SHORT_ORBIT_HOURS * 3600:
        details.append(f"short orbital period {_period(period)}")
    orbit = _orbit(scan)
    if orbit and scan["Eccentricity"] >= HIGH_ECCENTRICITY:
        details.append(f"eccentricity {scan['Eccentricity']:.6f}")
    return details


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


def _binary_pairs(system_map):
    nodes, children = _nodes(system_map), defaultdict(list)
    for body_id, node in sorted(nodes.items()):
        kind, parent_id = _parent(node)
        parent = nodes.get(parent_id, {})
        if parent_id is not None and (kind == "Null" or parent.get("kind") == "Barycentre"):
            children[parent_id].append(body_id)
    for parent_id in sorted(children):
        ids = children[parent_id]
        # Count all direct children, including unscanned bodies: no multi-body sums.
        if len(ids) != 2:
            continue
        first, second = (nodes[body_id] for body_id in ids)
        scans = [_scan(first), _scan(second)]
        orbits, radii = [_orbit(s) for s in scans], [_radius(s) for s in scans]
        if None in orbits or None in radii or not _binary_compatible(*scans):
            continue
        low = sum(orbit[0] for orbit in orbits) - sum(radii)
        high = sum(orbit[1] for orbit in orbits) - sum(radii)
        if not all(math.isfinite(value) for value in (low, high)):
            continue
        yield first, second, low, high, sum(radii)


def close_pairs(system_map):
    results = []
    for first, second, low, high, total_radius in _binary_pairs(system_map):
        scans = [_scan(first), _scan(second)]
        if not all(scan.get("PlanetClass") and not scan.get("StarType") for scan in scans):
            continue
        description = f"{_viewpoint(first)} and {_viewpoint(second)}"
        relative_gap = _number(low / total_radius)
        if low < 0 or _close(low) or relative_gap is not None and relative_gap < CLOSE_PAIR_GAP_RADII:
            label = "Binary pair" if low < 0 else "Close binary pair"
            text = (f"{label}: {description}; calculated surface-to-surface clearance {_km(low)} "
                    f"at periapsis to {_km(high)} at apoapsis")
            if relative_gap is not None:
                text += f"; surface gap {relative_gap:.3f} combined radii"
            results.append(text + ".")
    return results


def close_moons_of_ringed_parents(system_map):
    nodes, results = _nodes(system_map), []
    for body_id, moon in sorted(nodes.items()):
        scan = _scan(moon)
        parent = _planet_parent(nodes, moon)
        if parent is None or not scan.get("PlanetClass") or scan.get("StarType"):
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
        label = "Close nested moon of ringed parent" if _nested(nodes, moon) else "Close moon of ringed parent"
        inclination = _inclination(scan)
        if inclination:
            label = "Highly inclined " + label[0].lower() + label[1:]
            evidence.append(inclination)
        for ring_name, inner, outer in rings:
            if (outer - inner >= WIDE_RING_KM * METRES_PER_KM
                    or parent_radius and outer / parent_radius >= LARGE_RING_PARENT_RADII):
                evidence.append(f"large ring {ring_name}: inner radius {_km(inner)}, outer radius {_km(outer)}, width {_km(outer - inner)}")
        results.append(f"{label}: {_viewpoint(moon)} near {_viewpoint(parent)}; "
                       + f"orbital periapsis {_km(low)}, apoapsis {_km(high)}; "
                       + "; ".join(evidence) + f"; {location}.")
    return results


def close_nested_moons(system_map):
    """Direct nested closeness and conservative bounds to ringed ancestors."""
    nodes, results = _nodes(system_map), []
    for _, moon in sorted(nodes.items()):
        if not _nested(nodes, moon):
            continue
        scan = _scan(moon)
        parent = _planet_parent(nodes, moon)
        orbit, radius = _orbit(scan), _radius(scan)
        if orbit is None or radius is None or scan.get("StarType"):
            continue
        parent_scan = _scan(parent)
        parent_radius = _radius(parent_scan)
        evidence = []
        # The ringed-immediate-parent rule already emits this relationship.
        if parent_radius and not _rings(parent_scan):
            low, high = (distance - parent_radius - radius for distance in orbit)
            if math.isfinite(high) and (low < 0 or _close(low)):
                evidence.append(f"calculated surface-to-surface clearance to {_name(parent)} {_km(low)} at periapsis to {_km(high)} at apoapsis")
        low, high = orbit
        orbiting_parent = parent
        for ancestor in _planet_ancestors(nodes, moon)[1:]:
            parent_orbit = _orbit(_scan(orbiting_parent))
            if parent_orbit is None:
                break
            # Triangle inequality covers every intervening orbit without phase guesses.
            low, high = (max(0, parent_orbit[0] - high, low - parent_orbit[1]),
                         parent_orbit[1] + high)
            if not math.isfinite(high):
                break
            for ring_name, inner, outer in _rings(_scan(ancestor)):
                for edge_name, edge in (("inner", inner), ("outer", outer)):
                    minimum = max(max(low - edge, edge - high, 0) - radius, 0)
                    maximum = max(max(abs(low - edge), abs(high - edge)) - radius, 0)
                    # Require the entire bound to be close, not just a possible overlap.
                    if _close(maximum):
                        evidence.append(f"{_name(ancestor)} {ring_name} {edge_name} edge: calculated radial clearance bounds {_km(minimum)} to {_km(maximum)}; ancestor centre-distance bounds {_km(low)} to {_km(high)}")
            orbiting_parent = ancestor
        if evidence:
            results.append(f"Close nested moon: {_viewpoint(moon)} orbiting {_viewpoint(parent)}; orbital periapsis {_km(orbit[0])}, apoapsis {_km(orbit[1])}; " + "; ".join(evidence) + ".")
    return results


def close_stellar_relationships(system_map):
    results = []
    for first, second, low, high, total_radius in _binary_pairs(system_map):
        if not all(_scan(node).get("StarType") for node in (first, second)):
            continue
        if low < 0 or _close(low) or low / total_radius < CLOSE_PAIR_GAP_RADII:
            results.append(f"Close stellar binary: {_name(first)} ({_scan(first)['StarType']} star) and {_name(second)} ({_scan(second)['StarType']} star); calculated surface-to-surface clearance {_km(low)} at periapsis to {_km(high)} at apoapsis; orbital period {_period(_scan(first)['OrbitalPeriod'])}.")
    nodes = _nodes(system_map)
    for _, body in sorted(nodes.items()):
        kind, parent_id = _parent(body)
        parent = nodes.get(parent_id)
        scan = _scan(body)
        if kind not in (None, "Star") or parent is None or not scan.get("PlanetClass"):
            continue
        parent_scan = _scan(parent)
        stellar_radius = _radius(parent_scan)
        orbit, radius = _orbit(scan), _radius(scan)
        if not parent_scan.get("StarType") or stellar_radius is None or orbit is None or radius is None:
            continue
        if orbit[0] / stellar_radius <= CLOSE_STAR_RADII:
            low, high = (distance - stellar_radius - radius for distance in orbit)
            if math.isfinite(high):
                results.append(f"Close stellar companion: {_viewpoint(body)} orbiting {_name(parent)} ({parent_scan['StarType']} star); calculated surface-to-surface clearance {_km(low)} at periapsis to {_km(high)} at apoapsis; orbital periapsis {_km(orbit[0])}, apoapsis {_km(orbit[1])}.")
    return results


def _density(scan):
    mass, radius = _number(scan.get("MassEM")), _radius(scan)
    if mass is None or mass <= 0 or radius is None:
        return None
    try:
        density = mass * EARTH_MASS_KG / (4 / 3 * math.pi * radius ** 3)
    except (OverflowError, ZeroDivisionError):
        return None
    return density if math.isfinite(density) and density > 0 else None


def possible_green_gas_giants(system_map):
    results = []
    for _, node in sorted(_nodes(system_map).items()):
        scan = _scan(node)
        windows = _GGG_WINDOWS.get(_planet_class(scan), ())
        temperature = _number(scan.get("SurfaceTemperature"))
        if not windows or temperature is None or temperature <= 0 or scan.get("StarType"):
            continue
        density = _density(scan)
        if any(low <= temperature <= high and (minimum == 0 or density is not None and density >= minimum)
               for low, high, minimum in windows):
            evidence = f"{scan['PlanetClass']}; surface temperature {temperature:.6f} K"
            if density is not None:
                evidence += f"; calculated bulk density {density:,.3f} kg/m3"
            results.append(f"Possible green gas giant: {_name(node)}; {evidence}.")
    return results


def unusual_body_properties(system_map):
    """Combine independent body-property findings into one factual entry per body."""
    nodes, results = _nodes(system_map), []
    for _, node in sorted(nodes.items()):
        scan = _scan(node)
        planet_class = _planet_class(scan)
        if not planet_class or scan.get("StarType"):
            continue
        details = []
        orbit = _orbit(scan)
        if _parent(node)[1] is not None:
            details.extend(_orbital_details(scan))
            if details and orbit:
                details.append(f"orbital periapsis {_km(orbit[0])}, apoapsis {_km(orbit[1])}")
        rings = _rings(scan)
        if rings and (scan.get("Landable") is True or planet_class in _TERRESTRIAL_CLASSES):
            details.append(f"ringed {scan['PlanetClass']}")
            details.extend(f"{name}: inner radius {_km(inner)}, outer radius {_km(outer)}" for name, inner, outer in rings)
        parent = _planet_parent(nodes, node)
        if planet_class in _RARE_CLASSES and parent:
            details.append(f"{scan['PlanetClass']} moon of {_name(parent)}")
        radius, gravity = _radius(scan), _number(scan.get("SurfaceGravity"))
        temperature = _number(scan.get("SurfaceTemperature"))
        if scan.get("Landable") is True:
            if radius and (radius / METRES_PER_KM <= SMALL_LANDABLE_RADIUS_KM or radius / METRES_PER_KM >= LARGE_LANDABLE_RADIUS_KM):
                details.append(f"{'small' if radius / METRES_PER_KM <= SMALL_LANDABLE_RADIUS_KM else 'large'} landable radius {_km(radius)}")
            if gravity is not None and gravity >= HIGH_LANDABLE_GRAVITY_G * EARTH_GRAVITY:
                details.append(f"surface gravity {gravity / EARTH_GRAVITY:.3f} g")
            if temperature is not None and temperature > 0 and (temperature <= COLD_LANDABLE_K or temperature >= HOT_LANDABLE_K):
                details.append(f"surface temperature {temperature:.6f} K")
        rotation = _number(scan.get("RotationPeriod"))
        tilt = _number(scan.get("AxialTilt"))
        if rotation is not None and rotation != 0:
            spin = []
            if abs(rotation) <= FAST_ROTATION_HOURS * 3600:
                spin.append(f"rapid rotation period {_period(abs(rotation))}")
            period = _number(scan.get("OrbitalPeriod"))
            ratio = _number(abs(rotation) / period) if period is not None and period > 0 else None
            if ratio is not None and ratio >= SLOW_SPIN_ORBIT_RATIO:
                spin.append(f"rotation/orbit period ratio {ratio:.3f}")
            # Ordinary retrograde tilt is common. Select inverted spins separately,
            # or include retrograde orientation on an already notable spin finding.
            if tilt is not None and math.pi / 2 < abs(tilt) <= math.pi:
                if spin or abs(math.degrees(tilt)) >= INVERTED_SPIN_DEG:
                    spin.append(f"retrograde axial tilt {math.degrees(tilt):.3f} degrees")
            if spin:
                details.extend(spin)
                details.append(f"recorded rotation period {rotation:.6f} seconds")
                if isinstance(scan.get("TidalLock"), bool):
                    details.append(f"tidally locked: {'yes' if scan['TidalLock'] else 'no'}")
        if details:
            results.append(f"Unusual body: {_viewpoint(node)}; " + "; ".join(details) + ".")
    return results


CURIOSITY_RULES = (close_pairs, close_moons_of_ringed_parents, close_nested_moons,
                   close_stellar_relationships, possible_green_gas_giants,
                   unusual_body_properties)


def find_curiosities(system_map) -> list[str]:
    results = []
    for rule in CURIOSITY_RULES:
        results.extend(rule(system_map))
    return results
