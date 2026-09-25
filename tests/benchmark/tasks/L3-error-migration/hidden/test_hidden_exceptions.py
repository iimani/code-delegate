import ast
import io
import os
import pathlib
import tempfile
import unittest
from datetime import date

from shop import errors
from shop.cli.main import main
from shop.errors import ConflictError, NotFoundError, ServiceError, ValidationError
from shop.reports.sales import sales_report
from tests.support import make_app

ROOT = pathlib.Path(__file__).resolve().parent.parent


class HiddenErrorTypesTests(unittest.TestCase):
    def test_hierarchy(self):
        for cls, kind in ((NotFoundError, "not_found"), (ValidationError, "invalid"), (ConflictError, "conflict")):
            self.assertTrue(issubclass(cls, ServiceError))
            self.assertTrue(issubclass(ServiceError, Exception))
            exc = cls("boom")
            self.assertEqual((exc.kind, exc.message, str(exc)), (kind, "boom", "boom"))

    def test_tuple_api_removed(self):
        for name in ("ok", "fail", "Error", "Result"):
            self.assertFalse(hasattr(errors, name), f"shop.errors.{name} should be removed")
        self.assertEqual((errors.NOT_FOUND, errors.INVALID, errors.CONFLICT), ("not_found", "invalid", "conflict"))

    def test_no_tuple_convention_left(self):
        offenders = []
        for path in (ROOT / "shop").rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "shop.errors":
                    bad = {a.name for a in node.names} & {"ok", "fail", "Error", "Result"}
                    if bad:
                        offenders.append(f"{path.relative_to(ROOT)} imports {sorted(bad)}")
                if (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Tuple)
                        and len(node.targets[0].elts) == 2 and isinstance(node.value, ast.Call)
                        and isinstance(node.targets[0].elts[1], ast.Name)
                        and node.targets[0].elts[1].id in ("err", "e", "_")
                        and isinstance(node.value.func, ast.Attribute)
                        and "service" in ast.dump(node.value.func.value)):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} unpacks a service result")
        self.assertEqual(offenders, [])


class HiddenServiceTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = make_app()
        a = self.app
        self.alice = a.customer_service.create("Alice", "alice@example.com")
        self.pen = a.product_service.create("PEN-1", "Pen", "2.00")
        self.pad = a.product_service.create("PAD-1", "Pad", "1.00")
        a.inventory_service.receive(self.pen.id, 10)
        a.inventory_service.receive(self.pad.id, 1)

    def test_values_returned_directly(self):
        self.assertEqual(self.alice.email, "alice@example.com")
        self.assertEqual(self.app.customer_service.get(self.alice.id), self.alice)
        self.assertEqual([c.id for c in self.app.customer_service.list()], [self.alice.id])
        self.assertEqual(self.app.product_service.change_price(self.pen.id, "2.50").price_cents, 250)
        self.assertEqual(self.app.inventory_service.level(self.pen.id).available, 10)
        order = self.app.order_service.place(self.alice.id, [(self.pen.id, 2)])
        self.assertEqual(self.app.order_service.get(order.id).id, order.id)
        self.assertEqual(len(self.app.order_service.list_for_customer(self.alice.id)), 1)

    def test_raises(self):
        a = self.app
        cases = [
            (lambda: a.customer_service.create("", "x@example.com"), ValidationError),
            (lambda: a.customer_service.create("B", "alice@example.com"), ConflictError),
            (lambda: a.customer_service.get("cus_x"), NotFoundError),
            (lambda: a.product_service.create("PEN-1", "Dup", "1"), ConflictError),
            (lambda: a.product_service.create("P", "Bad", "1"), ValidationError),
            (lambda: a.product_service.change_price("prd_x", "1"), NotFoundError),
            (lambda: a.inventory_service.receive(self.pen.id, 0), ValidationError),
            (lambda: a.inventory_service.reserve(self.pad.id, 2), ConflictError),
            (lambda: a.inventory_service.level("prd_x"), NotFoundError),
            (lambda: a.order_service.place("cus_x", [(self.pen.id, 1)]), NotFoundError),
            (lambda: a.order_service.place(self.alice.id, [(self.pen.id, 1)], "NOPE"), ValidationError),
            (lambda: a.order_service.list_between(date(2026, 3, 5), date(2026, 3, 1)), ValidationError),
        ]
        for call, exc in cases:
            with self.assertRaises(exc):
                call()

    def test_deactivate_twice(self):
        self.app.product_service.deactivate(self.pen.id)
        with self.assertRaises(ConflictError):
            self.app.product_service.deactivate(self.pen.id)

    def test_failed_order_rolls_back(self):
        with self.assertRaises(ConflictError):
            self.app.order_service.place(self.alice.id, [(self.pen.id, 3), (self.pad.id, 5)])
        self.assertEqual(self.app.inventory_service.level(self.pen.id).reserved, 0)

    def test_sales_report_propagates(self):
        with self.assertRaises(ValidationError):
            sales_report(self.app, date(2026, 3, 5), date(2026, 3, 1))


class HiddenBoundaryTests(unittest.TestCase):
    def test_api_statuses_unchanged(self):
        app, _ = make_app()
        r = app.handle("POST", "/customers", {"name": "A", "email": "a@example.com"})
        self.assertEqual(r.status, 201)
        r = app.handle("POST", "/customers", {"name": "B", "email": "a@example.com"})
        self.assertEqual((r.status, r.body["error"]), (409, "conflict"))
        r = app.handle("POST", "/customers", {"name": "", "email": "b@example.com"})
        self.assertEqual((r.status, r.body["error"], r.body["message"]), (400, "invalid", "name is required"))
        r = app.handle("GET", "/products/prd_x")
        self.assertEqual((r.status, r.body["error"]), (404, "not_found"))
        r = app.handle("POST", "/orders", {"customer_id": "cus_x", "items": []})
        self.assertEqual(r.status, 404)

    def test_cli(self):
        fd, db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            out, err = io.StringIO(), io.StringIO()
            code = main(["--db", db, "customers", "add", "A", "bad"], out, err)
            self.assertEqual(code, 1)
            self.assertTrue(err.getvalue().startswith("error: invalid email"))
            out, err = io.StringIO(), io.StringIO()
            code = main(["--db", db, "report", "sales", "--from", "2026-03-05", "--to", "2026-03-01"], out, err)
            self.assertEqual(code, 1)
            self.assertIn("error:", err.getvalue())
        finally:
            os.unlink(db)


if __name__ == "__main__":
    unittest.main()
