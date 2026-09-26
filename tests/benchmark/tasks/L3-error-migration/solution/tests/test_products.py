import unittest

from shop.errors import ConflictError, NotFoundError, ValidationError
from tests.support import make_app


class ProductServiceTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = make_app()
        self.svc = self.app.product_service

    def test_create_normalizes_and_stocks(self):
        product = self.svc.create(" pen-001 ", "Blue  pen", "2.5")
        self.assertEqual((product.sku, product.name, product.price_cents, product.active),
                         ("PEN-001", "Blue pen", 250, True))
        level = self.app.inventory_service.level(product.id)
        self.assertEqual((level.on_hand, level.reserved), (0, 0))

    def test_invalid(self):
        for sku, name, price in (("x", "Pen", "1"), ("PEN-1", "", "1"), ("PEN-1", "Pen", "0"),
                                 ("PEN-1", "Pen", "abc")):
            with self.assertRaises(ValidationError, msg=(sku, name, price)):
                self.svc.create(sku, name, price)

    def test_duplicate_sku(self):
        self.svc.create("PEN-1", "Pen", "1")
        with self.assertRaises(ConflictError):
            self.svc.create("pen-1", "Other", "1")

    def test_change_price_and_deactivate(self):
        product = self.svc.create("PEN-1", "Pen", "1")
        self.assertEqual(self.svc.change_price(product.id, "1.99").price_cents, 199)
        self.svc.deactivate(product.id)
        with self.assertRaises(ConflictError):
            self.svc.deactivate(product.id)
        self.assertEqual(self.svc.list(active_only=True), [])

    def test_missing(self):
        with self.assertRaises(NotFoundError):
            self.svc.change_price("prd_missing", "1")


if __name__ == "__main__":
    unittest.main()
