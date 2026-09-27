import unittest

from shop.errors import ConflictError, NotFoundError, ValidationError
from tests.support import make_app, seed


class InventoryServiceTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = make_app()
        self.data = seed(self.app)
        self.svc = self.app.inventory_service

    def test_receive_reserve_release(self):
        pen = self.data["pen"].id
        level = self.svc.reserve(pen, 5)
        self.assertEqual((level.on_hand, level.reserved, level.available), (20, 5, 15))
        self.assertEqual(self.svc.release(pen, 2).reserved, 3)

    def test_cannot_over_reserve(self):
        with self.assertRaises(ConflictError):
            self.svc.reserve(self.data["pad"].id, 4)

    def test_invalid_quantities(self):
        pen = self.data["pen"].id
        for qty in (0, -1, 10_001):
            with self.assertRaises(ValidationError):
                self.svc.receive(pen, qty)
        with self.assertRaises(ValidationError):
            self.svc.release(pen, 1)

    def test_unknown_product(self):
        with self.assertRaises(NotFoundError):
            self.svc.receive("prd_missing", 1)


if __name__ == "__main__":
    unittest.main()
