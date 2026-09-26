import unittest
from datetime import date, datetime, time

from shop.util.dates import add_business_days, day_bounds, days_between, from_iso, parse_date, to_iso


class DatesTests(unittest.TestCase):
    def test_parse_date(self):
        self.assertEqual(parse_date("2026-03-02"), date(2026, 3, 2))
        self.assertEqual(parse_date(" 2026-03-02 "), date(2026, 3, 2))
        for bad in ("02.03.2026", "2026-13-01", ""):
            with self.assertRaises(ValueError):
                parse_date(bad)

    def test_day_bounds(self):
        start, end = day_bounds(date(2026, 3, 2))
        self.assertEqual(start, datetime(2026, 3, 2, 0, 0, 0))
        self.assertEqual(end, datetime.combine(date(2026, 3, 2), time.max))
        self.assertEqual(end.microsecond, 999999)

    def test_iso_roundtrip(self):
        moment = datetime(2026, 3, 2, 10, 5, 7, 123456)
        self.assertEqual(to_iso(moment), "2026-03-02T10:05:07")
        self.assertEqual(from_iso("2026-03-02T10:05:07"), datetime(2026, 3, 2, 10, 5, 7))

    def test_add_business_days(self):
        friday = date(2026, 3, 6)
        self.assertEqual(add_business_days(friday, 1), date(2026, 3, 9))
        self.assertEqual(add_business_days(friday, 5), date(2026, 3, 13))
        self.assertEqual(add_business_days(date(2026, 3, 9), -1), friday)
        self.assertEqual(add_business_days(friday, 0), friday)

    def test_days_between(self):
        self.assertEqual(days_between(date(2026, 3, 1), date(2026, 3, 1)), 1)
        self.assertEqual(days_between(date(2026, 3, 1), date(2026, 3, 31)), 31)
        self.assertEqual(days_between(date(2026, 3, 5), date(2026, 3, 1)), 0)


if __name__ == "__main__":
    unittest.main()
