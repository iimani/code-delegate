import unittest

from app.cache import TTLCache


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class TTLCacheTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.cache = TTLCache[int](5, clock=self.clock)

    def test_set_get(self):
        self.cache.set("a", 1)
        self.assertEqual(self.cache.get("a"), 1)

    def test_overwrite(self):
        self.cache.set("a", 1)
        self.cache.set("a", 2)
        self.assertEqual(self.cache.get("a"), 2)

    def test_delete(self):
        self.cache.set("a", 1)
        self.assertTrue(self.cache.delete("a"))
        self.assertIsNone(self.cache.get("a"))

    def test_default_ttl_expiry(self):
        self.cache.set("a", 1)
        self.clock.now = 5
        self.assertIsNone(self.cache.get("a"))

    def test_per_key_ttl(self):
        self.cache.set("a", 1, ttl=1)
        self.clock.now = 1
        self.assertIsNone(self.cache.get("a"))


if __name__ == "__main__":
    unittest.main()
