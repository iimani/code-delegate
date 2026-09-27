import json
import unittest

from shop.reports.base import Report
from shop.reports.export import export, to_csv, to_json
from tests.support import make_app, seed


class ExportTests(unittest.TestCase):
    def test_functions(self):
        r = Report("T", ["a", "b"], [{"a": 1, "b": "x,y"}])
        self.assertEqual(to_csv(r), 'a,b\r\n1,"x,y"\r\n')
        self.assertEqual(json.loads(to_json(r))["rows"], [{"a": 1, "b": "x,y"}])
        with self.assertRaises(ValueError):
            export(r, "xml")

    def test_endpoint(self):
        app, _ = make_app()
        seed(app)
        resp = app.handle("GET", "/reports/inventory?format=csv")
        self.assertEqual(resp.status, 200)
        self.assertTrue(resp.body["content"].startswith("sku,"))


if __name__ == "__main__":
    unittest.main()
