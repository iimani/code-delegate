import ast
import pathlib
import subprocess
import sys
import typing
import unittest

from app.cache import TTLCache

ROOT = pathlib.Path(__file__).resolve().parent.parent


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class HiddenCacheTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.cache = TTLCache(10, clock=self.clock)

    def test_generic_subscription(self):
        self.assertTrue(issubclass(TTLCache, typing.Generic))
        TTLCache[int]  # must not raise
        self.assertTrue(typing.get_type_hints(TTLCache.get), "TTLCache.get has no type hints")

    def test_set_get(self):
        self.cache.set("a", 1)
        self.assertEqual(self.cache.get("a"), 1)
        self.assertIsNone(self.cache.get("missing"))
        self.assertEqual(self.cache.get("missing", 5), 5)

    def test_default_ttl_boundary(self):
        self.cache.set("a", 1)
        self.clock.now += 9.999
        self.assertEqual(self.cache.get("a"), 1)
        self.clock.now += 0.001
        self.assertIsNone(self.cache.get("a"))
        self.assertEqual(self.cache.get("a", "d"), "d")

    def test_per_key_ttl(self):
        self.cache.set("short", 1, ttl=2)
        self.cache.set("long", 2, ttl=50)
        self.clock.now += 5
        self.assertIsNone(self.cache.get("short"))
        self.assertEqual(self.cache.get("long"), 2)

    def test_overwrite_restarts_ttl(self):
        self.cache.set("a", 1)
        self.clock.now += 8
        self.cache.set("a", 2)
        self.clock.now += 8
        self.assertEqual(self.cache.get("a"), 2)

    def test_delete(self):
        self.cache.set("a", 1)
        self.assertTrue(self.cache.delete("a"))
        self.assertFalse(self.cache.delete("a"))
        self.assertIsNone(self.cache.get("a"))

    def test_delete_expired_returns_false(self):
        self.cache.set("a", 1, ttl=1)
        self.clock.now += 2
        self.assertFalse(self.cache.delete("a"))

    def test_len_and_contains_ignore_expired(self):
        self.cache.set("a", 1, ttl=1)
        self.cache.set("b", 2, ttl=100)
        self.assertEqual(len(self.cache), 2)
        self.assertIn("a", self.cache)
        self.clock.now += 1
        self.assertEqual(len(self.cache), 1)
        self.assertNotIn("a", self.cache)
        self.assertIn("b", self.cache)

    def test_falsy_values_are_stored(self):
        self.cache.set("zero", 0)
        self.cache.set("none", None)
        self.assertEqual(self.cache.get("zero", 99), 0)
        self.assertIn("zero", self.cache)

    def test_invalid_ttls(self):
        with self.assertRaises(ValueError):
            TTLCache(0)
        with self.assertRaises(ValueError):
            self.cache.set("a", 1, ttl=0)
        with self.assertRaises(ValueError):
            self.cache.set("a", 1, ttl=-1)


class HiddenModelTestFileTests(unittest.TestCase):
    path = ROOT / "tests" / "test_cache.py"

    def test_test_file_exists_and_has_tests(self):
        self.assertTrue(self.path.exists(), "tests/test_cache.py was not written")
        tree = ast.parse(self.path.read_text())
        names = [n.name for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name.startswith("test")]
        self.assertGreaterEqual(len(names), 4, "expected at least 4 test methods")
        self.assertNotIn("sleep(", self.path.read_text())

    def test_test_file_passes(self):
        proc = subprocess.run([sys.executable, "-m", "unittest", "tests.test_cache"],
                              cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
