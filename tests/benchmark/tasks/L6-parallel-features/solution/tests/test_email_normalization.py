import unittest

from tests.support import make_app


class EmailTests(unittest.TestCase):
    def test_lowercased(self):
        app, _ = make_app()
        c, _ = app.customer_service.create("A", " A@Example.com ")
        self.assertEqual(c.email, "a@example.com")
        _, err = app.customer_service.create("B", "a@EXAMPLE.com")
        self.assertEqual(err.kind, "conflict")


if __name__ == "__main__":
    unittest.main()
