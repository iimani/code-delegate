import unittest

from tests.support import make_app, seed


class SearchTests(unittest.TestCase):
    def test_search(self):
        app, _ = make_app()
        seed(app)
        found, err = app.product_service.search("pad")
        self.assertIsNone(err)
        self.assertEqual([p.sku for p in found], ["PAD-001"])
        self.assertEqual(app.handle("GET", "/products?q=").status, 400)


if __name__ == "__main__":
    unittest.main()
