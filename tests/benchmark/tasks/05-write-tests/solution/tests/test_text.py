import unittest

from app.text import slugify


class SlugifyTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("  Hello, World!  "), "hello-world")

    def test_accents(self):
        self.assertEqual(slugify("Crème brûlée"), "creme-brulee")

    def test_lowercase(self):
        self.assertEqual(slugify("ABC"), "abc")

    def test_collapse_runs(self):
        self.assertEqual(slugify("a -- b"), "a-b")

    def test_trim(self):
        self.assertEqual(slugify("--a--"), "a")

    def test_max_length_no_trailing_dash(self):
        self.assertEqual(slugify("hello world", max_length=6), "hello")

    def test_max_length_cut(self):
        self.assertEqual(slugify("abcdef", max_length=3), "abc")


if __name__ == "__main__":
    unittest.main()
