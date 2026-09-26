import io
import os
import tempfile
import unittest

from shop.cli.main import main


class CliTests(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def tearDown(self):
        os.unlink(self.db)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        code = main(["--db", self.db, *args], out, err)
        return code, out.getvalue(), err.getvalue()

    def test_end_to_end(self):
        code, cid, _ = self.run_cli("customers", "add", "Alice", "alice@example.com")
        self.assertEqual(code, 0)
        _, pid, _ = self.run_cli("products", "add", "PEN-1", "Pen", "2.00")
        self.run_cli("inventory", "receive", pid.strip(), "10")
        code, out, _ = self.run_cli("orders", "place", cid.strip(), f"{pid.strip()}:3")
        self.assertEqual(code, 0)
        self.assertIn("CHF 6.49", out)  # 6.00 + 8.1 % VAT
        code, out, _ = self.run_cli("report", "inventory")
        self.assertIn("PEN-1", out)

    def test_errors(self):
        code, _, err = self.run_cli("customers", "add", "Alice", "nope")
        self.assertEqual(code, 1)
        self.assertIn("error: invalid email", err)
        code, _, err = self.run_cli("report", "sales")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
