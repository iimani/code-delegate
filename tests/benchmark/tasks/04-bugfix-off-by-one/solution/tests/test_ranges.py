import unittest

from app.ranges import chunk_ranges


class ChunkRangesTests(unittest.TestCase):
    def test_exact_multiple(self):
        self.assertEqual(chunk_ranges(6, 3), [(0, 3), (3, 6)])

    def test_keeps_final_partial_chunk(self):
        self.assertEqual(chunk_ranges(10, 3), [(0, 3), (3, 6), (6, 9), (9, 10)])

    def test_rejects_non_positive_size(self):
        with self.assertRaises(ValueError):
            chunk_ranges(5, 0)


if __name__ == "__main__":
    unittest.main()
