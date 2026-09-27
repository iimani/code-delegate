import unittest
from datetime import date, datetime

from shop.reports.base import Report, render_text
from shop.reports.customers import top_customers_report
from shop.reports.inventory import inventory_report
from shop.reports.sales import sales_report
from tests.support import make_app, seed


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.app, self.clock = make_app()
        self.d = seed(self.app)

    def test_inventory_report(self):
        report = inventory_report(self.app)
        self.assertEqual([r["sku"] for r in report.rows], ["INK-001", "PAD-001", "PEN-001"])
        pad = report.rows[1]
        self.assertEqual((pad["available"], pad["low_stock"]), (3, "yes"))
        self.assertEqual(report.rows[2]["low_stock"], "no")

    def test_top_customers(self):
        self.app.order_service.place(self.d["bob"].id, [(self.d["pen"].id, 5)])
        self.app.order_service.place(self.d["alice"].id, [(self.d["pen"].id, 1)])
        report = top_customers_report(self.app)
        self.assertEqual([r["name"] for r in report.rows], ["Bob Brown", "Alice Adams"])
        self.assertEqual(report.rows[0]["orders"], 1)

    def test_sales_report_counts_orders_per_day(self):
        self.clock.set(datetime(2026, 3, 2, 9, 30))
        self.app.order_service.place(self.d["alice"].id, [(self.d["pen"].id, 1)])
        self.app.order_service.place(self.d["bob"].id, [(self.d["pen"].id, 2)])
        report = sales_report(self.app, date(2026, 3, 2), date(2026, 3, 4))
        self.assertEqual([r["date"] for r in report.rows], ["2026-03-02", "2026-03-03", "2026-03-04"])
        self.assertEqual([r["orders"] for r in report.rows], [2, 0, 0])
        self.assertGreater(report.rows[0]["revenue_cents"], 0)

    def test_sales_report_includes_last_day(self):
        self.clock.set(datetime(2026, 3, 3, 18, 0))
        self.app.order_service.place(self.d["alice"].id, [(self.d["pen"].id, 1)])
        report = sales_report(self.app, date(2026, 3, 3), date(2026, 3, 3))
        self.assertEqual(report.rows[0]["orders"], 1)

    def test_render_text(self):
        text = render_text(Report("T", ["a", "bb"], [{"a": 1, "bb": "x"}, {"a": 22, "bb": "yy"}]))
        self.assertEqual(text, "T\na   bb\n--  --\n1   x\n22  yy\n")


if __name__ == "__main__":
    unittest.main()
