import unittest

from shop.models import OrderLine
from shop.services.pricing import discount_percent, normalize_code, price_order


class PricingTests(unittest.TestCase):
    def test_normalize_code(self):
        self.assertEqual(normalize_code(" welcome10 "), "WELCOME10")
        self.assertIsNone(normalize_code(None))
        self.assertIsNone(normalize_code("   "))

    def test_discount_percent(self):
        self.assertEqual(discount_percent(None, 1), 0)
        self.assertEqual(discount_percent("", 1), 0)
        self.assertEqual(discount_percent("WELCOME10", 1), 10)
        self.assertEqual(discount_percent("spring15", 1), 15)
        self.assertEqual(discount_percent("BULK5", 10), 5)
        with self.assertRaises(ValueError):
            discount_percent("BULK5", 9)
        with self.assertRaises(ValueError):
            discount_percent("NOPE", 1)

    def test_price_without_code(self):
        p = price_order([OrderLine("a", 2, 500), OrderLine("b", 1, 1000)])
        self.assertEqual(p, (2000, 0, 162, 2162))

    def test_vat_on_discounted_amount(self):
        p = price_order([OrderLine("a", 1, 1000)], "WELCOME10")
        self.assertEqual(p, (1000, 100, 73, 973))  # 8.1 % of 900 = 72.9 -> 73

    def test_bulk(self):
        p = price_order([OrderLine("a", 10, 100)], "bulk5")
        self.assertEqual(p.discount_cents, 50)
        self.assertEqual(p.total_cents, 950 + 77)  # 8.1 % of 950 = 76.95 -> 77

    def test_empty_code_means_none(self):
        self.assertEqual(price_order([OrderLine("a", 1, 100)], "  ").discount_cents, 0)


if __name__ == "__main__":
    unittest.main()
