import unittest

from shop.errors import CONFLICT, INVALID, NOT_FOUND
from tests.support import make_app, seed


class InventoryServiceTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = make_app()
        self.data = seed(self.app)
        self.svc = self.app.inventory_service

    def test_receive_reserve_release(self):
        pen = self.data["pen"].id
        level, err = self.svc.reserve(pen, 5)
        self.assertIsNone(err)
        self.assertEqual((level.on_hand, level.reserved, level.available), (20, 5, 15))
        level, _ = self.svc.release(pen, 2)
        self.assertEqual(level.reserved, 3)

    def test_cannot_over_reserve(self):
        _, err = self.svc.reserve(self.data["pad"].id, 4)
        self.assertEqual(err.kind, CONFLICT)

    def test_invalid_quantities(self):
        pen = self.data["pen"].id
        for qty in (0, -1, 10_001):
            _, err = self.svc.receive(pen, qty)
            self.assertEqual(err.kind, INVALID)
        _, err = self.svc.release(pen, 1)
        self.assertEqual(err.kind, INVALID)

    def test_unknown_product(self):
        _, err = self.svc.receive("prd_missing", 1)
        self.assertEqual(err.kind, NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
