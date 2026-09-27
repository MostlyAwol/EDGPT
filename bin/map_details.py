"""Human-readable views of all data retained in a saved system map."""

from html import escape
import math
import re

from system_map import _hierarchy, _scan_status


def text(value):
    return escape(str(value), quote=True)


def label(value):
    value = str(value).strip("$;").replace("SAA_SignalType_", "")
    value = value.replace("eRingClass_", "").replace("_", " ")
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)


def number(value, divisor=1, unit=""):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return "Unknown"
    value /= divisor
    formatted = f"{value:,.2f}".rstrip("0").rstrip(".")
    if value and abs(value) < 0.01:
        formatted = f"{value:.3g}"
    return formatted + (" " + unit if unit else "")


def fields(value):
    """Render arbitrary retained fields without dropping nested or future data."""
    if isinstance(value, dict):
        if not value:
            return '<span class="muted">None recorded</span>'
        return '<dl class="fields">' + "".join(
            f'<div><dt title="{text(key)}">{text(label(key))}</dt><dd>{fields(item)}</dd></div>'
            for key, item in value.items()) + '</dl>'
    if isinstance(value, list):
        return ('<ol class="records">' + "".join(f'<li>{fields(item)}</li>' for item in value)
                + '</ol>') if value else '<span class="muted">None recorded</span>'
    if value is None:
        return '<span class="muted">Not recorded</span>'
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return text(value)


def disclosure(title, content, key):
    return f'<details data-key="{text(key)}"><summary>{text(title)}</summary>{content}</details>'


def chip(value, tone=""):
    return f'<span class="chip {tone}">{text(value)}</span>'


def tone(node):
    kind = node.get("kind")
    body = str(node.get("body_type", "")).lower()
    if kind == "Star":
        return "star"
    if kind == "Barycentre":
        return "barycentre"
    if kind in ("Ring", "Belt cluster"):
        return "ring"
    if "earth" in body or "water" in body:
        return "water"
    if "ammonia" in body:
        return "ammonia"
    if "icy" in body or "ice" in body:
        return "ice"
    if "gas giant" in body:
        return "gas"
    return "rock"


def body_card(node):
    events = node.get("event_data", {})
    scan = events.get("Scan", {})
    orbit = scan or events.get("ScanBaryCentre", {})
    key = str(node.get("body_id", "unknown"))
    metrics = []
    if node.get("distance_ls") is not None:
        metrics.append(("Arrival", number(node["distance_ls"], unit="ls")))
    for name, field, divisor, unit in (
        ("Mass", "MassEM", 1, "M⊕"), ("Mass", "StellarMass", 1, "M☉"),
        ("Radius", "Radius", 1000, "km"), ("Gravity", "SurfaceGravity", 9.80665, "g"),
        ("Temperature", "SurfaceTemperature", 1, "K"),
        ("Orbit", "OrbitalPeriod", 86400, "d"), ("Rotation", "RotationPeriod", 86400, "d"),
        ("Semi-major axis", "SemiMajorAxis", 299792458, "ls"),
        ("Pressure", "SurfacePressure", 101325, "atm"), ("Age", "Age_MY", 1, "Myr"),
    ):
        if orbit.get(field) is not None:
            metrics.append((name, number(orbit[field], divisor, unit)))
    badges = []
    for field, caption in (("Landable", "Landable"), ("TidalLock", "Tidally locked")):
        if scan.get(field):
            badges.append(chip(caption, "positive"))
    if scan.get("TerraformState"):
        badges.append(chip(label(scan["TerraformState"]), "positive"))
    for field, yes, no in (("WasDiscovered", "Previously discovered", "Undiscovered at scan"),
                           ("WasMapped", "Previously mapped", "Unmapped at scan")):
        if field in scan:
            badges.append(chip(yes if scan[field] else no))
    if "SAAScanComplete" in events:
        badges.append(chip("Surface mapped", "positive"))
    if not scan and "ScanBaryCentre" not in events:
        badges.append(chip("Scan not recorded"))
    # Prefer the latest surface signals over the FSS report for the same type.
    signals = {}
    for event_type in ("FSSBodySignals", "SAASignalsFound"):
        for signal in events.get(event_type, {}).get("Signals", []):
            signals[signal.get("Type", signal.get("Type_Localised", "Signal"))] = signal
    for signal in signals.values():
        name = signal.get("Type_Localised") or label(signal.get("Type", "Signal"))
        badges.append(chip(f'{name} × {signal.get("Count", "?")}', "signal"))
    organisms = events.get("ScanOrganic", [])
    if isinstance(organisms, dict):
        organisms = [organisms]
    for species in dict.fromkeys(item.get("Species_Localised") or item.get("Species")
                                 for item in organisms):
        if species:
            badges.append(chip(label(species), "signal"))
    env = []
    for field in ("Atmosphere", "Volcanism", "Luminosity"):
        if scan.get(field):
            env.append(f'<span><b>{text(label(field))}</b> {text(scan[field])}</span>')
    rings = "".join(
        '<div class="ringline">' + chip(label(ring.get("RingClass", "Ring")), "ring")
        + f'<span>{text(ring.get("Name", "Unnamed ring"))}</span>'
        + f'<span class="muted">{text(number(ring.get("InnerRad"), 1000, "km"))} – '
        + text(number(ring.get("OuterRad"), 1000, "km")) + '</span></div>'
        for ring in scan.get("Rings", []))
    materials = scan.get("Materials", [])
    if isinstance(materials, dict):
        materials = [{"Name": name, "Percent": amount} for name, amount in materials.items()]
    material_html = "".join(chip(f'{label(item.get("Name", "Unknown"))} {number(item.get("Percent"), unit="%")}', "material")
                            for item in materials)
    detail_html = "".join(disclosure(label(name), fields(value), f"body-{key}-{name}")
                          for name, value in events.items())
    detail_html += disclosure("Hierarchy & identity", fields({k: v for k, v in node.items() if k != "event_data"}), f"body-{key}-identity")
    style = tone(node)
    return (f'<article class="body-card {style}" id="body-{text(key)}">'
            f'<div class="body-heading"><span class="orb" aria-hidden="true"></span><h3>{text(node.get("name", "Unknown body"))}</h3>'
            + chip(node.get("body_type", "Unknown"), style)
            + f'<span class="body-id">{text(node.get("kind", "Body"))} · ID {text(key)}</span></div>'
            + '<div class="metrics">' + "".join(f'<div><span>{text(name)}</span><strong>{text(value)}</strong></div>' for name, value in metrics) + '</div>'
            + ('<div class="environment">' + "".join(env) + '</div>' if env else '')
            + '<div class="badges">' + "".join(badges) + '</div>'
            + rings
            + ('<div class="materials"><span class="mini-label">Materials</span>' + material_html + '</div>' if material_html else '')
            + disclosure("All recorded details", '<p class="muted detail-note">Journal fields below retain their original values and units.</p>' + detail_html, f"body-{key}-details") + '</article>')


