import json
import sys
import tempfile
import unittest
from pathlib import Path


BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))

import history_store
import system_map_store
from system_map import apply_event, new_system_map, render_full_map, render_simple_map


ADDRESS = 123456789


def event(event_type, **values):
    return {
        "timestamp": values.pop("timestamp", "2026-01-01T00:00:00Z"),
        "event": event_type,
        "SystemAddress": ADDRESS,
        **values,
    }


class SystemMapRenderingTests(unittest.TestCase):
    def build_binary_map(self):
        model = new_system_map(ADDRESS, "Test System")
        events = [
            event("FSDJump", StarSystem="Test System", Body="Test System A", BodyID=0, BodyType="Star"),
            event("FSSDiscoveryScan", SystemName="Test System", Progress=1.0, BodyCount=5, NonBodyCount=1),
            event("Scan", StarSystem="Test System", BodyName="Test System A", BodyID=0,
                  DistanceFromArrivalLS=0.0, StarType="G"),
            event("Scan", StarSystem="Test System", BodyName="Test System 1", BodyID=3,
                  Parents=[{"Star": 0}], DistanceFromArrivalLS=100.0,
                  PlanetClass="Rocky body"),
            event("ScanBaryCentre", StarSystem="Test System", BodyID=7,
                  SemiMajorAxis=1000.0, OrbitalPeriod=500.0),
            event("Scan", StarSystem="Test System", BodyName="Test System 1 a", BodyID=8,
                  Parents=[{"Null": 7}, {"Planet": 3}, {"Star": 0}],
                  DistanceFromArrivalLS=100.10, PlanetClass="Icy body"),
            event("Scan", StarSystem="Test System", BodyName="Test System 1 b", BodyID=9,
                  Parents=[{"Null": 7}, {"Planet": 3}, {"Star": 0}],
                  DistanceFromArrivalLS=100.20, PlanetClass="Rocky ice body"),
            event("Scan", StarSystem="Test System", BodyName="Test System 2", BodyID=10,
                  Parents=[{"Star": 0}], DistanceFromArrivalLS=400.0,
                  PlanetClass="Sudarsky class I gas giant"),
            event("FSSBodySignals", BodyName="Test System 1 a", BodyID=8,
                  Signals=[{"Type": "$SAA_SignalType_Geological;", "Count": 2}]),
            event("SAAScanComplete", BodyName="Test System 1 a", BodyID=8,
                  ProbesUsed=4, EfficiencyTarget=6),
            event("FSSSignalDiscovered", SignalName="Test Station", SignalType="Station", IsStation=True),
            event("FSSAllBodiesFound", SystemName="Test System", Count=5),
        ]
        for event_id, value in enumerate(events, 1):
            apply_event(model, value, event_id)
        return model

    def test_tree_uses_parent_chain_and_distance_order(self):
        text = render_simple_map(self.build_binary_map())

        self.assertIn("System: Test System [123456789]", text)
        self.assertIn("Test System A [Star: G star; 0 ls]", text)
        self.assertIn("Test System 1 [Planet: Rocky body; 100.00 ls]", text)
        self.assertIn("Barycentre 7 [Barycentre; distance unknown]", text)
        self.assertIn("Test System 1 a [Moon: Icy body; 100.10 ls]", text)
        self.assertLess(text.index("Test System 1 ["), text.index("Test System 2 ["))
        self.assertLess(text.index("Barycentre 7 ["), text.index("Test System 1 a ["))

    def test_full_map_retains_scan_signal_and_saa_details(self):
        text = render_full_map(self.build_binary_map())

        self.assertIn("FSSBodySignals:", text)
        self.assertIn("SAAScanComplete:", text)
        self.assertIn('"SignalName": "Test Station"', text)
        self.assertIn('"PlanetClass": "Icy body"', text)

    def test_revisit_keeps_saved_bodies_without_rescanning(self):
        model = self.build_binary_map()
        apply_event(
            model,
            event(
                "FSDJump",
                timestamp="2026-01-02T00:00:00Z",
                StarSystem="Test System",
                Body="Test System A",
                BodyID=0,
                BodyType="Star",
            ),
            100,
        )
        text = render_simple_map(model)

        self.assertEqual(model["visits"], 2)
        self.assertTrue(model["known_complete"])
        self.assertFalse(model["current_visit_complete"])
        self.assertIn("saved map complete; current revisit not rescanned", text)
        self.assertIn("Test System 1 a", text)

    def test_ring_signal_node_attaches_to_scanned_parent(self):
        model = new_system_map(ADDRESS, "Ring Test")
        apply_event(model, event("FSDJump", StarSystem="Ring Test", Body="Ring Test A", BodyID=0, BodyType="Star"), 1)
        apply_event(
            model,
            event(
                "Scan",
                BodyName="Ring Test 1",
                BodyID=1,
                Parents=[{"Star": 0}],
                DistanceFromArrivalLS=50.0,
                PlanetClass="Icy body",
                Rings=[{"Name": "Ring Test 1 A Ring", "RingClass": "eRingClass_Icy"}],
            ),
            2,
        )
        apply_event(
            model,
            event(
                "SAASignalsFound",
                BodyName="Ring Test 1 A Ring",
                BodyID=2,
                Signals=[{"Type": "Opal", "Count": 1}],
            ),
            3,
        )
        text = render_simple_map(model)

        self.assertLess(text.index("Ring Test 1 ["), text.index("Ring Test 1 A Ring ["))
        self.assertIn("Planetary ring", text)


