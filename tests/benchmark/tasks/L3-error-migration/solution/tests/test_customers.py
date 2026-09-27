import unittest

from shop.errors import ConflictError, NotFoundError, ValidationError
from tests.support import START, make_app


class CustomerServiceTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = make_app()
        self.svc = self.app.customer_service

    def test_create_and_get(self):
        customer = self.svc.create("  Alice   Adams ", "alice@example.com")
        self.assertEqual(customer.name, "Alice Adams")
        self.assertEqual(customer.created_at, START)
        self.assertTrue(customer.id.startswith("cus_"))
        self.assertEqual(self.svc.get(customer.id), customer)

    def test_invalid_input(self):
        for name, email in (("", "a@example.com"), ("Al", "not-an-email"), ("Al", "a@b")):
            with self.assertRaises(ValidationError):
                self.svc.create(name, email)

    def test_duplicate_email(self):
        self.svc.create("Alice", "alice@example.com")
        with self.assertRaises(ConflictError):
            self.svc.create("Alice Again", "alice@example.com")

    def test_missing(self):
        with self.assertRaises(NotFoundError):
            self.svc.get("cus_missing")

    def test_list(self):
        self.svc.create("A", "a@example.com")
        self.svc.create("B", "b@example.com")
        self.assertEqual([c.name for c in self.svc.list()], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
