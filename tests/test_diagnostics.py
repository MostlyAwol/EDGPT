import json
from contextlib import closing
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
import diagnostics as d
import history_store as h
import system_map_store as m


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.journals = self.root / "private-commander"
        self.journals.mkdir()
        self.config = self.root / "config.json"
        self.config.write_text("{}")
        for patcher in (patch.object(h, "ELITE_DIR", self.journals),
                        patch.object(h, "DATA_DIR", self.root),
                        patch.object(h, "DB_PATH", self.root / "history.db"),
                        patch.object(m, "MAP_DB_PATH", self.root / "maps.db"),
                        patch.dict(os.environ, EDGPT_CONFIG_FILE=str(self.config), EDGPT_DATA_DIR=str(self.root)),
                        patch.object(d, "probe_service")):
            patcher.start()
            self.addCleanup(patcher.stop)
        d._observations.clear()
        self.journal = self.journals / "Journal.test.log"
        self.journal.write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
                                            "event": "FSDJump", "StarSystem": "Private System",
                                            "SystemAddress": 123}) + "\n")
        h.sync_journals()
        m.sync_system_maps()

    def test_ready_and_privacy(self):
        value = d.health()
        self.assertEqual(value["status"], "ready")
        self.assertEqual(value["components"]["history"]["event_count"], 1)
        for private in (str(self.root), "private-commander", "Private System", "Journal.test.log"):
            self.assertNotIn(private, json.dumps(value))

    def test_missing_journals(self):
        with patch.object(h, "ELITE_DIR", self.root / "missing"):
            self.assertEqual(d.health()["components"]["journal_directory"]["status"], "error")

    def test_database_unavailable(self):
        h.DB_PATH.write_bytes(b"broken")
        self.assertEqual(d.health()["status"], "error")

    def test_stale(self):
        with closing(sqlite3.connect(h.DB_PATH)) as db:
            db.execute("UPDATE events SET timestamp='2000-01-01T00:00:00Z'")
            db.commit()
        self.assertEqual(d.health()["status"], "stale")

    def test_indexing_and_restart(self):
        self.journal.write_text(self.journal.read_text() + json.dumps({"event": "Scan"}) + "\n")
        self.assertEqual(d.health()["status"], "indexing")
        h.sync_journals()
        self.assertEqual(d.health()["components"]["system_maps"]["status"], "indexing")
        m.sync_system_maps()
        d._observations.clear()
        self.assertEqual(d.health()["status"], "ready")

    def test_optional_failure_and_recovery(self):
        self.config.write_text(json.dumps({"github": {"enabled": True}}))
        d.heartbeat("github", "degraded", "GitHub request failed; check settings.")
        self.assertEqual(d.health()["status"], "degraded")
        d.heartbeat("github", "ready")
        result = d.health()
        self.assertEqual(result["status"], "ready")
        self.assertIsNotNone(result["components"]["github"]["last_error"])

    def test_core_probe_failure(self):
        with patch.object(d, "probe_service", side_effect=OSError("secret path")):
            result = d.health()
        self.assertEqual(result["components"]["mcp"]["status"], "error")
        self.assertNotIn("secret path", json.dumps(result))

    def test_startup_and_index_failure(self):
        h.DB_PATH.unlink()
        d.heartbeat("indexer", "indexing")
        self.assertEqual(d.health()["status"], "indexing")
        d.heartbeat("indexer", "error", "Index update failed.")
        self.assertEqual(d.health()["status"], "error")

    def test_capabilities_match_transports(self):
        import asyncio
        import mcp_server
        tools = asyncio.run(mcp_server.mcp.list_tools())
        self.assertEqual(set(d.TOOLS), {tool.name for tool in tools})
        self.assertEqual(mcp_server.get_edgpt_capabilities(), d.capabilities())

    def test_http_contract(self):
        import threading
        import urllib.request
        from http.server import ThreadingHTTPServer
        from server import Handler
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for endpoint in ("health", "capabilities", "version"):
                with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/{endpoint}") as response:
                    value = json.load(response)
                    self.assertEqual(value["application"], "EDGPT")
                    self.assertIn("no-store", response.headers["Cache-Control"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
