import io
import json
import os
import tempfile
import unittest
from datetime import datetime

from shop.cli.main import main
from shop.reports.base import Report, render_text
from shop.reports.export import FORMATS, export, to_csv, to_json
from tests.support import make_app, seed

SAMPLE = Report("Demo", ["sku", "name", "qty"], [{"sku": "A-1", "name": "Pen, blue", "qty": 3},
                                                  {"sku": "B-2", "name": 'Pad "A4"', "qty": 0}])


class HiddenExportFunctionTests(unittest.TestCase):
    def test_csv(self):
        self.assertEqual(to_csv(SAMPLE), 'sku,name,qty\r\nA-1,"Pen, blue",3\r\nB-2,"Pad ""A4""",0\r\n')

    def test_csv_empty(self):
        self.assertEqual(to_csv(Report("E", ["a", "b"])), "a,b\r\n")

    def test_json(self):
        data = json.loads(to_json(SAMPLE))
        self.assertEqual(data, {"title": "Demo", "columns": ["sku", "name", "qty"],
                                "rows": [{"sku": "A-1", "name": "Pen, blue", "qty": 3},
                                         {"sku": "B-2", "name": 'Pad "A4"', "qty": 0}]})
        self.assertEqual(to_json(SAMPLE), json.dumps(data, indent=2))
        self.assertEqual(list(json.loads(to_json(SAMPLE))["rows"][0]), ["sku", "name", "qty"])

    def test_formats(self):
        self.assertEqual(set(FORMATS), {"text", "csv", "json"})
        self.assertIs(FORMATS["text"], render_text)
        self.assertEqual(export(SAMPLE, "csv"), to_csv(SAMPLE))
        self.assertEqual(export(SAMPLE, "text"), render_text(SAMPLE))
        with self.assertRaises(ValueError):
            export(SAMPLE, "xml")


class HiddenExportApiTests(unittest.TestCase):
    def setUp(self):
        self.app, self.clock = make_app()
        self.d = seed(self.app)

    def test_inventory_json_default(self):
        r = self.app.handle("GET", "/reports/inventory")
        self.assertEqual((r.status, r.body["name"], r.body["format"]), (200, "inventory", "json"))
        rows = json.loads(r.body["content"])["rows"]
        self.assertEqual([row["sku"] for row in rows], ["INK-001", "PAD-001", "PEN-001"])

    def test_customers_csv(self):
        self.app.order_service.place(self.d["bob"].id, [(self.d["pen"].id, 2)])
        r = self.app.handle("GET", "/reports/customers?format=csv")
        self.assertEqual(r.status, 200)
        lines = r.body["content"].split("\r\n")
        self.assertEqual(lines[0], "name,email,orders,revenue_cents")
        self.assertTrue(lines[1].startswith("Bob Brown,bob@example.com,1,"))

    def test_sales_text(self):
        self.clock.set(datetime(2026, 3, 1, 9, 0))
        r = self.app.handle("GET", "/reports/sales?format=text&from=2026-03-01&to=2026-03-02")
        self.assertEqual(r.status, 200)
        self.assertTrue(r.body["content"].startswith("Sales 2026-03-01 to 2026-03-02\n"))

    def test_errors(self):
        cases = [("/reports/nope", 404, "not_found"), ("/reports/inventory?format=xml", 400, "invalid"),
                 ("/reports/sales", 400, "invalid"), ("/reports/sales?from=2026-03-01&to=bad", 400, "invalid"),
                 ("/reports/sales?from=2026-03-05&to=2026-03-01", 400, "invalid")]
        for path, status, error in cases:
            r = self.app.handle("GET", path)
            self.assertEqual((r.status, r.body.get("error")), (status, error), path)


class HiddenExportCliTests(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def tearDown(self):
        os.unlink(self.db)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        return main(["--db", self.db, *args], out, err), out.getvalue(), err.getvalue()

    def test_formats(self):
        self.run_cli("products", "add", "PEN-1", "Pen", "2.00")
        code, out, _ = self.run_cli("report", "inventory", "--format", "csv")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("sku,name,on_hand,reserved,available,low_stock\r\nPEN-1,Pen,0,0,0,yes\r\n"))
        code, out, _ = self.run_cli("report", "inventory", "--format", "json")
        self.assertEqual(json.loads(out)["rows"][0]["sku"], "PEN-1")
        code, text, _ = self.run_cli("report", "inventory")
        self.assertTrue(text.startswith("Inventory\n"))


if __name__ == "__main__":
    unittest.main()
