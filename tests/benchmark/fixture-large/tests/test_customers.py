import unittest

from shop.errors import CONFLICT, INVALID, NOT_FOUND
from tests.support import START, make_app


class CustomerServiceTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = make_app()
        self.svc = self.app.customer_service

    def test_create_and_get(self):
        customer, err = self.svc.create("  Alice   Adams ", "alice@example.com")
        self.assertIsNone(err)
        self.assertEqual(customer.name, "Alice Adams")
        self.assertEqual(customer.created_at, START)
        self.assertTrue(customer.id.startswith("cus_"))
        found, err = self.svc.get(customer.id)
        self.assertIsNone(err)
        self.assertEqual(found, customer)

    def test_invalid_input(self):
        for name, email in (("", "a@example.com"), ("Al", "not-an-email"), ("Al", "a@b")):
            customer, err = self.svc.create(name, email)
            self.assertIsNone(customer)
            self.assertEqual(err.kind, INVALID)

    def test_duplicate_email(self):
        self.svc.create("Alice", "alice@example.com")
        _, err = self.svc.create("Alice Again", "alice@example.com")
        self.assertEqual(err.kind, CONFLICT)

    def test_missing(self):
        _, err = self.svc.get("cus_missing")
        self.assertEqual(err.kind, NOT_FOUND)

    def test_list(self):
        self.svc.create("A", "a@example.com")
        self.svc.create("B", "b@example.com")
        customers, err = self.svc.list()
        self.assertIsNone(err)
        self.assertEqual([c.name for c in customers], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
