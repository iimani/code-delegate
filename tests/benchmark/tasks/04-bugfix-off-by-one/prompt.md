Bug report: `app.ranges.chunk_ranges` drops the final partial chunk.

    >>> chunk_ranges(10, 3)
    [(0, 3), (3, 6), (6, 9)]      # actual
    [(0, 3), (3, 6), (6, 9), (9, 10)]   # expected

Fix `app/ranges.py` so it matches its docstring for every valid input, including when `size` is larger than `total` and when `total` is 0. Keep the existing `ValueError` behaviour. Add a regression test for this bug to `tests/test_ranges.py`.

Python 3.9+, standard library only. Change only those two files. The full suite must pass: `python3 -m unittest discover -s tests -t .`
