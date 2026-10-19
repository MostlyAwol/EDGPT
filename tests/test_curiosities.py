from copy import deepcopy
from pathlib import Path
import json
import math
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
import curiosities
from system_map import apply_event, new_system_map
from system_summary import build_system_summary


def planet(body_id, parents, **fields):
    return {"event": "Scan", "BodyID": body_id, "BodyName": f"Test {body_id}",
            "Parents": parents, "PlanetClass": "Rocky body", "Radius": 500_000,
            "SemiMajorAxis": 1_000_000, "Eccentricity": 0,
            "OrbitalPeriod": 1000, "OrbitalInclination": 0, "Landable": True,
            **fields}


def model(*events):
    result = new_system_map(123, "Test")
    for event in events:
        apply_event(result, event)
    return result


def binary(clearance=1_999_000, eccentricity=0):
    axis = (1_000_000 + clearance) / (2 * (1 - eccentricity))
    return model(planet(1, [{"Null": 10}], SemiMajorAxis=axis,
                        Eccentricity=eccentricity, Periapsis=0),
                 planet(2, [{"Null": 10}], SemiMajorAxis=axis,
                        Eccentricity=eccentricity, Periapsis=180))


RINGS = [{"Name": "Test 1 A Ring", "InnerRad": 2_000_000, "OuterRad": 3_000_000}]


def ringed(axis=5_499_000, eccentricity=0, **fields):
    return model(planet(1, [{"Star": 0}], Radius=1_000_000, Rings=deepcopy(RINGS)),
                 planet(2, [{"Planet": 1}, {"Star": 0}], SemiMajorAxis=axis,
                        Eccentricity=eccentricity, **fields))


