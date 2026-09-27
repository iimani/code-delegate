import unittest

from shop.errors import CONFLICT, INVALID, NOT_FOUND
from shop.models.order import CANCELLED
from tests.support import make_app, seed


class HiddenSearchTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = make_app()
        self.d = seed(self.app)

    def test_search(self):
        found, err = self.app.product_service.search("PA")
        self.assertIsNone(err)
        self.assertEqual([p.sku for p in found], ["PAD-001"])
        found, _ = self.app.product_service.search("  pen ")
        self.assertEqual([p.sku for p in found], ["PEN-001"])
        found, _ = self.app.product_service.search("-001")
        self.assertEqual([p.sku for p in found], ["INK-001", "PAD-001", "PEN-001"])
        found, _ = self.app.product_service.search("bottle")
        self.assertEqual([p.sku for p in found], ["INK-001"])

    def test_search_skips_inactive_and_rejects_blank(self):
        self.app.product_service.deactivate(self.d["ink"].id)
        found, _ = self.app.product_service.search("ink")
        self.assertEqual(found, [])
        for q in ("", "   "):
            _, err = self.app.product_service.search(q)
            self.assertEqual(err.kind, INVALID)

    def test_api(self):
        r = self.app.handle("GET", "/products?q=pad")
        self.assertEqual((r.status, [p["sku"] for p in r.body]), (200, ["PAD-001"]))
        self.assertEqual(self.app.handle("GET", "/products?q=%20").status, 400)
        self.assertEqual(len(self.app.handle("GET", "/products").body), 3)


class HiddenEmailTests(unittest.TestCase):
    def test_normalized(self):
        app, _ = make_app()
        c, err = app.customer_service.create("Bob", "  Bob@Example.COM ")
        self.assertIsNone(err)
        self.assertEqual(c.email, "bob@example.com")
        self.assertEqual(app.customer_repo.get(c.id).email, "bob@example.com")
        _, err = app.customer_service.create("Bobby", "BOB@example.com")
        self.assertEqual(err.kind, CONFLICT)
        _, err = app.customer_service.create("X", "  not an email ")
        self.assertEqual(err.kind, INVALID)


class HiddenCancelTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = make_app()
        self.d = seed(self.app)
        self.order, _ = self.app.order_service.place(self.d["alice"].id, [(self.d["pen"].id, 3), (self.d["pad"].id, 2)])

    def level(self, key):
        return self.app.inventory_service.level(self.d[key].id)[0]

    def test_cancel_releases_stock(self):
        self.assertEqual((self.level("pen").reserved, self.level("pad").reserved), (3, 2))
        order, err = self.app.order_service.cancel(self.order.id)
        self.assertIsNone(err)
        self.assertEqual(order.status, CANCELLED)
        self.assertEqual(CANCELLED, "cancelled")
        self.assertEqual(self.app.order_service.get(self.order.id)[0].status, "cancelled")
        self.assertEqual((self.level("pen").reserved, self.level("pad").reserved), (0, 0))

    def test_cancel_errors(self):
        self.app.order_service.cancel(self.order.id)
        _, err = self.app.order_service.cancel(self.order.id)
        self.assertEqual(err.kind, CONFLICT)
        self.assertEqual(self.level("pen").reserved, 0)
        _, err = self.app.order_service.cancel("ord_missing")
        self.assertEqual(err.kind, NOT_FOUND)

    def test_api(self):
        r = self.app.handle("POST", f"/orders/{self.order.id}/cancel")
        self.assertEqual((r.status, r.body["status"]), (200, "cancelled"))
        self.assertEqual(self.app.handle("POST", f"/orders/{self.order.id}/cancel").status, 409)
        self.assertEqual(self.app.handle("POST", "/orders/ord_x/cancel").status, 404)


class HiddenTestFiles(unittest.TestCase):
    def test_written(self):
        import pathlib
        here = pathlib.Path(__file__).resolve().parent
        for name in ("test_search.py", "test_email_normalization.py", "test_cancel.py"):
            self.assertTrue((here / name).exists(), f"tests/{name} missing")


if __name__ == "__main__":
    unittest.main()