def render_details(model):
    roots, children = _hierarchy(model)
    nodes = model["nodes"]
    scans = [node.get("event_data", {}).get("Scan", {}) for node in nodes.values()]
    stats = (("Scanned bodies", sum(bool(scan) for scan in scans)),
             ("Expected bodies", model.get("body_count") if model.get("body_count") is not None else "—"),
             ("Landable", sum(bool(scan.get("Landable")) for scan in scans)),
             ("Surface mapped", sum("SAAScanComplete" in node.get("event_data", {}) for node in nodes.values())),
             ("Visits indexed", model.get("visits", 0)))
    html = '<div class="stats">' + "".join(f'<div><strong>{text(value)}</strong><span>{text(name)}</span></div>' for name, value in stats) + '</div>'
    html += f'<p class="scan-status"><span class="live-dot"></span>{text(_scan_status(model))}</p>'
    system_events = model.get("system_events", {})
    arrival = max((value for name, value in system_events.items() if name in ("FSDJump", "Location", "CarrierJump")),
                  key=lambda value: str(value.get("timestamp", "")), default={})
    overview = []
    for field in ("SystemAllegiance", "SystemEconomy", "SystemSecondEconomy", "SystemGovernment", "SystemSecurity", "Population"):
        value = arrival.get(field + "_Localised", arrival.get(field))
        if value is not None and value != "":
            overview.append(f'<div><dt>{text(label(field.removeprefix("System")))}</dt><dd>{text(value)}</dd></div>')
    if arrival.get("StarPos"):
        overview.append(f'<div><dt>Galactic position (ly)</dt><dd>{text(" / ".join(str(v) for v in arrival["StarPos"]))}</dd></div>')
    if overview:
        html += '<dl class="overview">' + "".join(overview) + '</dl>'
    html += '<div class="section-heading"><h2>System hierarchy</h2><span>Stars · planets · moons · rings</span></div><ul class="tree">'
    seen = set()

    def branch(key):
        if key in seen:
            return '<li class="muted">Repeated hierarchy link omitted</li>'
        seen.add(key)
        card = body_card(nodes[key])
        child_html = '<ul>' + "".join(branch(child) for child in children[key]) + '</ul>' if children[key] else ''
        return '<li>' + card + child_html + '</li>'

    for key in roots:
        html += branch(key)
    for key in nodes:
        if key not in seen:
            html += branch(key)
    if not nodes:
        html += '<li class="empty">No bodies recorded yet. Scan bodies to populate the map.</li>'
    html += '</ul>'
    signals = model.get("signals", {})
    html += '<div class="section-heading"><h2>System signals</h2><span>' + str(len(signals)) + ' recorded</span></div>'
    if not signals:
        html += '<p class="muted">No system signals recorded.</p>'
    for index, signal in enumerate(signals.values()):
        name = signal.get("SignalName_Localised") or signal.get("SignalName", "Signal")
        html += disclosure(str(name), fields(signal), f"system-signal-{index}")
    html += '<div class="section-heading"><h2>System records</h2><span>Complete retained journal details</span></div>'
    metadata = {k: v for k, v in model.items() if k not in ("nodes", "system_events", "signals")}
    html += disclosure("Map history & scan progress", fields(metadata), "map-metadata")
    html += "".join(disclosure(label(name), fields(value), f"system-{name}") for name, value in system_events.items())
    return html
