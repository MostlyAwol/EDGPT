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
from map_page import render_map_page
from system_map import apply_event, new_system_map
from system_map_store import _result


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
        lookup.assert_called_once_with("12345678901234567", include_model=True)
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
            lookup.assert_called_once_with("2", include_model=True)
            self.assertEqual(result["system_name"], "Latest")
            self.assertEqual(result["system_address"], 2)

    def test_rich_body_details_units_nested_data_and_escaping(self):
        model = new_system_map(123, "Rich system")
        for index, event in enumerate([
            {"event": "FSDJump", "StarSystem": "Rich system", "BodyID": 0, "Body": "Primary", "BodyType": "Star", "Population": 0},
            {"event": "Scan", "BodyID": 0, "BodyName": "Primary", "StarType": "K", "StellarMass": 0.8},
            {"event": "Scan", "BodyID": 1, "BodyName": "Planet <script>alert(1)</script>", "Parents": [{"Star": 0}],
             "PlanetClass": "Icy body", "DistanceFromArrivalLS": 0, "Radius": 1000000, "SurfaceGravity": 9.80665,
             "OrbitalPeriod": 86400, "RotationPeriod": -43200, "SurfacePressure": 101325, "MassEM": 0.0001,
             "WasDiscovered": False, "Landable": True, "Atmosphere": "thin atmosphere", "TerraformState": "Terraformable",
             "Rings": [{"Name": "Ring A", "RingClass": "eRingClass_Icy", "InnerRad": 2000000, "OuterRad": 3000000}],
             "Materials": [{"Name": "iron", "Percent": 20}], "Composition": {"Ice": 0.9}, "FutureField": {"Nested": [False, 0, "<img>"]}},
            {"event": "SAASignalsFound", "BodyID": 1, "Signals": [{"Type": "$SAA_SignalType_Biological;", "Count": 3}]},
            {"event": "ScanOrganic", "BodyID": 1, "Species_Localised": "Test organism"},
            {"event": "SAAScanComplete", "BodyID": 1, "ProbesUsed": 4},
            {"event": "FSSSignalDiscovered", "SignalName": "Test station", "IsStation": True},
        ], 1):
            apply_event(model, {"SystemAddress": 123, **event}, index)
        result = _result(model, include_model=True)
        page = render_map_page(result)
        for content in ("1,000 km", "1 g", "1 d", "-0.5 d", "1 atm", "0.0001 M⊕", "Biological × 3",
                        "Landable", "Terraformable", "Surface mapped", "Undiscovered at scan", "Ring A", "iron 20 %",
                        "Test organism", "Test station", "Future Field", "&lt;img&gt;", "Composition"):
            self.assertIn(content, page)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertLess(page.index('id="body-0"'), page.index('id="body-1"'))
        self.assertNotIn("model", _result(model))

    def test_cyclic_nodes_remain_visible_once(self):
        model = new_system_map(123, "Cycle")
        for body, parent in ((1, 2), (2, 1)):
            apply_event(model, {"event": "Scan", "BodyID": body, "BodyName": f"Body {body}",
                               "PlanetClass": "Rocky body", "Parents": [{"Planet": parent}]})
        page = render_map_page(_result(model, include_model=True))
        self.assertEqual(page.count('id="body-1"'), 1)
        self.assertEqual(page.count('id="body-2"'), 1)


if __name__ == "__main__":
    unittest.main()
