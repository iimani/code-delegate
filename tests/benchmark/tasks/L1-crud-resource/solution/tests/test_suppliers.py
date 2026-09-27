import unittest

from shop.errors import CONFLICT, INVALID
from tests.support import make_app


class SupplierTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = make_app()

    def test_create_and_list(self):
        s, err = self.app.supplier_service.create("Acme", "a@acme.example", "ch")
        self.assertIsNone(err)
        self.assertEqual(s.country, "CH")
        suppliers, _ = self.app.supplier_service.list()
        self.assertEqual(suppliers, [s])

    def test_errors(self):
        _, err = self.app.supplier_service.create("Acme", "a@acme.example", "CHE")
        self.assertEqual(err.kind, INVALID)
        self.app.supplier_service.create("Acme", "a@acme.example", "CH")
        _, err = self.app.supplier_service.create("Other", "a@acme.example", "CH")
        self.assertEqual(err.kind, CONFLICT)

    def test_api(self):
        resp = self.app.handle("POST", "/suppliers", {"name": "Acme", "email": "a@acme.example", "country": "DE"})
        self.assertEqual(resp.status, 201)


if __name__ == "__main__":
    unittest.main()
