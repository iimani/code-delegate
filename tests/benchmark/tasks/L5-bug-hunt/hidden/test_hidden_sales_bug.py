import unittest
from datetime import date, datetime

from shop.reports.sales import sales_report
from tests.support import make_app, seed


class HiddenSalesBugTests(unittest.TestCase):
    def setUp(self):
        self.app, self.clock = make_app()
        self.d = seed(self.app)

    def order_at(self, moment, qty=1):
        self.clock.set(moment)
        order, err = self.app.order_service.place(self.d["alice"].id, [(self.d["pen"].id, qty)])
        self.assertIsNone(err)
        return order

    def test_single_day(self):
        o = self.order_at(datetime(2026, 3, 2, 10, 0))
        report = sales_report(self.app, date(2026, 3, 2), date(2026, 3, 2))
        self.assertEqual(report.rows, [{"date": "2026-03-02", "orders": 1, "revenue_cents": o.total_cents}])

    def test_last_day_of_range_and_boundaries(self):
        self.order_at(datetime(2026, 3, 1, 0, 0, 0))
        self.order_at(datetime(2026, 3, 2, 12, 0))
        self.order_at(datetime(2026, 3, 3, 23, 59, 59))
        self.order_at(datetime(2026, 3, 4, 0, 0, 0))
        report = sales_report(self.app, date(2026, 3, 1), date(2026, 3, 3))
        self.assertEqual([r["orders"] for r in report.rows], [1, 1, 1])

    def test_repository_bounds(self):
        o = self.order_at(datetime(2026, 3, 2, 10, 0))
        found = self.app.order_repo.list_between(datetime(2026, 3, 2, 0, 0), datetime(2026, 3, 2, 23, 59, 59))
        self.assertEqual([x.id for x in found], [o.id])
        self.assertEqual(self.app.order_repo.list_between(datetime(2026, 3, 2, 10, 0), datetime(2026, 3, 2, 10, 0))[0].id, o.id)
        self.assertEqual(self.app.order_repo.list_between(datetime(2026, 3, 2, 10, 0, 1), datetime(2026, 3, 3)), [])

    def test_service_range(self):
        self.order_at(datetime(2026, 3, 2, 23, 59, 59))
        orders, err = self.app.order_service.list_between(date(2026, 3, 2), date(2026, 3, 2))
        self.assertIsNone(err)
        self.assertEqual(len(orders), 1)


if __name__ == "__main__":
    unittest.main()
