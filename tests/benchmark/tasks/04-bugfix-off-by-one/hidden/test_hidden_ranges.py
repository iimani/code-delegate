import unittest

from app.ranges import chunk_ranges


class HiddenChunkRangesTests(unittest.TestCase):
    def test_partial_last_chunk(self):
        self.assertEqual(chunk_ranges(10, 3), [(0, 3), (3, 6), (6, 9), (9, 10)])

    def test_exact_multiple(self):
        self.assertEqual(chunk_ranges(9, 3), [(0, 3), (3, 6), (6, 9)])

    def test_size_larger_than_total(self):
        self.assertEqual(chunk_ranges(2, 5), [(0, 2)])

    def test_zero_total(self):
        self.assertEqual(chunk_ranges(0, 4), [])

    def test_size_one(self):
        self.assertEqual(chunk_ranges(3, 1), [(0, 1), (1, 2), (2, 3)])

    def test_covers_range_without_gaps(self):
        for total in range(0, 40):
            for size in range(1, 12):
                chunks = chunk_ranges(total, size)
                flat = [i for s, e in chunks for i in range(s, e)]
                self.assertEqual(flat, list(range(total)), (total, size))
                self.assertTrue(all(0 < e - s <= size for s, e in chunks))

    def test_errors_kept(self):
        with self.assertRaises(ValueError):
            chunk_ranges(5, 0)
        with self.assertRaises(ValueError):
            chunk_ranges(5, -2)
        with self.assertRaises(ValueError):
            chunk_ranges(-1, 3)


if __name__ == "__main__":
    unittest.main()
