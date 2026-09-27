import sys
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
import server


class MapPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = HTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join()

    def get(self, path):
        try:
            response = urlopen(self.url + path)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read().decode("utf-8")

    def test_current_html_escapes_journal_text(self):
        with patch.object(server, "current_page_map", return_value={
            "system_name": "<script>bad()</script>", "system_address": 123,
            "simple_text": "Star\n└─ Planet <img src=x>",
        }):
            code, headers, body = self.get("/map")
        self.assertEqual(code, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("└─ Planet &lt;img src=x&gt;", body)
        self.assertNotIn("<script>bad()", body)
        self.assertIn("setTimeout(refresh,5000)", body)

    def test_saved_system_preserves_large_id(self):
        with patch.object(server, "get_system_map", return_value={"system_name": "Saved"}) as lookup:
            code, _, body = self.get("/map?system=12345678901234567")
        lookup.assert_called_once_with("12345678901234567")
        self.assertEqual(code, 200)
        self.assertIn("Saved system", body)

    def test_missing_and_invalid_are_html(self):
        with patch.object(server, "get_system_map", return_value=None):
            code, _, body = self.get("/map?system=123")
            self.assertEqual(code, 404)
            self.assertIn("No saved map", body)
        for query in ("system=", "system=no", "system=-1", "system=1&system=2",
                      "other=1", "system=999999999999999999999999"):
            code, headers, _ = self.get("/map?" + query)
            self.assertEqual(code, 400, query)
            self.assertIn("text/html", headers["Content-Type"])

    def test_empty_current_page(self):
        with patch.object(server, "current_page_map", return_value=None):
            code, _, body = self.get("/map")
        self.assertEqual(code, 200)
        self.assertIn("Waiting for journal data", body)

    def test_current_follows_latest_location_and_carrier_jump(self):
        for kind in ("Location", "CarrierJump"):
            with patch.object(server, "latest_state_events", return_value=[
                {"event": "FSDJump", "SystemAddress": 1},
                {"event": kind, "SystemAddress": 2, "StarSystem": "Latest"},
            ]), patch.object(server, "get_system_map", return_value=None) as lookup:
                result = server.current_page_map()
            lookup.assert_called_once_with("2")
            self.assertEqual(result["system_name"], "Latest")
            self.assertEqual(result["system_address"], 2)


if __name__ == "__main__":
    unittest.main()