class SystemMapPersistenceTests(unittest.TestCase):
    def test_schema_upgrade_recovers_previously_skipped_organic_scans(self):
        self.write_events([event("ScanOrganic", Body=27, ScanType="Log", Species_Localised="Tussock")])
        system_map_store.sync_system_maps()
        with system_map_store._connect() as conn:
            old = new_system_map(ADDRESS)
            old["schema_version"] = 2
            system_map_store._save_model(conn, old)
            system_map_store._set_meta(conn, "schema_version", 2)
            conn.commit()
        saved = system_map_store.get_system_map(str(ADDRESS), include_model=True)
        organic = saved["model"]["nodes"]["27"]["event_data"]["ScanOrganic"]
        self.assertEqual(organic[0]["Species_Localised"], "Tussock")
        self.assertEqual(system_map_store.sync_system_maps(), 0)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.journals = self.root / "journals"
        self.data = self.root / "data"
        self.journals.mkdir()
        self.data.mkdir()
        self.journal = self.journals / "Journal.2026-01-01T000000.01.log"

        self.original_history = (history_store.ELITE_DIR, history_store.DATA_DIR, history_store.DB_PATH)
        self.original_maps = (system_map_store.DATA_DIR, system_map_store.MAP_DB_PATH)
        history_store.ELITE_DIR = self.journals
        history_store.DATA_DIR = self.data
        history_store.DB_PATH = self.data / "history.db"
        system_map_store.DATA_DIR = self.data
        system_map_store.MAP_DB_PATH = self.data / "maps.db"

    def tearDown(self):
        history_store.ELITE_DIR, history_store.DATA_DIR, history_store.DB_PATH = self.original_history
        system_map_store.DATA_DIR, system_map_store.MAP_DB_PATH = self.original_maps
        self.temp.cleanup()

    def write_events(self, values, append=False):
        mode = "a" if append else "w"
        with self.journal.open(mode, encoding="utf-8") as stream:
            for value in values:
                stream.write(json.dumps(value) + "\n")

    def test_historical_backfill_and_revisit_persist_maps(self):
        other_address = 987654321
        values = [
            event("FSDJump", StarSystem="Saved System", Body="Saved System A", BodyID=0, BodyType="Star"),
            event("Scan", StarSystem="Saved System", BodyName="Saved System A", BodyID=0,
                  DistanceFromArrivalLS=0.0, StarType="K"),
            event("Scan", StarSystem="Saved System", BodyName="Saved System 1", BodyID=1,
                  Parents=[{"Star": 0}], DistanceFromArrivalLS=20.0, PlanetClass="High metal content body"),
            event("FSSAllBodiesFound", SystemName="Saved System", Count=2),
            {**event("FSDJump", StarSystem="Other System", Body="Other System A", BodyID=0, BodyType="Star"),
             "SystemAddress": other_address, "timestamp": "2026-01-01T01:00:00Z"},
            event("FSDJump", timestamp="2026-01-01T02:00:00Z", StarSystem="Saved System",
                  Body="Saved System A", BodyID=0, BodyType="Star"),
        ]
        self.write_events(values)

        processed = system_map_store.sync_system_maps()
        saved = system_map_store.get_current_system_map(include_full=True)
        listing = system_map_store.list_system_maps()

        self.assertEqual(processed, len(values))
        self.assertEqual(len(listing), 2)
        self.assertEqual(saved["visits"], 2)
        self.assertTrue(saved["known_complete"])
        self.assertFalse(saved["current_visit_complete"])
        self.assertIn("Saved System 1", saved["simple_text"])
        self.assertIn('"PlanetClass": "High metal content body"', saved["full_text"])

        self.write_events(
            [
                event("SAAScanComplete", timestamp="2026-01-01T02:05:00Z",
                      BodyName="Saved System 1", BodyID=1, ProbesUsed=3, EfficiencyTarget=4)
            ],
            append=True,
        )
        self.assertEqual(system_map_store.sync_system_maps(), 1)
        updated = system_map_store.get_system_map("Saved System", include_full=True)
        self.assertIn("SAAScanComplete", updated["full_text"])


if __name__ == "__main__":
    unittest.main()
