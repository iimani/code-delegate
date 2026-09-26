import unittest

from tests.support import make_app, seed


class CancelTests(unittest.TestCase):
    def test_cancel(self):
        app, _ = make_app()
        d = seed(app)
        order, _ = app.order_service.place(d["alice"].id, [(d["pen"].id, 2)])
        cancelled, err = app.order_service.cancel(order.id)
        self.assertIsNone(err)
        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(app.inventory_service.level(d["pen"].id)[0].reserved, 0)


if __name__ == "__main__":
    unittest.main()
