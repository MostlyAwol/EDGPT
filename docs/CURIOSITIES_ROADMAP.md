# Curiosities roadmap

Created 2026-10-08. Updated 2026-10-10: close binary pairs and close moons
of ringed immediate parents are enabled. Remaining families are planning items.

## Purpose

Develop `bin/curiosities.py` into a detector for unusual Elite Dangerous
systems worth investigating or visiting. Favor notable relationships and
geometry, with measurements explaining why a body stands out. Ordinary body
classifications already belong in the system overview.

This roadmap owns curiosity planning separately from the main EDGPT roadmap.
The initial priorities below come from the requested exploration interests;
later candidates are proposals, not commitments. The requested initial proximity
threshold is strictly less than 2000 km; broader thresholds still need calibration.

## Enabled rules and tuning

Change `CLOSE_DISTANCE_KM = 2000.0` near the top of `bin/curiosities.py` to
adjust all enabled proximity checks, then restart the helper processes.
Exactly 2000 km does not match. The threshold uses unrounded distances;
displayed distances are rounded to three decimal places in km.
Saved completed system summaries rerun these rules when retrieved.

Geometry uses retained `Scan` fields. `Radius`, `SemiMajorAxis`, `InnerRad`
and `OuterRad` are handled in metres, with output divided by 1000 for km.
`Eccentricity` is dimensionless; `OrbitalPeriod` is seconds, and orbital
inclination/periapsis are degrees. Frontier's v32 manual section 6.3 describes
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
the maximum determines whether closeness persists throughout the orbit.
Each pair is reported once, with both names, recorded landability and ring
status. Negative calculated clearance is reported as a signed value.
Scans do not verify orbital phase or full orientation: these are model-based
estimates, not measured current separation. Multi-body and incomplete binaries
are skipped. Size-relative selection remains deferred.

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
ring crossing, or proof of shepherding. Inclination alerts remain deferred.

Validation uses synthetic positive/negative/boundary examples in
`tests/test_curiosities.py` and a saved-map refresh test in
`tests/test_system_summary.py`, including eccentricity, invalid/missing fields,
root sentinels, inferred barycentres, nesting, duplicate rings, stable ordering
and input immutability. Real-system alert-volume calibration remains open;
2000 km is the user-selected initial default.

## 1. Shared relationship and geometry helpers

- [ ] Read scans from `nodes[*].event_data.Scan` and resolve bodies using IDs,
  `parent_id`, and `parent_chain`; do not infer relationships from body names.
- [ ] Distinguish direct parents, shared barycentres, and distant ancestors.
  Preserve nested moon relationships and handle missing/inferred parent nodes.
- [ ] Establish units from Frontier's journal documentation. Keep calculations
  in journal units and explicitly convert displayed distances to km and periods
  to hours or days.
- [ ] Validate required numbers, rejecting non-finite or physically invalid
  values. Missing values must not become zeros or false matches.
- [ ] Support orbital distance ranges from semimajor axis and eccentricity:
  periapsis `a * (1 - e)`, apoapsis `a * (1 + e)` for supported bound orbits.
- [ ] For verified two-body binary orbits around a common barycentre, establish
  when the component semimajor axes can be combined into a relative orbit.
  Do not subtract arbitrary sibling orbital radii to claim a close pair.
- [ ] Distinguish nominal separation, predicted closest approach, conservative
  bounds, and current separation. Orbital elements alone must not be presented
  as a measurement of where bodies are now.
- [ ] Define ring geometry limitations: radial proximity is a screening metric,
  not a three-dimensional distance to ring material. Orbital inclination may
  use a different reference plane from a parent's equator/rings.

## 2. Initial detector priorities

### 2.1 Close pairs

- [x] Detect unusually close binary planets and binary moons under the documented model.
- [x] Use surface-to-surface separation, subtracting both body radii from a
  justified centre-to-centre separation; include the distance basis in output.
- [x] Report both body names and landability; identify pairs with a landable
  viewpoint and pairs where one or both bodies have rings.
- [ ] Compare absolute clearance and separation relative to body size so large
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

- [ ] Detect moons of moons only when closeness or another relationship makes
  them notable; nesting by itself should not create routine alerts.
- [ ] Measure the relationship to the immediate parent first.
- [ ] Consider ringed immediate parents and nested systems with a nearby ringed
  ancestor. The latter requires accounting for both levels of orbital motion;
  ancestry alone cannot establish proximity.

### 2.4 High inclination near ringed parents

- [ ] Combine the close-parent/ring screening with unusually inclined orbits.
- [ ] Preserve the reported inclination and document its reference frame.
  Do not describe it as a verified angle to the rings unless established.
