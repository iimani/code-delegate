import importlib
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class HiddenRenameTests(unittest.TestCase):
    def test_new_name_works(self):
        from app.pricing import order_subtotal
        self.assertEqual(order_subtotal([("a", 2, 1.25), ("b", 1, 0.5)]), 3.0)
        self.assertEqual(order_subtotal([]), 0)

    def test_old_name_gone(self):
        pricing = importlib.import_module("app.pricing")
        self.assertFalse(hasattr(pricing, "calc_total"))
        offenders = [str(p.relative_to(ROOT))
                     for folder in ("app", "tests")
                     for p in (ROOT / folder).rglob("*.py")
                     if not p.name.startswith("test_hidden_")
                     and "calc_total" in p.read_text()]
        self.assertEqual(offenders, [])

    def test_orders_unchanged(self):
        from app.orders import Order
        self.assertEqual(Order([("a", 1, 10.0)], discount_percent=10).total(), 9.0)
        self.assertEqual(Order([("a", 2, 2.5), ("b", 1, 1.0)]).summary(), "2 items, total 6.00")

    def test_other_names_kept(self):
        from app.pricing import apply_discount, LineItem  # noqa: F401
        self.assertEqual(apply_discount(100, 50), 50)


if __name__ == "__main__":
    unittest.main()
