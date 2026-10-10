from copy import deepcopy
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
