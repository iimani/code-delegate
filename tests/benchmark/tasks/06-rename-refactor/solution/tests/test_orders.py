import unittest

from app.orders import Order
from app.pricing import order_subtotal


class OrderTests(unittest.TestCase):
    def test_total_without_discount(self):
        order = Order([("a", 2, 1.50), ("b", 1, 4.00)])
        self.assertEqual(order.total(), 7.00)

    def test_total_with_discount(self):
        order = Order([("a", 1, 10.00)], discount_percent=25)
        self.assertEqual(order.total(), 7.50)

    def test_order_subtotal_rounds_to_cents(self):
        self.assertEqual(order_subtotal([("x", 3, 0.1)]), 0.3)

    def test_summary(self):
        self.assertEqual(Order([("a", 1, 2.0)]).summary(), "1 items, total 2.00")


if __name__ == "__main__":
    unittest.main()
