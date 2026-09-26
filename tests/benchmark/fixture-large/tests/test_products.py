import unittest

from shop.errors import CONFLICT, INVALID, NOT_FOUND
from tests.support import make_app


class ProductServiceTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = make_app()
        self.svc = self.app.product_service

    def test_create_normalizes_and_stocks(self):
        product, err = self.svc.create(" pen-001 ", "Blue  pen", "2.5")
        self.assertIsNone(err)
        self.assertEqual((product.sku, product.name, product.price_cents, product.active),
                         ("PEN-001", "Blue pen", 250, True))
        level, _ = self.app.inventory_service.level(product.id)
        self.assertEqual((level.on_hand, level.reserved), (0, 0))

    def test_invalid(self):
        for sku, name, price in (("x", "Pen", "1"), ("PEN-1", "", "1"), ("PEN-1", "Pen", "0"),
                                 ("PEN-1", "Pen", "abc")):
            product, err = self.svc.create(sku, name, price)
            self.assertIsNone(product)
            self.assertEqual(err.kind, INVALID, (sku, name, price))

    def test_duplicate_sku(self):
        self.svc.create("PEN-1", "Pen", "1")
        _, err = self.svc.create("pen-1", "Other", "1")
        self.assertEqual(err.kind, CONFLICT)

    def test_change_price_and_deactivate(self):
        product, _ = self.svc.create("PEN-1", "Pen", "1")
        updated, err = self.svc.change_price(product.id, "1.99")
        self.assertIsNone(err)
        self.assertEqual(updated.price_cents, 199)
        _, err = self.svc.deactivate(product.id)
        self.assertIsNone(err)
        _, err = self.svc.deactivate(product.id)
        self.assertEqual(err.kind, CONFLICT)
        active, _ = self.svc.list(active_only=True)
        self.assertEqual(active, [])

    def test_missing(self):
        _, err = self.svc.change_price("prd_missing", "1")
        self.assertEqual(err.kind, NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
