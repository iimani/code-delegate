`app/text.py` contains `slugify`, which has no tests. Write a thorough `unittest` test suite for it at `tests/test_text.py`.

- Test every rule listed in the `slugify` docstring, including accent handling, lower-casing, collapsing runs of separators into one "-", trimming leading/trailing "-", and `max_length` (including that a cut never leaves a trailing "-").
- Use exact expected values (`assertEqual`), not just type or length checks.
- Do not modify `app/text.py` or any other file — only create `tests/test_text.py`. The tests must pass against the current implementation.

Your tests will be scored by running them against deliberately broken versions of `slugify`: good tests fail on each broken version.

Python 3.9+, standard library only. The full suite must pass: `python3 -m unittest discover -s tests -t .`
