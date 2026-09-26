import unittest
from datetime import date

from shop.errors import CONFLICT, INVALID, NOT_FOUND
from tests.support import make_app, seed


class OrderServiceTests(unittest.TestCase):
    def setUp(self):
        self.app, self.clock = make_app()
        self.d = seed(self.app)
        self.svc = self.app.order_service

    def test_place_prices_and_reserves(self):
        order, err = self.svc.place(self.d["alice"].id, [(self.d["pen"].id, 4), (self.d["pad"].id, 1)])
        self.assertIsNone(err)
        self.assertEqual(order.subtotal_cents, 4 * 250 + 490)
        self.assertEqual(order.total_cents, order.subtotal_cents - order.discount_cents + order.vat_cents)
        self.assertEqual(order.status, "placed")
        level, _ = self.app.inventory_service.level(self.d["pen"].id)
        self.assertEqual(level.reserved, 4)
        stored, _ = self.svc.get(order.id)
        self.assertEqual(stored, order)

    def test_discount_code_is_recorded_normalized(self):
        order, err = self.svc.place(self.d["alice"].id, [(self.d["pen"].id, 1)], " welcome10 ")
        self.assertIsNone(err)
        self.assertEqual(order.discount_code, "WELCOME10")
        self.assertGreater(order.discount_cents, 0)

    def test_failures(self):
        alice, pen, pad = self.d["alice"].id, self.d["pen"].id, self.d["pad"].id
        cases = [
            (("cus_missing", [(pen, 1)]), NOT_FOUND),
            ((alice, []), INVALID),
            ((alice, [(pen, 1), (pen, 2)]), INVALID),
            ((alice, [("prd_missing", 1)]), NOT_FOUND),
            ((alice, [(pen, 0)]), INVALID),
            ((alice, [(pad, 4)]), CONFLICT),
        ]
        for args, kind in cases:
            order, err = self.svc.place(*args)
            self.assertIsNone(order)
            self.assertEqual(err.kind, kind, args)

    def test_failed_order_releases_earlier_reservations(self):
        _, err = self.svc.place(self.d["alice"].id, [(self.d["pen"].id, 2), (self.d["pad"].id, 9)])
        self.assertEqual(err.kind, CONFLICT)
        level, _ = self.app.inventory_service.level(self.d["pen"].id)
        self.assertEqual(level.reserved, 0)

    def test_unknown_code_is_invalid(self):
        _, err = self.svc.place(self.d["alice"].id, [(self.d["pen"].id, 1)], "NOPE")
        self.assertEqual(err.kind, INVALID)

    def test_inactive_product(self):
        self.app.product_service.deactivate(self.d["pen"].id)
        _, err = self.svc.place(self.d["alice"].id, [(self.d["pen"].id, 1)])
        self.assertEqual(err.kind, INVALID)

    def test_list_for_customer(self):
        self.svc.place(self.d["alice"].id, [(self.d["pen"].id, 1)])
        orders, _ = self.svc.list_for_customer(self.d["alice"].id)
        self.assertEqual(len(orders), 1)
        orders, _ = self.svc.list_for_customer(self.d["bob"].id)
        self.assertEqual(orders, [])

    def test_list_between_rejects_reversed_range(self):
        _, err = self.svc.list_between(date(2026, 3, 5), date(2026, 3, 1))
        self.assertEqual(err.kind, INVALID)


if __name__ == "__main__":
    unittest.main()
