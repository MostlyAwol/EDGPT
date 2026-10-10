# Curiosities roadmap

Created 2026-10-08. Updated 2026-10-10: all five initial detector families and
the additional candidate categories below are implemented. Phase-dependent
geometry and broader green gas giant prediction remain research topics.

## Purpose

Develop `bin/curiosities.py` into a detector for unusual Elite Dangerous
systems worth investigating or visiting. Favor notable relationships and
geometry, with measurements explaining why a body stands out. Ordinary body
classifications already belong in the system overview.

This roadmap owns curiosity planning separately from the main EDGPT roadmap.
The initial priorities below come from the requested exploration interests;
the additional candidates were authorized for implementation on 2026-10-10.
Initial local defaults are documented below and remain adjustable.

## Enabled rules and tuning

Change `CLOSE_DISTANCE_KM = 2000.0` near the top of `bin/curiosities.py` to
adjust absolute proximity checks, then restart the helper processes.
Exactly 2000 km does not pass the absolute check; a binary may still qualify by
the separate body-size-relative check. The threshold uses unrounded distances;
displayed distances are rounded to three decimal places in km.
Partial and completed saved system summaries rerun these rules when retrieved.

The additional selection defaults are named constants in `curiosities.py`:

| Constant | Default | Selection |
| --- | ---: | --- |
| `CLOSE_PAIR_GAP_RADII` | 1 | Binary surface gap strictly smaller than this multiple of combined radii |
| `HIGH_INCLINATION_DEG` | 15 | Minimum departure from coplanarity |
| `POLAR_TOLERANCE_DEG` | 15 | Maximum departure from 90 degrees for near-polar label |
| `SHORT_ORBIT_HOURS` | 1 | Maximum positive orbital period |
| `HIGH_ECCENTRICITY` | 0.9 | Minimum eccentricity in a valid bound orbit |
| `CLOSE_STAR_RADII` | 5 | Maximum planetary periapsis / stellar radius |
| `WIDE_RING_KM` | 1000000 | Minimum nearby ring width for large-ring detail |
| `LARGE_RING_PARENT_RADII` | 100 | Alternative minimum outer ring radius / parent radius |
| `SMALL_LANDABLE_RADIUS_KM` | 300 | Maximum small landable radius |
| `LARGE_LANDABLE_RADIUS_KM` | 10000 | Minimum large landable radius |
| `HIGH_LANDABLE_GRAVITY_G` | 3 | Minimum landable surface gravity |
| `COLD_LANDABLE_K` | 20 | Maximum positive cold landable temperature |
| `HOT_LANDABLE_K` | 1500 | Minimum hot landable temperature |
| `FAST_ROTATION_HOURS` | 1 | Maximum nonzero absolute rotation period |
| `SLOW_SPIN_ORBIT_RATIO` | 10 | Minimum absolute rotation / positive orbital period |
| `INVERTED_SPIN_DEG` | 175 | Minimum absolute axial tilt for standalone retrograde spin alert |

These are local exploration defaults, not claims of galaxy-wide rarity. Selection
uses original values. Body-property findings combine into one entry per body;
a distinct relationship entry may coexist. No threshold text appears in matches.

