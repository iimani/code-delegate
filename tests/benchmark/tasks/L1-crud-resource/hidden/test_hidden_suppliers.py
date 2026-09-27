import io
import os
import tempfile
import unittest

from shop.cli.main import main
from shop.errors import CONFLICT, INVALID, NOT_FOUND
from tests.support import START, make_app


class HiddenSupplierServiceTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = make_app()
        self.svc = self.app.supplier_service

    def test_model_export(self):
        from shop.models import Supplier  # noqa: F401
        from shop.repositories.supplier_repo import SupplierRepository
        self.assertIsInstance(self.app.supplier_repo, SupplierRepository)

    def test_create(self):
        s, err = self.svc.create("  Acme   Paper ", "sales@acme.example", "ch")
        self.assertIsNone(err)
        self.assertEqual((s.name, s.email, s.country, s.created_at), ("Acme Paper", "sales@acme.example", "CH", START))
        self.assertTrue(s.id.startswith("sup_"))
        self.assertEqual(self.svc.get(s.id), (s, None))

    def test_invalid(self):
        for name, email, country in (("", "a@b.example", "CH"), ("A", "bad", "CH"), ("A", "a@b.example", "C"),
                                     ("A", "a@b.example", "CHE"), ("A", "a@b.example", "1H"), ("A", "a@b.example", "")):
            s, err = self.svc.create(name, email, country)
            self.assertIsNone(s)
            self.assertEqual(err.kind, INVALID, (name, email, country))

    def test_conflict_and_missing(self):
        self.svc.create("A", "a@b.example", "DE")
        _, err = self.svc.create("B", "a@b.example", "FR")
        self.assertEqual(err.kind, CONFLICT)
        _, err = self.svc.get("sup_missing")
        self.assertEqual(err.kind, NOT_FOUND)

    def test_list_ordered_by_name(self):
        for name in ("Zeta", "Alpha", "Mid"):
            self.svc.create(name, f"{name.lower()}@x.example", "IT")
        suppliers, err = self.svc.list()
        self.assertIsNone(err)
        self.assertEqual([s.name for s in suppliers], ["Alpha", "Mid", "Zeta"])

    def test_customers_unaffected(self):
        c, err = self.app.customer_service.create("A", "a@b.example")
        self.assertIsNone(err)
        _, err = self.svc.create("A", "a@b.example", "CH")
        self.assertIsNone(err, "supplier emails must not clash with customer emails")


class HiddenSupplierApiTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = make_app()

    def test_endpoints(self):
        resp = self.app.handle("POST", "/suppliers", {"name": "Acme", "email": "a@acme.example", "country": "at"})
        self.assertEqual(resp.status, 201)
        self.assertEqual(set(resp.body), {"id", "name", "email", "country", "created_at"})
        self.assertEqual((resp.body["country"], resp.body["created_at"]), ("AT", "2026-03-02T10:00:00"))
        sid = resp.body["id"]
        self.assertEqual(self.app.handle("GET", f"/suppliers/{sid}").body["name"], "Acme")
        self.assertEqual(len(self.app.handle("GET", "/suppliers").body), 1)
        self.assertEqual(self.app.handle("GET", "/suppliers/sup_x").status, 404)
        bad = self.app.handle("POST", "/suppliers", {"name": "B", "email": "b@acme.example", "country": "X"})
        self.assertEqual((bad.status, bad.body["error"]), (400, "invalid"))
        dup = self.app.handle("POST", "/suppliers", {"name": "B", "email": "a@acme.example", "country": "DE"})
        self.assertEqual(dup.status, 409)


class HiddenSupplierCliTests(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def tearDown(self):
        os.unlink(self.db)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        return main(["--db", self.db, *args], out, err), out.getvalue(), err.getvalue()

    def test_add_and_list(self):
        code, sid, _ = self.run_cli("suppliers", "add", "Acme", "a@acme.example", "ch")
        self.assertEqual(code, 0)
        self.assertTrue(sid.strip().startswith("sup_"))
        code, out, _ = self.run_cli("suppliers", "list")
        self.assertEqual(out, f"{sid.strip()}\tAcme\ta@acme.example\tCH\n")
        code, _, err = self.run_cli("suppliers", "add", "Acme", "bad", "CH")
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("error: "))


class HiddenSupplierTestFile(unittest.TestCase):
    def test_model_wrote_tests(self):
        import pathlib
        path = pathlib.Path(__file__).resolve().parent / "test_suppliers.py"
        self.assertTrue(path.exists(), "tests/test_suppliers.py missing")
        self.assertIn("def test", path.read_text())


if __name__ == "__main__":
    unittest.main()
