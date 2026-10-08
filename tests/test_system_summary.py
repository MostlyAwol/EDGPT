import asyncio
from copy import deepcopy
from http.server import HTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))
import curiosities
import history_store as history
import mcp_server
import server
import system_map_store as maps
from system_map import apply_event, new_system_map
from system_summary import build_system_summary, SUMMARY_SCHEMA_VERSION

EVENTS = [json.loads(line) for line in
          Path(__file__).with_name("fixtures").joinpath("system_overview.jsonl").read_text().splitlines()]


def model_from(events):
    model = new_system_map(123, "Overview")
    for index, event in enumerate(events, 1):
        apply_event(model, event, index)
    return model


class SummaryRenderingTests(unittest.TestCase):
    def test_gate_and_grouping(self):
        self.assertIsNone(build_system_summary(model_from(EVENTS[:-1])))
        model = model_from(EVENTS)
        original = deepcopy(model)
        summary = build_system_summary(model)
        self.assertEqual(model, original)
        self.assertEqual(summary["stars"], [{"type": "K star", "count": 1}])
        self.assertEqual(summary["planets"], [{"type": "Rocky body", "count": 2}])
        self.assertEqual(summary["rings"], [{"type": "Rocky", "count": 1}])
        self.assertIn("3 of 3 bodies known", summary["summary_text"])
        self.assertEqual(summary["exobiology"]["biological_signals"], 2)
        self.assertEqual(summary["exobiology"]["bodies"], 1)
        self.assertEqual(summary["exobiology"]["species"], ["Stratum Tectonicas"])
        self.assertNotIn("value", summary["summary_text"])
        self.assertNotIn("Curiosities", summary["summary_text"])
        order = [summary["summary_text"].index("## " + name)
                 for name in ("Stars", "Planets", "Rings", "Exobiology")]
        self.assertEqual(order, sorted(order))

    def test_ordinary_system_and_empty_sections(self):
        model = model_from([e for e in EVENTS if e["event"] not in
                            ("ScanOrganic", "FSSBodySignals", "SAASignalsFound")])
        model["nodes"]["1"]["event_data"]["Scan"].pop("Rings")
        text = build_system_summary(model)["summary_text"]
        for name in ("Rings", "Exobiology", "Curiosities", "None", "discovery", "mapped"):
            self.assertNotIn(name, text)

    def test_expected_unknown_conflicting_and_partial(self):
        model = model_from(EVENTS)
        del model["nodes"]["2"]
        self.assertIn("2 of 3 bodies known", build_system_summary(model)["summary_text"])
        model["system_events"]["FSSDiscoveryScan"]["BodyCount"] = 4
        self.assertNotIn("bodies known", build_system_summary(model)["summary_text"])
        model["body_count"] = None
        self.assertNotIn("bodies known", build_system_summary(model)["summary_text"])

    def test_determinism_ring_deduplication_and_inferred_nodes(self):
        model = model_from(EVENTS)
        apply_event(model, {"event": "Scan", "BodyID": 10, "BodyName": "Overview B",
                            "StarType": "B", "Parents": [{"Null": 20}]})
        apply_event(model, {"event": "Scan", "BodyID": 11, "BodyName": "Overview 1 A Ring",
                            "RingClass": "eRingClass_Rocky"})
        model["nodes"]["1"]["event_data"]["Scan"]["Rings"].append(
            {"Name": "Overview A Belt", "RingClass": "eRingClass_Rocky"})
        summary = build_system_summary(model)
        self.assertEqual(summary["bodies_known"], 4)
        self.assertEqual([r["type"] for r in summary["stars"]], ["B star", "K star"])
        self.assertEqual(sum(r["count"] for r in summary["rings"]), 1)
        model["nodes"] = dict(reversed(list(model["nodes"].items())))
        self.assertEqual(summary, build_system_summary(model))

    def test_organics_without_signal_counts(self):
        model = model_from([e for e in EVENTS if e["event"] not in ("FSSBodySignals", "SAASignalsFound")])
        summary = build_system_summary(model)
        self.assertIn("Exobiology", summary["summary_text"])
        self.assertNotIn("0 biological signals", summary["summary_text"])


class CuriosityTests(unittest.TestCase):
    def test_initial_dispatcher_and_rule_order(self):
        model = model_from(EVENTS)
        original = deepcopy(model)
        self.assertEqual(curiosities.find_curiosities(model), [])
        with patch.object(curiosities, "CURIOSITY_RULES", (lambda m: ["First", "Second"], lambda m: ["Third"])):
            self.assertEqual(curiosities.find_curiosities(model), ["First", "Second", "Third"])
        self.assertEqual(model, original)


class SummaryPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.journals = self.root / "journals"
        self.journals.mkdir()
        self.enterContext(patch.object(history, "ELITE_DIR", self.journals))
        self.enterContext(patch.object(history, "DB_PATH", self.root / "history.db"))
        self.enterContext(patch.object(maps, "MAP_DB_PATH", self.root / "maps.db"))
        self.journal = self.journals / "Journal.01.log"
        self.write(EVENTS[:-1])

    def write(self, events, append=False):
        with self.journal.open("a" if append else "w", encoding="utf-8") as stream:
            for event in events:
                stream.write(json.dumps(event) + "\n")

    def persisted(self):
        with maps._connect() as conn:
            row = conn.execute("SELECT summary_json FROM system_summaries WHERE system_address=123").fetchone()
            return json.loads(row[0]) if row else None

    def test_gating_ingestion_restart_and_schema_rebuild(self):
        self.assertIsNone(maps.get_system_summary())
        self.assertIsNone(self.persisted())
        self.write([EVENTS[-1]], append=True)
        maps.sync_system_maps()
        saved = self.persisted()
        self.assertIn("3 of 3", saved["summary_text"])
        code = "import system_map_store as m; print(m.get_system_summary(123)['summary_text'])"
        env = dict(os.environ, PYTHONPATH=str(BIN), ELITE_JOURNAL_DIR=str(self.journals),
                   EDGPT_DATA_DIR=str(self.root))
        # Use the same persisted DB paths in a fresh interpreter.
        code = ("from pathlib import Path; import history_store as h; import system_map_store as m; "
                f"h.DB_PATH=Path({str(history.DB_PATH)!r}); m.MAP_DB_PATH=Path({str(maps.MAP_DB_PATH)!r}); " + code)
        result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(saved["summary_text"], result.stdout)
        with maps._connect() as conn:
            conn.execute("UPDATE system_summaries SET schema_version=0,summary_json='{}'")
            conn.commit()
        maps.sync_system_maps()
        self.assertEqual(self.persisted()["schema_version"], SUMMARY_SCHEMA_VERSION)

    def test_refresh_revisit_saved_read_and_nonmutation(self):
        self.write([EVENTS[-1]], append=True)
        maps.sync_system_maps()
        with maps._connect() as conn:
            original = conn.execute("SELECT map_json FROM system_maps WHERE system_address=123").fetchone()[0]
        with patch.object(curiosities, "find_curiosities", return_value=["One", "Two"]) as detector:
            summary = maps.get_system_summary("overview")
            self.assertEqual(detector.call_args.args[0], json.loads(original))
            self.assertEqual(summary, self.persisted())
            self.assertIn("- One\n- Two", summary["summary_text"])
        self.write([{**EVENTS[0], "timestamp": "2026-01-02T00:00:00Z"}], append=True)
        with patch.object(curiosities, "find_curiosities", return_value=["New"]) as detector:
            maps.sync_system_maps()
            self.assertTrue(detector.called)
            self.assertEqual(self.persisted()["curiosities"], ["New"])
        summary = maps.get_system_summary(123)
        self.assertNotIn("Curiosities", summary["summary_text"])
        self.assertEqual(summary, self.persisted())
        with maps._connect() as conn:
            before = conn.execute("SELECT map_json FROM system_maps WHERE system_address=123").fetchone()[0]
        maps.get_system_summary(123)
        with maps._connect() as conn:
            after = conn.execute("SELECT map_json FROM system_maps WHERE system_address=123").fetchone()[0]
        self.assertEqual(before, after)
        self.assertEqual(summary["stars"][0]["type"], "K star")

    def test_current_location_does_not_return_previous_system(self):
        self.write([EVENTS[-1], {"event": "Location", "SystemAddress": 999, "StarSystem": "Unknown"}], append=True)
        self.assertIsNone(maps.get_system_summary())
        self.assertIsNotNone(maps.get_system_summary(123))
        self.write([{ "event": "CarrierJump", "SystemAddress": 123}], append=True)
        self.assertIsNotNone(maps.get_system_summary())

    def test_adoption_and_history_reset(self):
        self.write([EVENTS[-1]], append=True)
        maps.sync_system_maps()
        with maps._connect() as conn:
            conn.execute("DELETE FROM system_summaries")
            conn.commit()
        maps.sync_system_maps()
        self.assertIsNotNone(self.persisted())
        self.write(EVENTS[:2])
        self.assertIsNone(maps.get_system_summary(123))
        self.assertIsNone(self.persisted())

    def test_http_and_registered_mcp_equivalence(self):
        http = HTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(http.server_close)
        self.addCleanup(thread.join, 3)
        self.addCleanup(http.shutdown)
        base = f"http://127.0.0.1:{http.server_port}/system-map/summary"
        def read(suffix=""):
            with urllib.request.urlopen(base + suffix, timeout=10) as response:
                return json.load(response)
        self.assertEqual(read(), {})
        self.write([EVENTS[-1]], append=True)
        expected = read()
        self.assertEqual(read("?system=Overview"), expected)
        self.assertEqual(read("?system=999"), {})
        for suffix in ("?system=", "?system=123&system=123", "?unknown=1"):
            with self.assertRaises(urllib.error.HTTPError) as error:
                read(suffix)
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
        async def check():
            for tool, args in (("get_current_system_summary", {}),
                               ("get_saved_system_summary", {"system": "123"})):
                content = await mcp_server.mcp.call_tool(tool, args)
                self.assertEqual(json.loads(content[0].text), expected)
        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