Geometry uses retained `Scan` fields. `Radius`, `SemiMajorAxis`, `InnerRad`
and `OuterRad` are handled in metres, with output divided by 1000 for km.
`Eccentricity` is dimensionless; `OrbitalPeriod` is seconds, and orbital
inclination/periapsis are degrees. `AxialTilt` is radians, `RotationPeriod` is
seconds, `SurfaceGravity` is m/s2, and `SurfaceTemperature` is Kelvin. Gravity
conversion uses `9.80665 m/s2` per g. Frontier's v32 manual section 6.3 describes
scan fields and the parent hierarchy; the manual does not explicitly
label every distance unit. Observatory's journal field definitions provide an
additional implementation reference (including the metre-based body radius in
[Scan.cs](https://github.com/Xjph/ObservatoryCore/blob/master/ObservatoryFramework/Files/Journal/Exploration/Scan.cs)).
Missing, non-finite, Boolean, string, negative or unsupported orbital values
are skipped rather than replaced by zero. Bound orbits require `a > 0` and
`0 <= e < 1`, giving centre-distance limits `a(1-e)` and `a(1+e)`.

**Close pairs:** require exactly two known direct children of a non-root
barycentre, both with planetary scans, valid radii/orbits and positive matching
periods. Periods and eccentricities must agree within relative tolerance `1e-5`
(absolute tolerance `1e-7`); inclinations within 0.01 degrees. Eccentric orbits
also require opposing periapsides within 0.01 degrees. The common barycentre
may be inferred or absent when both chains explicitly identify it. `Null:0`
is a root sentinel and cannot identify a binary. Planet/moon siblings orbiting
a normal body do not qualify.

Under the two-body binary model, relative semimajor axis is `a1+a2`.
Reported surface clearance limits are the sums of component periapsis or
apoapsis distances minus both radii. The minimum drives the threshold;
the maximum is also reported. Body-size selection additionally compares
minimum clearance divided by the sum of component radii.
Each pair is reported once, with both names, recorded landability and ring
status. Negative calculated clearance is reported as a signed value.
Scans do not verify orbital phase or full orientation: these are model-based
estimates, not measured current separation. Multi-body and incomplete binaries
are skipped. Stellar binary detection uses the same compatibility checks and
clearance calculations, but requires both components to have stellar scans.

**Moons of ringed parents:** require a scanned planetary immediate parent,
at least one valid embedded ring, and a moon radius and bound orbit.
Nested moons qualify when their immediate parent is ringed; a distant ringed
ancestor alone cannot qualify. Parent surface clearance, when its radius is
available, is `a(1-e)-Rmoon-Rparent` through `a(1+e)-Rmoon-Rparent`.
Each named ring's inner and outer edges are screened separately. For edge
radius `r`, minimum radial surface clearance is
`max(max(periapsis-r, r-apoapsis, 0)-Rmoon, 0)`.
The maximum radial clearance uses the larger absolute endpoint distance
minus the moon radius, clamped to zero. Each matched edge reports its minimum
and maximum radial clearance. Moon orbital periapsis and apoapsis are also
included. Zero clearance is explicitly labelled as radial range overlap.

Parent and edge findings are combined into one string per moon, with
inside-innermost/between-bands/outside-outermost status when that relation
persists for the whole moon over its orbit. Otherwise the relationship is
labelled varying or overlapping. Asteroid belts are excluded; embedded rings
are authoritative, standalone copies are ignored, and identical embedded
duplicates collapse. Conflicting geometry for a duplicate name is skipped.
Radial edge screening is not a 3D distance to ring material, evidence of a
ring crossing, or proof of shepherding.

**Inclined moons:** combined into the ringed-parent finding. Inclination is the
journal's orbital reference frame, not a reconstructed ring plane. For valid
signed inclination in `[-180, 180]`, departure from coplanarity is
`min(abs(i), 180-abs(i))`. Near-polar and retrograde (`abs(i)>90`) labels are
separate; near-180-degree coplanar orbits do not qualify simply as inclined.
Recorded biological signals are added to relationship descriptions, using the
maximum FSS/SAA count rather than adding duplicate observations.

**Nested moons:** require at least two consecutively scanned planetary ancestors.
Immediate-parent clearance is checked even without parent rings. Direct ringed
parent findings are emitted by the existing ring rule without repeating them.
For more distant ringed ancestors, combine every intervening orbit. Descendant
bounds `[low, high]` and parent orbit `[p_low, p_high]` become
`[max(0, p_low-high, low-p_high), p_high+high]` by triangle inequality. Stop at
missing/invalid intervening data and reject cycles. Ancestor ring proximity
requires the **maximum** radial clearance bound to pass the threshold; a
possible radial overlap alone is insufficient. Report these as conservative
centre-distance/radial-clearance bounds, not ancestor periapsis or current positions.

**Possible GGGs:** pin `GGG_CRITERIA_VERSION` to
`edGGG-temperature-table-2026-10-05`. `_GGG_WINDOWS` contains the precise
temperature endpoints and density floors from the dated community table.
Water-life, water, helium, and helium-rich giants use its six windows between
158 and 242 K. Class I/ammonia-life use the narrow 130 K window with a density
floor of 2078 kg/m3 plus exact 115 K. Class III uses 520-700 K in 30 K steps,
plus exact 370/780 K; Class IV uses 1149.999878-1150 K.
Endpoints are inclusive with no extra rounding tolerance. Density is
`MassEM * 5.97219e24 / (4/3 * pi * Radius**3)` in kg/m3. Valid mass/radius are
required for positive density floors; temperature-only cases can match without
them. Journal aliases cover unhyphenated life/helium labels and older Sudarsky
class names. Matches report possible GGG, class, precise temperature and available
density; they do not include the criterion version.

This is selective screening, not a complete GGG classifier. Density-dependent
cloud-depth cases, hidden random temperature nudges, Class II/V coverage, and
cross-version behavior remain research. Exact 115/370 K cases can be affected by
the unknown nudge. Broad cold-temperature ranges never trigger merely because
a nudge is theoretically possible. Published catalog fixtures have rounded
radii, so they validate table screening, not the game's cloud algorithm.

Validation uses synthetic positive/negative/boundary examples in
`tests/test_curiosities.py` and a saved-map refresh test in
`tests/test_system_summary.py`, including eccentricity, invalid/missing fields,
root sentinels, inferred barycentres, nesting, duplicate rings, stable ordering
and input immutability. Published GGG examples and synthetic adjacent-temperature
and low-density negatives are in `tests/fixtures/curiosity_ggg_examples.json`
with sources. Initial read-only aggregate review of saved maps reduced noisy
50 K cold-world and ordinary-retrograde defaults to the limits above. No raw
maps, local databases, system names, or commander details from that review are
committed. Ongoing broader calibration remains useful.

## 1. Shared relationship and geometry helpers

- [x] Read scans from `nodes[*].event_data.Scan` and resolve bodies using IDs,
  `parent_id`, and `parent_chain`; do not infer relationships from body names.
- [x] Distinguish direct parents, shared barycentres, and distant ancestors.
  Preserve nested moon relationships and handle missing/inferred parent nodes.
- [x] Establish units from Frontier's journal documentation. Keep calculations
  in journal units and explicitly convert displayed distances to km and periods
  to hours or days.
- [x] Validate required numbers, rejecting non-finite or physically invalid
  values. Missing values must not become zeros or false matches.
- [x] Support orbital distance ranges from semimajor axis and eccentricity:
  periapsis `a * (1 - e)`, apoapsis `a * (1 + e)` for supported bound orbits.
- [x] For verified two-body binary orbits around a common barycentre, establish
  when the component semimajor axes can be combined into a relative orbit.
  Do not subtract arbitrary sibling orbital radii to claim a close pair.
- [x] Distinguish nominal separation, predicted closest approach, conservative
  bounds, and current separation. Orbital elements alone must not be presented
  as a measurement of where bodies are now.
- [x] Define ring geometry limitations: radial proximity is a screening metric,
  not a three-dimensional distance to ring material. Orbital inclination may
  use a different reference plane from a parent's equator/rings.

## 2. Initial detector priorities

### 2.1 Close pairs

- [x] Detect unusually close binary planets and binary moons under the documented model.
- [x] Use surface-to-surface separation, subtracting both body radii from a
  justified centre-to-centre separation; include the distance basis in output.
- [x] Report both body names and landability; identify pairs with a landable
  viewpoint and pairs where one or both bodies have rings.
- [x] Compare absolute clearance and separation relative to body size so large
  apparent companions can stand out too. Keep the criteria explicit.
- [x] Report negative calculated clearance as a signed value with the same
  periapsis and apoapsis labels used for other pairs.

### 2.2 Close moons of ringed parents

- [x] Find moons close to a ringed parent's surface and separately screen for
  proximity to each ring's inner or outer edge.
- [x] Distinguish moons inside the innermost ring, between ring bands, and
  outside the outermost ring. These are shepherd-moon candidates, not proof
  that the moon physically confines the ring.
- [x] Account for moon radius and eccentricity. Report the relevant ring name
  and whether the radial relationship persists or occurs only over part of
  the orbit.
- [x] Exclude asteroid belts and duplicate embedded/standalone ring records.

### 2.3 Close nested moons

- [x] Detect moons of moons only when closeness or another relationship makes
  them notable; nesting by itself should not create routine alerts.
- [x] Measure the relationship to the immediate parent first.
- [x] Consider ringed immediate parents and nested systems with a nearby ringed
  ancestor. The latter requires accounting for both levels of orbital motion;
  ancestry alone cannot establish proximity.

### 2.4 High inclination near ringed parents

- [x] Combine the close-parent/ring screening with unusually inclined orbits.
- [x] Preserve the reported inclination and document its reference frame.
  Do not describe it as a verified angle to the rings unless established.
- [x] Distinguish near-polar and retrograde motion. A near-180-degree orbit
  can be retrograde while still nearly coplanar, so it must not automatically
  receive the same scenic interpretation as a near-90-degree orbit.
- [x] Report factual orbital orientation without promising ring visibility
  from a surface viewpoint.

### 2.5 Possible green gas giants

- [x] Research and pin a dated, reproducible community criterion set before
  implementing this rule. Verify required fields against retained scans.
- [x] Investigate planet class, full-precision surface temperature, and density
  derived from mass and radius where the model requires it.
- [x] Preserve raw precision; avoid broad rounded-temperature windows that
  would turn ordinary giants into candidates.
- [x] Use sourced positive examples and similar negative examples to assess
  selectivity and numeric tolerance; document unverified cross-version coverage.
- [x] Return "possible green gas giant" with relevant scan data. Keep criterion
  versions in developer documentation. A scan-based candidate needs visual
  confirmation; do not infer color
  simply from life-bearing classification or a broad temperature range.

## 3. Additional candidates to consider

These extend the initial interests and are now enabled with the defaults above.

| Candidate | Why investigate it | Evidence or limitation |
| --- | --- | --- |
| Close ringed binaries | Nearby ringed companion | Existing binary detector identifies each ringed member |
| Very short orbital periods | Fast moons and planets | Positive period in hours; combined body-property entry |
| Extreme eccentricity | Large proximity changes | Valid bound orbit, eccentricity and periapsis/apoapsis |
| Bodies very close to stars | Large apparent star | Direct scanned stellar parent and valid body/star radii; periapsis-based selection |
| Close stellar pairs | Compact stellar binaries | Both stellar scans; same binary compatibility and geometry checks |
| Unusual ring scale with nearby viewpoints | Large rings near a moon | Ring width/parent-relative size attached to matching moon findings |
| Ringed landable bodies or terrestrial worlds | Distinctive destination | Valid actual rings and explicit landability or supported terrestrial class |
| Rare body types in unusual relationships | Earth-like or helium/helium-rich moons | Recorded type and direct planetary parent; rare types also labelled in close findings |
| Extreme landable worlds | Small/large size, high gravity, cold/hot temperature | Explicit landability and the documented limits |
| Unusual spin/orbit relationships | Rapid spin, inverted orientation, slow rotation relative to year | Absolute period, spin/orbit ratio, axial tilt in radians; recorded tidal lock retained |
| Rich combinations | Landable nested moon, rings, inclination and biology | Recorded data combined in relationship findings |

Rotation periods are seconds and axial tilt is radians. Negative rotation periods
are preserved literally, not alone interpreted as retrograde motion. Axial tilt
establishes retrograde orientation. Ordinary retrograde tilt is common, so report
it on another notable spin finding or select an especially inverted spin.

Potential transits, eclipses, ring crossings, and apparent collisions remain
research topics. They require stronger three-dimensional geometry and, for
timing, orbital phase/epoch handling. Overlapping radial ranges alone cannot
confirm these phenomena. Terrain features, colors, and visible ring density
also require evidence beyond ordinary numeric scan fields.

## 4. Output and integration

- Preserve `find_curiosities(system_map) -> list[str]` and the ordered
  `CURIOSITY_RULES` registry. Rules remain independent and do not mutate input.
- Keep detection in `curiosities.py`; the summary renderer only displays results.
- Sort bodies/pairs consistently by stable IDs within each detector and report
  each pair once. Combine overlapping findings when they otherwise repeat the
  same information, while retaining distinct measurements.
- Each string should name the bodies, state the curiosity, and report factual
  scan data or labelled calculated values with units. Include periapsis and
  apoapsis where available. Do not include selection thresholds, criteria,
  threshold-duration commentary, or explanatory disclaimers such as "not proof
  of collision". Keep formulas, criteria, and model limitations in developer
  documentation. Use precise labels such as "calculated", "radial", or
  "possible green gas giant" to describe what the data represents.
- Favor landable viewpoints, but retain exceptional non-landable relationships.
- Existing summary retrieval already reruns detectors for saved partial and completed maps;
  use this path so new rules can apply to old systems without raw-journal replay.
- A completed FSS event does not guarantee every required scan field is present.
  Skip unsupported findings rather than treating missing evidence as absence.

## 5. Delivery and completion criteria

The initial families and additional categories are delivered. Future additions
should follow the same field, geometry, output and validation requirements.

Completed delivery checks:

- [x] Document required fields, units, formulas, thresholds, and limitations.
- [x] Include meaningful positive, negative, and threshold-boundary fixtures.
- [x] Cover incomplete scans, missing parents, barycentres, nesting, eccentric
  orbits, malformed values, duplicate pairs/rings, and stable output as relevant.
- [x] Verify input immutability and summary refresh for a saved completed system.
- [x] Evaluate alert volume on sanitized examples before choosing defaults.
- [x] Record enabled rule status here and document any changed output semantics.

## Research references

Consult these when implementing; EDGPT thresholds are deliberate local choices,
not automatic copies of other tools' defaults.

- [Frontier Journal Manual v32](https://hosting.zaonce.net/community/journal/v32/Journal_Manual-v32.pdf): verify scan fields, orbital units, and reference conventions against the applicable journal version.
- [Elite Observatory](https://github.com/Xjph/ObservatoryCore): an existing journal-processing tool and implementation reference.
- [EDDI exploration criteria discussion](https://github.com/EDCD/EDDI/issues/1490): prior candidate collection, including wide rings and links to Observatory rules.
- [edGGG research](https://ed-ggg.github.io/edggg/about/index.html) and [temperature/density model](https://ed-ggg.github.io/edggg/densitydemo.html): community GGG hypotheses and candidate criteria; validate and version any adopted model.
