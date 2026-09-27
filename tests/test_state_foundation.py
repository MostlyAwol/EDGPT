import asyncio
import json
import os
from pathlib import Path
import subprocess
import socket
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))
import current_state
import history_store as history
import system_map_store as maps
import server
import mcp_server
from diagnostics import TOOLS

FIXTURES = Path(__file__).with_name("fixtures")


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.journals = self.root / "journals"
        self.journals.mkdir()
        for module, key, value in (
            (history, "ELITE_DIR", self.journals),
            (history, "DB_PATH", self.root / "data" / "history.db"),
            (maps, "MAP_DB_PATH", self.root / "data" / "maps.db"),
        ):
            self.enterContext(patch.object(module, key, value))
        self.journal = self.journals / "Journal.01.log"
        self.journal.write_bytes((FIXTURES / "session.jsonl").read_bytes())

    def append(self, values):
        with self.journal.open("a", encoding="utf-8") as stream:
            for value in values:
                stream.write(json.dumps(value) + "\n")

    def test_shared_state_and_single_sync_per_profile(self):
        self.append([{"event": "Unrelated"}] * 300)
        (self.journals / "Status.json").write_text(json.dumps({
            "Flags": 8, "Latitude": 3, "Fuel": {"FuelMain": 17, "FuelReservoir": 0.5}}))
        with patch.object(history, "sync_journals", wraps=history.sync_journals) as sync:
            http = server.build_state()
            self.assertEqual(sync.call_count, 1)
            sync.reset_mock()
            mcp = mcp_server.build_current_state()
            self.assertEqual(sync.call_count, 1)
        for key, value in http.items():
            if key != "generated_at":
                self.assertEqual(value, mcp[key], key)
        self.assertEqual(http["system"], "Destination")
        self.assertFalse(http["docked"])
        self.assertIsNone(http["station"])
        self.assertEqual(http["location"]["latitude"], 3)
        self.assertEqual(http["fuel"]["main"], 17)
        self.assertEqual(mcp["location_event"]["event"], "FSDJump")
        self.assertEqual(len(mcp["recent_events"]), 250)
        self.assertIn("loadout", mcp)
        self.assertEqual(mcp["live_json_files"], ["Status.json"])

    def test_incremental_restart_duplicates_and_query_contracts(self):
        self.assertEqual(history.sync_journals(), 8)
        self.assertEqual(history.sync_journals(), 0)
        duplicate = {"event": "FuelScoop", "Total": 30}
        self.append([duplicate, duplicate])
        self.assertEqual(history.sync_journals(), 2)
        # New interpreter reads existing cursors, rather than only testing in-memory state.
        env = dict(os.environ, PYTHONPATH=str(BIN), ELITE_JOURNAL_DIR=str(self.journals),
                   EDGPT_DATA_DIR=str(history.DB_PATH.parent))
        code = "import history_store as h; from pathlib import Path; h.DB_PATH=Path(r'%s'); print(h.sync_journals())" % history.DB_PATH
        result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "0")
        self.assertEqual(len(history.search_events(event="FuelScoop")), 3)
        self.assertEqual(len(history.search_events(query="Destination", start_time="2026-01-01T00:00:05Z")), 2)
        first = history.get_event_page(limit=6)
        second = history.get_event_page(first["next_before_id"], 6)
        ids = [item["id"] for item in first["items"] + second["items"]]
        self.assertEqual(len(ids), 10)
        self.assertEqual(len(set(ids)), 10)

    def test_multiple_files_legacy_malformed_and_partial_append(self):
        (self.journals / "Journal.02.log").write_bytes((FIXTURES / "legacy_and_malformed.jsonl").read_bytes())
        self.assertEqual(history.sync_journals(), 11)
        self.assertEqual(history.latest_event("UnknownFutureEvent")["NewField"], {"retained": True})
        with self.journal.open("ab") as stream:
            stream.write(b'{"event":"FuelScoop","Total":')
        self.assertEqual(history.sync_journals(), 0)
        with self.journal.open("ab") as stream:
            stream.write(b'31}\n')
        self.assertEqual(history.sync_journals(), 1)
        self.assertEqual(history.latest_event("FuelScoop")["Total"], 31)

    def test_truncation_invalidates_history_and_maps(self):
        maps.sync_system_maps()
        generation = history.history_generation()
        self.journal.write_text('{"event":"FSDJump","StarSystem":"New","SystemAddress":300}\n')
        self.assertEqual(history.sync_journals(), 1)
        self.assertNotEqual(history.history_generation(), generation)
        self.assertEqual(history.history_summary()["events_indexed"], 1)
        self.assertEqual(maps.get_current_system_map()["system_name"], "New")
        self.assertIsNone(maps.get_system_map(200))

    def test_schema_migration_and_map_rebuild_with_equal_watermark(self):
        maps.sync_system_maps()
        with history._connect() as conn:
            conn.execute("PRAGMA user_version=0")
        history.init_db()
        with history._connect() as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], history.HISTORY_SCHEMA_VERSION)
            conn.execute("UPDATE history_meta SET value='replacement' WHERE key='generation'")
        with maps._connect() as conn:
            conn.execute("UPDATE system_maps SET system_name='obsolete'")
            conn.commit()
        maps.sync_system_maps()
        self.assertEqual(maps.list_system_maps()[0]["system_name"], "Destination")
        with maps._connect() as conn:
            maps._set_meta(conn, "schema_version", 0)
            conn.commit()
        self.assertEqual(maps.sync_system_maps(), 1)
        with history._connect() as conn:
            conn.execute("PRAGMA user_version=999")
        with self.assertRaisesRegex(RuntimeError, "Unsupported history schema"):
            history.sync_journals()

    def test_imports_do_not_start_network_or_create_data(self):
        data = self.root / "uncreated"
        code = """
import socket
from unittest.mock import patch
with patch.object(socket.socket, 'bind', side_effect=AssertionError('listener on import')), \\
     patch.object(socket.socket, 'connect', side_effect=AssertionError('network on import')):
    import server, mcp_server
"""
        env = dict(os.environ, PYTHONPATH=str(BIN), EDGPT_DATA_DIR=str(data), ELITE_JOURNAL_DIR=str(self.journals))
        result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(data.exists())

    def test_mcp_registration_and_invocation(self):
        async def check():
            registered = await mcp_server.mcp.list_tools()
            self.assertEqual({tool.name for tool in registered}, set(TOOLS))
            result = await mcp_server.mcp.call_tool("get_elite_state", {})
            self.assertIn("Destination", str(result))
        asyncio.run(check())

    def test_mcp_client_over_http(self):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = dict(os.environ, ELITE_JOURNAL_DIR=str(self.journals),
                   EDGPT_DATA_DIR=str(self.root / "mcp-data"), EDGPT_MCP_PORT=str(port))
        process = subprocess.Popen([sys.executable, str(BIN / "mcp_server.py")],
                                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        self.fail("MCP server did not start")
                    time.sleep(0.05)

            async def check():
                async with streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        listed = await session.list_tools()
                        self.assertEqual({tool.name for tool in listed.tools}, set(TOOLS))
                        result = await session.call_tool("get_elite_state", {})
                        self.assertFalse(result.isError)
                        self.assertIn("Destination", str(result.content))
            asyncio.run(asyncio.wait_for(check(), timeout=15))
        finally:
            process.terminate()
            process.wait(timeout=10)


class ReducerTests(unittest.TestCase):
    def test_pure_reducer_live_precedence_and_no_mutation(self):
        events = [json.loads(line) for line in (FIXTURES / "session.jsonl").read_text().splitlines()]
        original = json.dumps(events)
        result = current_state.reduce_state(events, {"Latitude": 9, "Fuel": {"FuelMain": 12}})
        self.assertEqual(result["system"], "Destination")
        self.assertEqual(result["ship"], "CobraMkIII")
        self.assertEqual(result["fuel"], {"main": 12, "reservoir": None, "capacity": 32})
        self.assertEqual(result["location"]["latitude"], 9)
        self.assertEqual(json.dumps(events), original)

    def test_empty_legacy_and_movement_clears_old_docking(self):
        self.assertIsNone(current_state.reduce_state([])["system"])
        result = current_state.reduce_state([
            {"event": "Docked", "StationName": "Old"},
            {"event": "CarrierJump", "StarSystem": "New"},
        ])
        self.assertEqual(result["system"], "New")
        self.assertFalse(result["docked"])
        self.assertIsNone(result["station"])
