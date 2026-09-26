import unittest
from decimal import Decimal

from shop.util.money import format_cents, percent_of, split_evenly, to_cents


class MoneyTests(unittest.TestCase):
    def test_to_cents(self):
        self.assertEqual(to_cents("12.5"), 1250)
        self.assertEqual(to_cents(7), 700)
        self.assertEqual(to_cents(Decimal("3.999")), 400)
        self.assertEqual(to_cents(" 1.00 "), 100)

    def test_to_cents_rounds_half_up(self):
        self.assertEqual(to_cents("0.125"), 13)
        self.assertEqual(to_cents("0.105"), 11)
        self.assertEqual(to_cents("-0.125"), -13)

    def test_to_cents_errors(self):
        with self.assertRaises(TypeError):
            to_cents(1.5)
        with self.assertRaises(ValueError):
            to_cents("abc")

    def test_format_cents(self):
        self.assertEqual(format_cents(1250), "CHF 12.50")
        self.assertEqual(format_cents(5), "CHF 0.05")
        self.assertEqual(format_cents(-5), "-CHF 0.05")
        self.assertEqual(format_cents(123456789), "CHF 1'234'567.89")
        self.assertEqual(format_cents(100, "EUR"), "EUR 1.00")

    def test_percent_of(self):
        self.assertEqual(percent_of(1000, 10), 100)
        self.assertEqual(percent_of(1005, 10), 101)   # 100.5 rounds up
        self.assertEqual(percent_of(999, "8.1"), 81)  # 80.919
        self.assertEqual(percent_of(1234, Decimal("50")), 617)

    def test_split_evenly(self):
        self.assertEqual(split_evenly(100, 3), [34, 33, 33])
        self.assertEqual(split_evenly(101, 4), [26, 25, 25, 25])
        self.assertEqual(split_evenly(90, 3), [30, 30, 30])
        self.assertEqual(sum(split_evenly(1001, 7)), 1001)
        with self.assertRaises(ValueError):
            split_evenly(10, 0)


if __name__ == "__main__":
    unittest.main()