- [ ] Distinguish near-polar and retrograde motion. A near-180-degree orbit
  can be retrograde while still nearly coplanar, so it must not automatically
  receive the same scenic interpretation as a near-90-degree orbit.
- [ ] Describe promising viewpoints as candidates; do not promise ring
  visibility from the surface without sufficient orientation information.

### 2.5 Possible green gas giants

- [ ] Research and pin a dated, reproducible community criterion set before
  implementing this rule. Verify required fields against retained scans.
- [ ] Investigate planet class, full-precision surface temperature, and density
  derived from mass and radius where the model requires it.
- [ ] Preserve raw precision; avoid broad rounded-temperature windows that
  would turn ordinary giants into candidates.
- [ ] Use known positive examples and similar negative examples to assess
  selectivity, numeric tolerance, and any game-version differences.
- [ ] Return "possible green gas giant" with relevant scan data. Keep criterion
  versions in developer documentation. A scan-based candidate needs visual
  confirmation; do not infer color
  simply from life-bearing classification or a broad temperature range.

## 3. Additional candidates to consider

These extend the initial interests. Each needs a supported definition and a
useful threshold before promotion into an enabled detector.

| Candidate | Why investigate it | Evidence or limitation |
| --- | --- | --- |
| Close ringed binaries | A nearby ringed companion could provide an unusual view | Extend close-pair geometry; identify which component has rings |
| Very short orbital periods | Fast moons and binaries may show noticeable motion | Orbital period plus relationship and separation; avoid duplicate alerts |
| Extreme eccentricity | Large changes in parent proximity over an orbit | Eccentricity and periapsis/apoapsis; no claim about current position |
| Bodies very close to stars | A large apparent star could make a distinctive destination | Validated orbit, stellar radius, body radius, and landability |
| Close stellar pairs | Compact binaries involving dwarfs or other unusual stars | Shared barycentre and justified relative orbit; validate stellar scans |
| Unusual ring scale with nearby viewpoints | Wide rings or multiple bands become more interesting with a nearby moon | Ring radii and body relationships; prioritize combined geometry |
| Ringed landable bodies or ringed terrestrial worlds | Potentially distinctive destinations beyond ringed gas giants | Recorded ring data, planet class, and explicit landability |
| Rare body types in unusual relationships | For example, a helium-rich giant or Earth-like moon in a close pair | Verify taxonomy and prevalence; avoid flagging common classes alone |
| Extreme landable worlds | Very small/large radius, high gravity, or extreme temperatures | Scan values and calibrated limits; describe measured properties |
| Unusual spin/orbit relationships | Rapid rotation, retrograde rotation, or unusual day/year ratios | Verify signed period conventions and tidal-lock fields first |
| Rich combinations | A landable nested moon, close ringed parent, and biological signals | Combine recorded findings; no guessed species or scenic guarantees |

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
- Existing summary retrieval already reruns detectors for saved completed maps;
  use this path so new rules can apply to old systems without raw-journal replay.
- A completed FSS event does not guarantee every required scan field is present.
  Skip unsupported findings rather than treating missing evidence as absence.

## 5. Delivery and completion criteria

Implement one detector family at a time: helpers and close pairs first, then
ring proximity, nested moons, combined inclination, and researched GGG
candidates. Additional candidates can follow once the initial rules are useful.

For each enabled family:

- [ ] Document required fields, units, formulas, thresholds, and limitations.
- [ ] Include meaningful positive, negative, and threshold-boundary fixtures.
- [ ] Cover incomplete scans, missing parents, barycentres, nesting, eccentric
  orbits, malformed values, duplicate pairs/rings, and stable output as relevant.
- [ ] Verify input immutability and summary refresh for a saved completed system.
- [ ] Evaluate alert volume on sanitized examples before choosing defaults.
- [ ] Record enabled rule status here and document any changed output semantics.

## Research references

Consult these when implementing; EDGPT thresholds are deliberate local choices,
not automatic copies of other tools' defaults.

- [Frontier Journal Manual v32](https://hosting.zaonce.net/community/journal/v32/Journal_Manual-v32.pdf): verify scan fields, orbital units, and reference conventions against the applicable journal version.
- [Elite Observatory](https://github.com/Xjph/ObservatoryCore): an existing journal-processing tool and implementation reference.
- [EDDI exploration criteria discussion](https://github.com/EDCD/EDDI/issues/1490): prior candidate collection, including wide rings and links to Observatory rules.
- [edGGG research](https://ed-ggg.github.io/edggg/about/index.html) and [temperature/density model](https://ed-ggg.github.io/edggg/densitydemo.html): community GGG hypotheses and candidate criteria; validate and version any adopted model.
