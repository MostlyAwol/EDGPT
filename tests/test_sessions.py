import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))
import history_store as history
import session_store as sessions
import session_summary as summary
import server
import mcp_server

FIXTURE = Path(__file__).with_name("fixtures") / "session_activities.jsonl"


class SessionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.journals = self.root / "journals"
        self.journals.mkdir()
        self.journal = self.journals / "Journal.02.log"
        for module, name, value in (
            (history, "ELITE_DIR", self.journals),
            (history, "DB_PATH", self.root / "edgpt_history.db"),
            (sessions, "SESSION_DB_PATH", self.root / "edgpt_sessions.db"),
        ):
            self.enterContext(patch.object(module, name, value))

    def append(self, *events, path=None):
        with (path or self.journal).open("a", encoding="utf-8") as stream:
            for event in events:
                stream.write(json.dumps(event) + "\n")

    def fixture(self):
        self.journal.write_bytes(FIXTURE.read_bytes())

    def test_activity_totals_and_provenance(self):
        self.fixture()
        result = sessions.get_current_session_summary()
        self.assertEqual(result, mcp_server.get_current_session_summary())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["profile_id"], "F123")
        self.assertEqual(result["game_mode"], "Solo")
        self.assertEqual(result["duration_seconds"], 1198)
        self.assertEqual(result["source_event_range"], {"first_id": 3, "last_id": 25})
        groups = result["activities"]
        self.assertEqual(groups["credits"]["totals"], {"earned": 1650, "spent": 500, "net": 1150})
        self.assertEqual(groups["jumps"]["totals"], {"distance_ly": 12.5})
        self.assertEqual(groups["material_changes"]["totals"], {"added": 4, "removed": 2})
        self.assertEqual(groups["cargo_changes"]["totals"], {"added": 2, "removed": 1})
        for name in ("ship_changes", "deaths", "rebuys", "hull_damage", "bounty_awards", "scans",
                     "mapped_bodies", "organic_discoveries", "notable_finds", "missions_accepted",
                     "missions_completed", "missions_failed"):
            self.assertEqual(groups[name]["count"], 1, name)
            self.assertGreaterEqual(groups[name]["source_event_range"]["first_id"], 3)
        self.assertIn("12.5 ly", result["summary_text"])
        self.assertIn("1650 credits earned", result["summary_text"])
        self.assertNotIn("raw_json", json.dumps(result))

    def test_rollover_restart_crash_and_commander_switch(self):
        self.append({"event": "LoadGame", "Commander": "One", "FID": "F1"}, {"event": "Continued", "Part": 2})
        initial = sessions.get_current_session_summary()
        rollover = self.journals / "Journal.03.log"
        self.append({"event": "FileHeader", "part": 2}, {"event": "FSDJump", "StarSystem": "Other", "JumpDist": 4}, path=rollover)
        env = dict(os.environ, PYTHONPATH=str(BIN), EDGPT_DATA_DIR=str(self.root), ELITE_JOURNAL_DIR=str(self.journals))
        run = subprocess.run([sys.executable, "-c", "import json,session_store; print(json.dumps(session_store.get_current_session_summary()))"],
                             env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stderr)
        restarted = json.loads(run.stdout)
        self.assertEqual(restarted["session_id"], initial["session_id"])
        self.assertEqual(restarted["activities"]["jumps"]["count"], 1)
        self.append({"event": "LoadGame", "Commander": "Two", "FID": "F2"}, path=rollover)
        current = sessions.get_current_session_summary()
        self.assertEqual(current["profile_id"], "F2")
        past = sessions.get_game_session(initial["session_id"])
        self.assertEqual(past["end_reason"], "new_load_game")
        self.assertEqual(past["status"], "incomplete")
        self.assertEqual(len(sessions.list_game_sessions()["items"]), 2)
        self.append({"event": "Shutdown"}, path=rollover)
        self.assertEqual(sessions.get_current_session_summary()["status"], "completed")

    def test_new_file_crash_and_missing_start(self):
        self.append({"event": "FSDJump", "JumpDist": 1})
        first = sessions.get_current_session_summary()
        self.assertTrue(any("LoadGame is missing" in item for item in first["warnings"]))
        self.append({"event": "FileHeader", "part": 1}, {"event": "LoadGame"}, path=self.journals / "Journal.03.log")
        self.assertEqual(sessions.list_game_sessions()["count"], 2)
        self.assertEqual(sessions.get_game_session(first["session_id"])["end_reason"], "new_journal")

    def test_rebuild_schema_generation_and_late_history(self):
        self.fixture()
        original = sessions.get_current_session_summary()
        with closing(sqlite3.connect(sessions.SESSION_DB_PATH)) as conn:
            with conn:
                conn.execute("UPDATE session_meta SET value='999' WHERE key='schema_version'")
        self.assertEqual(sessions.get_current_session_summary(), original)
        # An older journal imported later must sort before the existing session.
        self.append({"event": "LoadGame", "Commander": "Earlier"}, {"event": "Shutdown"}, path=self.journals / "Journal.01.log")
        self.assertEqual(sessions.get_current_session_summary()["session_id"], original["session_id"])
        self.assertEqual(sessions.list_game_sessions()["count"], 2)
        self.journal.write_text('{"event":"LoadGame","Commander":"Replacement"}\n')
        self.assertEqual(sessions.get_current_session_summary()["commander"], "Replacement")
        self.assertEqual(sessions.get_game_session(original["session_id"]), {})

    def test_pagination_filters_empty_and_validation(self):
        self.assertEqual(sessions.get_current_session_summary(), {})
        self.assertEqual(sessions.list_game_sessions()["items"], [])
        self.fixture()
        self.append({"event": "LoadGame", "timestamp": "2026-01-02T00:00:00Z"})
        page = sessions.list_game_sessions(limit=1)
        second = sessions.list_game_sessions(limit=1, before=page["next_before"])
        self.assertNotEqual(page["items"][0]["session_id"], second["items"][0]["session_id"])
        self.assertIsNone(second["next_before"])
        self.assertEqual(sessions.list_game_sessions(start_time="2026-01-01T19:00:00-05:00")["count"], 1)
        self.assertEqual(sessions.list_game_sessions(end_time="2026-01-01T23:00:00Z")["count"], 1)
        for kwargs in ({"limit": 0}, {"limit": 101}, {"before": -1}, {"start_time": "bad"},
                       {"start_time": "2026-01-01"}, {"start_time": "2026-01-02T00:00:00Z", "end_time": "2026-01-01T00:00:00Z"}):
            with self.assertRaises(ValueError):
                sessions.list_game_sessions(**kwargs)

    def test_bounded_output_malformed_fields_and_duplicates(self):
        self.append({"event": "LoadGame"})
        self.append(*[{"event": "Scan", "BodyName": f"Body {index}"} for index in range(300)])
        self.append({"event": "FSDJump", "JumpDist": "bad"}, {"event": "MarketBuy", "TotalCost": True},
                    {"event": "MaterialTrade", "Paid": None}, {"event": "UnknownFutureEvent"})
        result = sessions.get_current_session_summary()
        group = result["activities"]["scans"]
        self.assertEqual(group["count"], 300)
        self.assertEqual(len(group["examples"]), 20)
        self.assertEqual(group["examples_omitted"], 280)
        self.assertNotIn("distance_ly", result["activities"]["jumps"]["totals"])
        self.assertEqual(result, sessions.get_current_session_summary())
        self.assertTrue(any("invalid" in warning for warning in result["warnings"]))

    def test_http_endpoints(self):
        self.fixture()
        http = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        base = f"http://127.0.0.1:{http.server_port}"

        def get(path):
            with urllib.request.urlopen(base + path, timeout=5) as response:
                return json.load(response)

        current = get("/sessions/current")
        self.assertEqual(current, get("/sessions/get?id=" + current["session_id"]))
        self.assertEqual(get("/sessions")["items"], [current])
        for path, status in (("/sessions?limit=0", 400), ("/sessions?limit=2&limit=3", 400),
                             ("/sessions?start=bad", 400), ("/sessions/get", 400),
                             ("/sessions/get?id=missing", 404)):
            with self.assertRaises(urllib.error.HTTPError) as error:
                get(path)
            self.assertEqual(error.exception.code, status)
        with patch.object(server, "build_state", return_value={"unchanged": True}):
            self.assertEqual(get("/state"), {"unchanged": True})


class SessionReducerTests(unittest.TestCase):
    def test_inputs_unchanged_and_cash_is_not_double_counted(self):
        events = [{"event": "LoadGame", "Credits": 1000},
                  {"event": "Bounty", "TotalReward": 100},
                  {"event": "RedeemVoucher", "Amount": 100},
                  {"event": "SellOrganicData", "BioData": [{"Value": 50, "Bonus": 20}]},
                  {"event": "SellExplorationData", "BaseValue": 20, "Bonus": 5},
                  {"event": "MultiSellExplorationData", "TotalEarnings": 50, "BaseValue": 40, "Bonus": 10}]
        before = json.dumps(events)
        model = summary.new_session(events[0], ["Journal.01.log", 1])
        for index, event in enumerate(events, 1):
            summary.apply_event(model, event, index)
        self.assertEqual(model["activities"]["credits"]["totals"]["earned"], 245)
        self.assertEqual(json.dumps(events), before)
        rendered = summary.render_session(model)
        rendered["warnings"].append("not in model")
        self.assertNotIn("not in model", model["warnings"])
