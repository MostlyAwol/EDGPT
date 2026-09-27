import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch


BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))

import server


class StateEndpointContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = [
            {
                "timestamp": f"2026-01-01T00:{index // 60:02d}:{index % 60:02d}Z",
                "event": "TestEvent",
                "Sequence": index,
            }
            for index in range(300)
        ]
        cls.live_files = {
            "Status.json": {"Fuel": {"FuelMain": 12.5, "FuelReservoir": 0.5}},
            "NavRoute.json": {"Route": [{"StarSystem": "Destination"}]},
            "Cargo.json": {"Inventory": []},
        }

        def latest_event(event_name):
            values = {
                "Loadout": {
                    "event": "Loadout",
                    "Ship": "CobraMkIII",
                    "ShipName": "Test Ship",
                    "ShipIdent": "TEST",
                    "MaxJumpRange": 22.5,
                    "FuelCapacity": {"Main": 32.0},
                    "Modules": [{"Slot": "MainEngines", "Item": "test_engine"}],
                },
                "Location": {
                    "event": "Location",
                    "StarSystem": "Test System",
                    "SystemAddress": 123,
                    "Body": "Test System A",
                    "BodyType": "Star",
                    "Docked": False,
                },
                "LoadGame": {
                    "event": "LoadGame",
                    "Ship": "CobraMkIII",
                    "ShipName": "Test Ship",
                    "ShipIdent": "TEST",
                },
            }
            return values.get(event_name)

        cls.patchers = [
            patch.object(server, "sync_journals", return_value=0),
            patch.object(
                server,
                "recent_events",
                side_effect=lambda limit: cls.events[-int(limit):],
            ),
            patch.object(server, "latest_event", side_effect=latest_event),
            patch.object(
                server,
                "history_summary",
                return_value={"events_indexed": 300, "journal_files_indexed": 1},
            ),
            patch.object(server, "all_live_json_files", return_value=cls.live_files),
            patch.object(
                server,
                "read_json_file",
                side_effect=lambda name: cls.live_files.get(name),
            ),
            patch.object(
                server,
                "get_current_system_map",
                return_value={"system_name": "Test System", "simple_text": "System: Test System"},
            ),
        ]
        cls.mocks = [patcher.start() for patcher in cls.patchers]
        cls.httpd = HTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base_url = f"http://127.0.0.1:{cls.httpd.server_port}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
        for patcher in reversed(cls.patchers):
            patcher.stop()

    def setUp(self):
        for mock in self.mocks:
            mock.reset_mock()

    def request(self, query=""):
        suffix = f"?{query}" if query else ""
        with urllib.request.urlopen(self.base_url + "/state" + suffix, timeout=5) as response:
            self.assertEqual(response.status, 200)
            return json.loads(response.read().decode("utf-8"))

    def assert_heavy_fields(self, state, expected):
        for name in ("history_summary", "recent_events", "loadout", "live_files"):
            self.assertEqual(name in state, name in expected, name)

    def test_default_state_omits_heavy_fields_but_keeps_derived_state(self):
        state = self.request()

        self.assert_heavy_fields(state, set())
        self.assertEqual(state["system"], "Test System")
        self.assertEqual(state["ship"], "CobraMkIII")
        self.assertEqual(state["jump_range"], 22.5)
        self.assertEqual(state["fuel"]["capacity"], 32.0)
        self.assertEqual(state["fuel"]["main"], 12.5)
        self.assertIn("status", state)
        self.assertIn("navroute", state)
        self.assertIn("system_map", state)
        server.history_summary.assert_not_called()
        server.all_live_json_files.assert_not_called()
        server.recent_events.assert_called_once_with(250)

    def test_each_heavy_field_is_independently_selectable(self):
        cases = (
            ("history_summary=true", "history_summary"),
            ("recent_events=5", "recent_events"),
            ("loadout=true", "loadout"),
            ("live_files=true", "live_files"),
        )
        for query, field in cases:
            with self.subTest(field=field):
                state = self.request(query)
                self.assert_heavy_fields(state, {field})
                if field == "recent_events":
                    self.assertEqual(len(state[field]), 5)

    def test_explicit_zero_returns_empty_recent_events(self):
        state = self.request("recent_events=0")

        self.assert_heavy_fields(state, {"recent_events"})
        self.assertEqual(state["recent_events"], [])
        server.recent_events.assert_called_once_with(250)

    def test_combined_options_return_all_requested_fields(self):
        state = self.request(
            "history_summary=true&recent_events=100&loadout=true&live_files=true"
        )

        self.assert_heavy_fields(
            state, {"history_summary", "recent_events", "loadout", "live_files"}
        )
        self.assertEqual(len(state["recent_events"]), 100)
        self.assertEqual(state["loadout"]["Ship"], "CobraMkIII")
        self.assertIn("Cargo.json", state["live_files"])

    def test_false_options_do_not_include_fields(self):
        state = self.request("history_summary=false&loadout=off&live_files=0")
        self.assert_heavy_fields(state, set())

    def test_invalid_options_return_400_with_an_error(self):
        invalid_queries = (
            "history_summary=maybe",
            "loadout=",
            "live_files=true&live_files=false",
            "recent_events=abc",
            "recent_events=-1",
            "recent_events=5001",
        )
        for query in invalid_queries:
            with self.subTest(query=query):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(
                        self.base_url + "/state?" + query, timeout=5
                    )
                self.assertEqual(caught.exception.code, 400)
                body = json.loads(caught.exception.read().decode("utf-8"))
                self.assertTrue(body.get("error"))


if __name__ == "__main__":
    unittest.main()