class CuriosityTests(unittest.TestCase):
    def setUp(self):
        # These cases isolate the two original rules from independent new alerts.
        self.enterContext(patch.object(curiosities, "CURIOSITY_RULES",
                                       (curiosities.close_pairs, curiosities.close_moons_of_ringed_parents)))

    def test_binary_threshold_and_editable_setting(self):
        self.assertIn("1,999.000 km", curiosities.find_curiosities(binary())[0])
        for clearance in (2_000_000, 2_001_000):
            self.assertEqual(curiosities.find_curiosities(binary(clearance)), [])
        with patch.object(curiosities, "CLOSE_DISTANCE_KM", 1000):
            self.assertEqual(curiosities.find_curiosities(binary()), [])
        with patch.object(curiosities, "CLOSE_DISTANCE_KM", 2500):
            self.assertEqual(len(curiosities.find_curiosities(binary(2_001_000))), 1)

    def test_eccentric_binary_and_anomaly(self):
        text = curiosities.find_curiosities(binary(eccentricity=0.5))[0]
        self.assertIn("1,999.000 km at periapsis", text)
        self.assertIn("7,997.000 km at apoapsis", text)
        self.assertNotIn("< 2000", text)
        self.assertNotIn("over part of orbit", text)
        text = curiosities.find_curiosities(binary(-1000))[0]
        self.assertIn("calculated surface-to-surface clearance -1.000 km at periapsis", text)
        self.assertNotIn("anomaly", text)
        self.assertNotIn("not proof of collision", text)

    def test_siblings_sentinel_multiple_children(self):
        for parents in ([{"Star": 0}], [{"Planet": 10}], [{"Null": 0}]):
            with self.subTest(parents=parents):
                self.assertEqual(curiosities.find_curiosities(model(planet(1, parents), planet(2, parents))), [])
        value = binary()
        apply_event(value, planet(3, [{"Null": 10}]))
        self.assertEqual(curiosities.find_curiosities(value), [])

    def test_binary_missing_or_incompatible_fields(self):
        for field, replacement in (("Radius", None), ("SemiMajorAxis", float("inf")),
                                   ("Eccentricity", -0.1), ("Eccentricity", 1),
                                   ("OrbitalPeriod", 2000), ("Radius", True),
                                   ("OrbitalInclination", 10), ("PlanetClass", None)):
            with self.subTest(field=field, replacement=replacement):
                value = binary()
                value["nodes"]["2"]["event_data"]["Scan"][field] = replacement
                self.assertEqual(curiosities.find_curiosities(value), [])
        value = binary(eccentricity=0.5)
        value["nodes"]["2"]["event_data"]["Scan"]["Periapsis"] = 0
        self.assertEqual(curiosities.find_curiosities(value), [])

    def test_ring_surface_to_edge_threshold(self):
        text = curiosities.find_curiosities(ringed())[0]
        self.assertIn("outer edge: calculated radial surface-to-edge clearance 1,999.000 km minimum to 1,999.000 km maximum", text)
        self.assertIn("outside outermost ring throughout orbit", text)
        for axis in (5_500_000, 5_501_000):
            self.assertEqual(curiosities.find_curiosities(ringed(axis)), [])
        with patch.object(curiosities, "CLOSE_DISTANCE_KM", 1000):
            self.assertEqual(curiosities.find_curiosities(ringed()), [])

    def test_ring_parent_surface_and_eccentricity(self):
        text = curiosities.find_curiosities(ringed(3_499_000))[0]
        self.assertIn("surface-to-surface clearance 1,999.000 km", text)
        self.assertIn("radial ranges overlap", text)
        text = curiosities.find_curiosities(ringed(8_000_000, 0.5))[0]
        self.assertIn("clearance 500.000 km minimum to 8,500.000 km maximum", text)
        self.assertIn("orbital periapsis 4,000.000 km, apoapsis 12,000.000 km", text)
        self.assertNotIn("over part of orbit", text)
        self.assertNotIn("not a 3D distance", text)

    def test_ring_gaps_inside_and_nested_parent(self):
        value = ringed(8_000_000)
        value["nodes"]["1"]["event_data"]["Scan"]["Rings"].append(
            {"Name": "Test 1 B Ring", "InnerRad": 10_000_000, "OuterRad": 11_000_000})
        self.assertIn("between ring bands throughout orbit", curiosities.find_curiosities(value)[0])
        value = ringed(1_800_000, Radius=100_000)
        self.assertIn("inside innermost ring throughout orbit", curiosities.find_curiosities(value)[0])
        apply_event(value, planet(1, [{"Planet": 20}, {"Star": 0}], Radius=1_000_000, Rings=RINGS))
        self.assertEqual(len(curiosities.find_curiosities(value)), 1)
        value["nodes"].pop("1")
        self.assertEqual(curiosities.find_curiosities(value), [])

    def test_ring_duplicates_belts_and_invalid_fields(self):
        value = ringed()
        scan = value["nodes"]["1"]["event_data"]["Scan"]
        before = curiosities.find_curiosities(value)
        scan["Rings"] *= 2
        scan["Rings"].append({"Name": "Test Belt", "InnerRad": 5_000_000, "OuterRad": 6_000_000})
        apply_event(value, {"event": "Scan", "BodyID": 5, "BodyName": "Test 1 A Ring", "RingClass": "Rocky"})
        self.assertEqual(curiosities.find_curiosities(value), before)
        for field, replacement in (("Radius", 0), ("Eccentricity", None),
                                   ("SemiMajorAxis", float("nan")), ("Radius", "500000")):
            bad = ringed()
            bad["nodes"]["2"]["event_data"]["Scan"][field] = replacement
            self.assertEqual(curiosities.find_curiosities(bad), [])
        scan["Rings"] = [{"Name": "Bad Ring", "InnerRad": 4, "OuterRad": 3}]
        self.assertEqual(curiosities.find_curiosities(value), [])

    def test_determinism_immutability_and_summary(self):
        for value in (ringed(), binary()):
            value["system_events"]["FSSAllBodiesFound"] = {"event": "FSSAllBodiesFound"}
            original = deepcopy(value)
            findings = curiosities.find_curiosities(value)
            self.assertEqual(value, original)
            self.assertEqual(build_system_summary(value)["curiosities"], findings)
            value["nodes"] = dict(reversed(list(value["nodes"].items())))
            self.assertEqual(curiosities.find_curiosities(value), findings)


