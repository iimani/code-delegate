import unittest
from datetime import date

from shop.errors import ConflictError, NotFoundError, ValidationError
from tests.support import make_app, seed


class OrderServiceTests(unittest.TestCase):
    def setUp(self):
        self.app, self.clock = make_app()
        self.d = seed(self.app)
        self.svc = self.app.order_service

    def test_place_prices_and_reserves(self):
        order = self.svc.place(self.d["alice"].id, [(self.d["pen"].id, 4), (self.d["pad"].id, 1)])
        self.assertEqual(order.subtotal_cents, 4 * 250 + 490)
        self.assertEqual(order.total_cents, order.subtotal_cents - order.discount_cents + order.vat_cents)
        self.assertEqual(order.status, "placed")
        self.assertEqual(self.app.inventory_service.level(self.d["pen"].id).reserved, 4)
        self.assertEqual(self.svc.get(order.id), order)

    def test_discount_code_is_recorded_normalized(self):
        order = self.svc.place(self.d["alice"].id, [(self.d["pen"].id, 1)], " welcome10 ")
        self.assertEqual(order.discount_code, "WELCOME10")
        self.assertGreater(order.discount_cents, 0)

    def test_failures(self):
        alice, pen, pad = self.d["alice"].id, self.d["pen"].id, self.d["pad"].id
        cases = [
            (("cus_missing", [(pen, 1)]), NotFoundError),
            ((alice, []), ValidationError),
            ((alice, [(pen, 1), (pen, 2)]), ValidationError),
            ((alice, [("prd_missing", 1)]), NotFoundError),
            ((alice, [(pen, 0)]), ValidationError),
            ((alice, [(pad, 4)]), ConflictError),
        ]
        for args, exc in cases:
            with self.assertRaises(exc, msg=args):
                self.svc.place(*args)

    def test_failed_order_releases_earlier_reservations(self):
        with self.assertRaises(ConflictError):
            self.svc.place(self.d["alice"].id, [(self.d["pen"].id, 2), (self.d["pad"].id, 9)])
        self.assertEqual(self.app.inventory_service.level(self.d["pen"].id).reserved, 0)

    def test_unknown_code_is_invalid(self):
        with self.assertRaises(ValidationError):
            self.svc.place(self.d["alice"].id, [(self.d["pen"].id, 1)], "NOPE")

    def test_inactive_product(self):
        self.app.product_service.deactivate(self.d["pen"].id)
        with self.assertRaises(ValidationError):
            self.svc.place(self.d["alice"].id, [(self.d["pen"].id, 1)])

    def test_list_for_customer(self):
        self.svc.place(self.d["alice"].id, [(self.d["pen"].id, 1)])
        self.assertEqual(len(self.svc.list_for_customer(self.d["alice"].id)), 1)
        self.assertEqual(self.svc.list_for_customer(self.d["bob"].id), [])

    def test_list_between_rejects_reversed_range(self):
        with self.assertRaises(ValidationError):
            self.svc.list_between(date(2026, 3, 5), date(2026, 3, 1))


if __name__ == "__main__":
    unittest.main()
