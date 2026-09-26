import unittest

from tests.support import make_app, seed


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = make_app()
        self.d = seed(self.app)

    def test_customer_endpoints(self):
        resp = self.app.handle("POST", "/customers", {"name": "Cara", "email": "cara@example.com"})
        self.assertEqual(resp.status, 201)
        cid = resp.body["id"]
        self.assertEqual(self.app.handle("GET", f"/customers/{cid}").body["email"], "cara@example.com")
        self.assertEqual(len(self.app.handle("GET", "/customers").body), 3)
        dup = self.app.handle("POST", "/customers", {"name": "C", "email": "cara@example.com"})
        self.assertEqual((dup.status, dup.body["error"]), (409, "conflict"))
        self.assertEqual(self.app.handle("GET", "/customers/cus_x").status, 404)

    def test_product_endpoints(self):
        resp = self.app.handle("POST", "/products", {"sku": "CUP-1", "name": "Cup", "price": "3.20"})
        self.assertEqual((resp.status, resp.body["price_cents"]), (201, 320))
        pid = resp.body["id"]
        self.assertEqual(self.app.handle("POST", f"/products/{pid}/receive", {"quantity": 7}).body["available"], 7)
        self.assertEqual(self.app.handle("POST", f"/products/{pid}/receive", {"quantity": "7"}).status, 400)
        self.assertEqual(self.app.handle("POST", f"/products/{pid}/price", {"price": "3.5"}).body["price_cents"], 350)
        self.assertEqual(self.app.handle("POST", f"/products/{pid}/deactivate").body["active"], False)
        active = self.app.handle("GET", "/products?active=1").body
        self.assertNotIn(pid, [p["id"] for p in active])
        self.assertEqual(self.app.handle("GET", f"/products/{pid}/stock").body["on_hand"], 7)

    def test_order_endpoints(self):
        body = {"customer_id": self.d["alice"].id, "items": [{"product_id": self.d["pen"].id, "quantity": 2}]}
        resp = self.app.handle("POST", "/orders", body)
        self.assertEqual(resp.status, 201)
        self.assertEqual(self.app.handle("GET", f"/orders/{resp.body['id']}").body["lines"][0]["quantity"], 2)
        self.assertEqual(len(self.app.handle("GET", f"/customers/{self.d['alice'].id}/orders").body), 1)
        self.assertEqual(self.app.handle("POST", "/orders", {"items": "x"}).status, 400)

    def test_routing_errors(self):
        self.assertEqual(self.app.handle("GET", "/nowhere").status, 404)
        self.assertEqual(self.app.handle("DELETE", "/customers").status, 405)


if __name__ == "__main__":
    unittest.main()