class ShepherdMoonTests(unittest.TestCase):
    def system(self, axis=10_000_000, eccentricity=0, **fields):
        value = ringed(axis, eccentricity, OrbitalPeriod=10000, Landable=False, **fields)
        value["nodes"]["1"]["event_data"]["Scan"]["Rings"] = [
            {"Name": "Test 1 A Ring", "InnerRad": 20_000_000, "OuterRad": 30_000_000},
            {"Name": "Test 1 B Ring", "InnerRad": 60_000_000, "OuterRad": 70_000_000}]
        return value

    def test_inside_ring_without_proximity_and_summary(self):
        value = self.system(eccentricity=0.1)
        original = deepcopy(value)
        findings = curiosities.close_moons_of_ringed_parents(value)
        self.assertEqual(len(findings), 1)
        text = findings[0]
        self.assertTrue(text.startswith("Shepherd moon candidate"))
        self.assertIn("Test 2 (not landable)", text)
        self.assertIn("between parent surface and Test 1 A Ring inner edge", text)
        self.assertIn("7,500.000 km minimum to 9,500.000 km maximum", text)
        self.assertIn("8,500.000 km minimum to 10,500.000 km maximum", text)
        self.assertIn("inside innermost ring throughout orbit", text)
        self.assertEqual(build_system_summary(value)["curiosities"], curiosities.find_curiosities(value))
        self.assertIn(text, curiosities.find_curiosities(value))
        self.assertEqual(value, original)

    def test_between_rings_without_proximity_and_stable_order(self):
        value = self.system(45_000_000)
        findings = curiosities.close_moons_of_ringed_parents(value)
        self.assertEqual(len(findings), 1)
        self.assertIn("between Test 1 A Ring outer edge and Test 1 B Ring inner edge", findings[0])
        self.assertIn("between ring bands throughout orbit", findings[0])
        scan = value["nodes"]["1"]["event_data"]["Scan"]
        scan["Rings"] = list(reversed(scan["Rings"] * 2))
        value["nodes"] = dict(reversed(list(value["nodes"].items())))
        self.assertEqual(curiosities.close_moons_of_ringed_parents(value), findings)

    def test_boundaries_crossing_and_outside_are_not_shepherd_candidates(self):
        for axis, eccentricity in ((1_500_000, 0), (19_500_000, 0),
                                    (30_500_000, 0), (59_500_000, 0),
                                    (25_000_000, 0), (80_000_000, 0),
                                    (15_000_000, 0.4), (45_000_000, 0.4)):
            with self.subTest(axis=axis, eccentricity=eccentricity):
                findings = curiosities.close_moons_of_ringed_parents(
                    self.system(axis, eccentricity=eccentricity))
                self.assertNotIn("shepherd", " ".join(findings).lower())

    def test_overlapping_bands_do_not_create_false_gap(self):
        value = self.system(45_000_000)
        value["nodes"]["1"]["event_data"]["Scan"]["Rings"].append(
            {"Name": "Enclosing Ring", "InnerRad": 25_000_000, "OuterRad": 65_000_000})
        self.assertEqual(curiosities.close_moons_of_ringed_parents(value), [])

    def test_close_findings_combine_and_nested_parent_qualifies(self):
        value = ringed(1_800_000, Radius=100_000)
        findings = curiosities.close_moons_of_ringed_parents(value)
        self.assertEqual(len(findings), 1)
        self.assertIn("shepherd moon candidate", findings[0])
        self.assertIn("Close moon of ringed parent", findings[0])
        value = self.system()
        apply_event(value, planet(1, [{"Planet": 20}, {"Star": 0}],
                                  Radius=1_000_000,
                                  Rings=value["nodes"]["1"]["event_data"]["Scan"]["Rings"]))
        apply_event(value, planet(20, [{"Star": 0}]))
        self.assertIn("Nested shepherd moon candidate", curiosities.close_moons_of_ringed_parents(value)[0])
        value["nodes"].pop("1")
        self.assertEqual(curiosities.close_moons_of_ringed_parents(value), [])

    def test_missing_invalid_geometry(self):
        for field, replacement in (("Radius", None), ("Radius", True),
                                   ("SemiMajorAxis", float("inf")), ("Eccentricity", None)):
            value = self.system()
            value["nodes"]["2"]["event_data"]["Scan"][field] = replacement
            self.assertEqual(curiosities.close_moons_of_ringed_parents(value), [])
        value = self.system()
        value["nodes"]["1"]["event_data"]["Scan"].pop("Radius")
        self.assertEqual(curiosities.close_moons_of_ringed_parents(value), [])
        # A gap between two rings does not require the parent's surface radius.
        value["nodes"]["2"]["event_data"]["Scan"]["SemiMajorAxis"] = 45_000_000
        self.assertEqual(len(curiosities.close_moons_of_ringed_parents(value)), 1)


class ExtendedCuriosityTests(unittest.TestCase):
    def nested(self, axis=2_499_000, **fields):
        return model(planet(1, [{"Star": 0}], SemiMajorAxis=100_000_000),
                     planet(2, [{"Planet": 1}, {"Star": 0}], SemiMajorAxis=10_000_000),
                     planet(3, [{"Planet": 2}, {"Planet": 1}, {"Star": 0}],
                            SemiMajorAxis=axis, **fields))

    def test_size_relative_binary_selection_and_boundary(self):
        value = binary(9_999_000)
        for node in value["nodes"].values():
            scan = node.get("event_data", {}).get("Scan")
            if scan:
                scan.update(Radius=5_000_000, SemiMajorAxis=9_999_500)
        text = curiosities.close_pairs(value)[0]
        self.assertIn("9,999.000 km at periapsis", text)
        self.assertIn("1.000 combined radii", text)
        for node in value["nodes"].values():
            scan = node.get("event_data", {}).get("Scan")
            if scan:
                scan["SemiMajorAxis"] = 10_000_000
        self.assertEqual(curiosities.close_pairs(value), [])
        with patch.object(curiosities, "CLOSE_PAIR_GAP_RADII", 2):
            self.assertEqual(len(curiosities.close_pairs(value)), 1)

    def test_nested_immediate_clearance_boundaries_and_missing_parents(self):
        text = curiosities.close_nested_moons(self.nested())[0]
        self.assertIn("Close nested moon", text)
        self.assertIn("1,499.000 km at periapsis", text)
        self.assertIn("orbital periapsis 2,499.000 km", text)
        self.assertEqual(curiosities.close_nested_moons(self.nested(3_000_000)), [])
        self.assertEqual(curiosities.close_nested_moons(self.nested(3_001_000)), [])
        value = self.nested()
        value["nodes"].pop("2")
        self.assertEqual(curiosities.close_nested_moons(value), [])
        self.assertEqual(curiosities.close_nested_moons(ringed()), [])

    def test_nested_ringed_parent_not_duplicated(self):
        value = self.nested()
        value["nodes"]["2"]["event_data"]["Scan"]["Rings"] = RINGS
        self.assertIn("Close nested moon of ringed parent", curiosities.close_moons_of_ringed_parents(value)[0])
        self.assertEqual(curiosities.close_nested_moons(value), [])

    def test_nested_ancestor_uses_both_orbits_and_conservative_bounds(self):
        value = self.nested(500_000, Radius=100_000)
        value["nodes"]["1"]["event_data"]["Scan"]["Rings"] = [
            {"Name": "Ancestor A Ring", "InnerRad": 9_000_000, "OuterRad": 10_000_000}]
        text = curiosities.close_nested_moons(value)[0]
        self.assertIn("Ancestor A Ring", text)
        self.assertIn("ancestor centre-distance bounds 9,500.000 km to 10,500.000 km", text)
        value["nodes"]["3"]["event_data"]["Scan"]["SemiMajorAxis"] = 5_000_000
        # Overlapping radial ranges alone must not produce an ancestor alert.
        self.assertEqual(curiosities.close_nested_moons(value), [])
        value["nodes"]["2"]["event_data"]["Scan"].pop("Eccentricity")
        self.assertEqual(curiosities.close_nested_moons(value), [])

    def test_inclination_polar_retrograde_and_coplanar(self):
        for inclination, expected in ((15, "Highly inclined"), (90, "near-polar"),
                                      (-90, "near-polar"), (120, "retrograde"), (165, "retrograde")):
            with self.subTest(inclination=inclination):
                findings = curiosities.close_moons_of_ringed_parents(ringed(OrbitalInclination=inclination))
                self.assertEqual(len(findings), 1)
                self.assertIn(expected, findings[0])
                self.assertIn(f"orbital inclination {inclination:.3f} degrees", findings[0])
        for inclination in (14.999, 180, 179, None, True, float("nan"), 181):
            with self.subTest(inclination=inclination):
                text = curiosities.close_moons_of_ringed_parents(ringed(OrbitalInclination=inclination))[0]
                self.assertNotIn("Highly inclined", text)
        self.assertEqual(curiosities.close_moons_of_ringed_parents(ringed(100_000_000, OrbitalInclination=90)), [])

    def test_ggg_published_examples_and_adjacent_negatives(self):
        cases = json.loads(Path(__file__).with_name("fixtures").joinpath("curiosity_ggg_examples.json").read_text())
        for case in cases:
            with self.subTest(name=case["name"]):
                scan = planet(1, [{"Star": 0}], **case["scan"], BodyName=case["name"])
                findings = curiosities.possible_green_gas_giants(model(scan))
                self.assertEqual(bool(findings), case["candidate"])
                if findings:
                    self.assertIn("Possible green gas giant", findings[0])
                    self.assertIn(f"{case['scan']['SurfaceTemperature']:.6f} K", findings[0])

    def test_ggg_temperature_and_density_boundaries(self):
        for temperature, density, expected in ((130, 5245, True), (130, 597, False),
                                                (130, 1620, False), (130.000015, 2078.1, True),
                                                (130.000016, 5245, False)):
            radius = 60_000_000
            mass = density * (4 / 3 * math.pi * radius ** 3) / curiosities.EARTH_MASS_KG
            value = model(planet(1, [{"Star": 0}], PlanetClass="Class I gas giant",
                                 Radius=radius, MassEM=mass, SurfaceTemperature=temperature))
            self.assertEqual(bool(curiosities.possible_green_gas_giants(value)), expected)
        for temperature in (176.666641, 176.666702):
            value = model(planet(1, [{"Star": 0}], PlanetClass="Gas giant with water-based life",
                                 MassEM=200, Radius=60_000_000, SurfaceTemperature=temperature))
            self.assertEqual(len(curiosities.possible_green_gas_giants(value)), 1)
        for cls, temperature in (("Class III gas giant", 640), ("Class IV gas giant", 1150),
                                 ("Water giant", 242.000015), ("Helium-rich gas giant", 210)):
            self.assertEqual(len(curiosities.possible_green_gas_giants(model(
                planet(1, [{"Star": 0}], PlanetClass=cls, SurfaceTemperature=temperature)))), 1)
        for cls, temperature in (("Class II gas giant", 640), ("Rocky body", 158),
                                 ("Class III gas giant", 640.000001)):
            self.assertEqual(curiosities.possible_green_gas_giants(model(
                planet(1, [{"Star": 0}], PlanetClass=cls, SurfaceTemperature=temperature))), [])
        value = model(planet(1, [{"Star": 0}], PlanetClass="Gas giant with water-based life", SurfaceTemperature=158))
        self.assertEqual(curiosities.possible_green_gas_giants(value), [])
        for field, replacement in (("SurfaceTemperature", True), ("MassEM", -1),
                                   ("Radius", float("inf")), ("SurfaceTemperature", "158")):
            bad = model(planet(1, [{"Star": 0}], PlanetClass="Gas giant with water-based life",
                               SurfaceTemperature=158, MassEM=200, Radius=60_000_000))
            bad["nodes"]["1"]["event_data"]["Scan"][field] = replacement
            self.assertEqual(curiosities.possible_green_gas_giants(bad), [])

    def test_journal_class_aliases_and_invalid_class(self):
        for cls, temperature in (("Gas giant with water based life", 158),
                                 ("Gas giant with ammonia based life", 130),
                                 ("Sudarsky class III gas giant", 640),
                                 ("Helium rich gas giant", 158),
                                 ("Water giant with life", 158)):
            value = model(planet(1, [{"Star": 0}], PlanetClass=cls, SurfaceTemperature=temperature,
                                 MassEM=1000, Radius=60_000_000))
            self.assertEqual(len(curiosities.possible_green_gas_giants(value)), 1)
        value = model(planet(1, [{"Star": 0}], PlanetClass=["Class III gas giant"], SurfaceTemperature=640))
        self.assertEqual(curiosities.possible_green_gas_giants(value), [])
        self.assertEqual(curiosities.unusual_body_properties(value), [])

    def test_axial_tilt_alone_does_not_select_a_body(self):
        for tilt in (120, 174.999, 175, -175, 175.796, 180, 181):
            value = model(planet(1, [{"Star": 0}], OrbitalPeriod=10000,
                                 RotationPeriod=10000, AxialTilt=math.radians(tilt)))
            self.assertEqual(curiosities.unusual_body_properties(value), [])

    def test_reported_non_landable_examples_do_not_select_bodies(self):
        value = model(
            planet(1, [{"Star": 0}], BodyName="Umbaiss GR-T d4-141 ABC 2",
                   Landable=False, OrbitalPeriod=1_000_000, RotationPeriod=113045.598546,
                   AxialTilt=math.radians(175.796), TidalLock=False),
            planet(2, [{"Star": 0}], BodyName="Umbaiss GR-T d4-146 D 7",
                   Landable=False, OrbitalPeriod=1_000_000, PlanetClass="Icy body",
                   Rings=[{"Name": "Umbaiss GR-T d4-146 D 7 A Ring",
                           "InnerRad": 18_824_000, "OuterRad": 45_433_000}]),
            planet(3, [{"Star": 0}], BodyName="Umbaiss GR-T d4-154 4",
                   Landable=False, OrbitalPeriod=1_000_000, PlanetClass="High metal content body",
                   Rings=[{"Name": "Umbaiss GR-T d4-154 4 A Ring",
                           "InnerRad": 17_638_000, "OuterRad": 58_007_000}]))
        self.assertEqual(curiosities.find_curiosities(value), [])
        self.assertNotIn("Curiosities", build_system_summary(value)["summary_text"])

    def test_derived_ratio_overflow_is_not_reported_as_data(self):
        value = model(planet(1, [{"Star": 0}], OrbitalPeriod=1e-308, RotationPeriod=1e308))
        text = curiosities.unusual_body_properties(value)[0]
        self.assertNotIn("rotation/orbit", text)
        self.assertNotIn("inf", text)
        value = binary()
        for body_id in (1, 2):
            value["nodes"][str(body_id)]["event_data"]["Scan"].update(Radius=1e-308, SemiMajorAxis=1000)
        text = curiosities.close_pairs(value)[0]
        self.assertNotIn("combined radii", text)
        self.assertNotIn("inf", text)

    def test_missing_cycles_and_non_finite_nested_geometry(self):
        for field, replacement in (("SemiMajorAxis", float("inf")), ("Radius", True),
                                   ("Eccentricity", None)):
            value = self.nested()
            value["nodes"]["3"]["event_data"]["Scan"][field] = replacement
            self.assertEqual(curiosities.close_nested_moons(value), [])
        value = self.nested()
        value["nodes"]["2"].update(parent_id=3, parent_chain=[{"kind": "Planet", "id": 3}])
        self.assertEqual(curiosities.close_nested_moons(value), [])

    def test_close_star_planets_and_stellar_binaries(self):
        star = {"event": "Scan", "BodyID": 0, "BodyName": "Test star", "StarType": "K", "Radius": 100_000_000}
        for axis, expected in ((500_000_000, True), (500_000_001, False)):
            value = model(star, planet(1, [{"Star": 0}], SemiMajorAxis=axis))
            findings = curiosities.close_stellar_relationships(value)
            self.assertEqual(bool(findings), expected)
            if findings:
                self.assertIn("399,500.000 km at periapsis", findings[0])
        value = binary()
        for body_id in (1, 2):
            scan = value["nodes"][str(body_id)]["event_data"]["Scan"]
            scan.pop("PlanetClass")
            scan["StarType"] = "D"
        self.assertEqual(len(curiosities.close_stellar_relationships(value)), 1)
        self.assertEqual(curiosities.close_pairs(value), [])
        value["nodes"]["2"]["event_data"]["Scan"]["OrbitalPeriod"] = 2000
        self.assertEqual(curiosities.close_stellar_relationships(value), [])

    def test_stellar_binary_clearance_uses_larger_star_radius(self):
        value = binary(1_000_000, eccentricity=0.5)
        for body_id in (1, 2):
            scan = value["nodes"][str(body_id)]["event_data"]["Scan"]
            scan.pop("PlanetClass")
            scan["StarType"] = "K"
        value["nodes"]["2"]["event_data"]["Scan"]["Radius"] = 1_000_000
        text = curiosities.close_stellar_relationships(value)[0]
        self.assertIn("clearance 0.500 at periapsis to 4.500 at apoapsis", text)
        self.assertIn("times the radius of Test 2 (larger star)", text)
        self.assertTrue(text.endswith("closest surface-to-surface clearance 500.000 km."))
        value["nodes"] = dict(reversed(list(value["nodes"].items())))
        self.assertEqual(curiosities.close_stellar_relationships(value), [text])
        # Swapping the radii must use the other star as the same-sized reference.
        value["nodes"]["1"]["event_data"]["Scan"]["Radius"] = 1_000_000
        value["nodes"]["2"]["event_data"]["Scan"]["Radius"] = 500_000
        self.assertIn("times the radius of Test 1 (larger star)",
                      curiosities.close_stellar_relationships(value)[0])

    def test_stellar_binary_clearance_keeps_signed_overlap(self):
        value = binary(-100_000)
        for body_id in (1, 2):
            scan = value["nodes"][str(body_id)]["event_data"]["Scan"]
            scan.pop("PlanetClass")
            scan["StarType"] = "K"
        text = curiosities.close_stellar_relationships(value)[0]
        self.assertIn("clearance -0.200 at periapsis to -0.200 at apoapsis", text)
        self.assertTrue(text.endswith("closest surface-to-surface clearance -100.000 km."))

    def test_short_period_eccentricity_and_thresholds(self):
        value = model(planet(1, [{"Star": 0}], OrbitalPeriod=3600, Eccentricity=0.9))
        text = curiosities.unusual_body_properties(value)[0]
        self.assertIn("short orbital period 1.000 hours", text)
        self.assertIn("eccentricity 0.900000", text)
        self.assertIn("orbital periapsis 100.000 km, apoapsis 1,900.000 km", text)
        for fields in ({"OrbitalPeriod": 3600.001, "Eccentricity": 0.899999},
                       {"OrbitalPeriod": None, "Eccentricity": 1},
                       {"OrbitalPeriod": True, "Eccentricity": float("nan")}):
            self.assertEqual(curiosities.unusual_body_properties(model(planet(1, [{"Star": 0}], **fields))), [])

    def test_large_ring_and_rich_recorded_combination(self):
        value = ringed(1_103_499_000, OrbitalPeriod=10000, OrbitalInclination=90)
        value["nodes"]["1"]["event_data"]["Scan"]["Rings"] = [
            {"Name": "Wide A Ring", "InnerRad": 2_000_000, "OuterRad": 1_101_000_000}]
        for event in ("FSSBodySignals", "SAASignalsFound"):
            apply_event(value, {"event": event, "BodyID": 2, "Signals": [
                {"Type": "$SAA_SignalType_Biological;", "Count": 3}]})
        text = curiosities.close_moons_of_ringed_parents(value)[0]
        self.assertIn("large ring Wide A Ring", text)
        self.assertIn("3 biological signals", text)
        self.assertNotIn("6 biological", text)
        self.assertIn("near-polar orbit", text)
        self.assertEqual(len(curiosities.close_moons_of_ringed_parents(value)), 1)

    def test_ringed_landable_and_rare_moon(self):
        value = ringed(OrbitalPeriod=10000)
        parent_scan = value["nodes"]["1"]["event_data"]["Scan"]
        parent_scan.update(OrbitalPeriod=10000, Landable=True)
        findings = curiosities.unusual_body_properties(value)
        self.assertEqual(len(findings), 1)
        self.assertIn("ringed landable Rocky body", findings[0])
        parent_scan["Landable"] = False
        self.assertEqual(curiosities.unusual_body_properties(value), [])
        self.assertEqual(len(curiosities.close_moons_of_ringed_parents(value)), 1)
        for landability in (None, "true", 1):
            parent_scan["Landable"] = landability
            self.assertEqual(curiosities.unusual_body_properties(value), [])
        parent_scan["PlanetClass"] = "Class I gas giant"
        self.assertEqual(curiosities.unusual_body_properties(value), [])
        value["nodes"]["2"]["event_data"]["Scan"]["PlanetClass"] = "Earthlike body"
        self.assertIn("Earthlike body moon of Test 1", curiosities.unusual_body_properties(value)[0])

    def test_landable_extremes_and_spin_units(self):
        value = model(planet(1, [{"Star": 0}], OrbitalPeriod=10000, Radius=300_000,
                             SurfaceGravity=3 * curiosities.EARTH_GRAVITY, SurfaceTemperature=1500,
                             RotationPeriod=-3600, AxialTilt=math.radians(120), TidalLock=False))
        text = curiosities.unusual_body_properties(value)[0]
        for expected in ("small landable radius 300.000 km", "surface gravity 3.000 g",
                         "surface temperature 1500.000000 K", "rapid rotation period 1.000 hours",
                         "retrograde axial tilt 120.000 degrees", "tidally locked: no"):
            self.assertIn(expected, text)
        scan = value["nodes"]["1"]["event_data"]["Scan"]
        scan.update(Radius=10_000_000, SurfaceTemperature=20, RotationPeriod=100000, AxialTilt=0)
        text = curiosities.unusual_body_properties(value)[0]
        self.assertIn("large landable radius 10,000.000 km", text)
        self.assertIn("rotation/orbit period ratio 10.000", text)
        scan.update(Landable=False, RotationPeriod=None)
        self.assertEqual(curiosities.unusual_body_properties(value), [])
        scan.update(Landable=True, Radius=300001, SurfaceTemperature=20.001,
                    SurfaceGravity=3 * curiosities.EARTH_GRAVITY - .001,
                    RotationPeriod=3600.001, AxialTilt=0)
        self.assertEqual(curiosities.unusual_body_properties(value), [])

    def test_all_rules_stable_pure_and_partial_summary(self):
        value = self.nested(OrbitalInclination=90)
        apply_event(value, planet(4, [{"Star": 0}], PlanetClass="Class III gas giant", SurfaceTemperature=640))
        original = deepcopy(value)
        findings = curiosities.find_curiosities(value)
        self.assertEqual(value, original)
        self.assertEqual(build_system_summary(value)["curiosities"], findings)
        self.assertFalse(build_system_summary(value)["all_bodies_found"])
        value["nodes"] = dict(reversed(list(value["nodes"].items())))
        self.assertEqual(curiosities.find_curiosities(value), findings)
        self.assertEqual(len(findings), len(set(findings)))
        for text in findings:
            for unwanted in ("< 2000", "not proof", "not current", "criterion", "not a 3D"):
                self.assertNotIn(unwanted, text)


if __name__ == "__main__":
    unittest.main()
