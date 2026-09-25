Three modules of the `shop` service have no direct tests: `shop/util/money.py`, `shop/util/dates.py` and `shop/services/pricing.py`. Write thorough `unittest` suites for them:

- `tests/test_money.py` for `to_cents`, `format_cents`, `percent_of`, `split_evenly`
- `tests/test_dates.py` for `parse_date`, `day_bounds`, `to_iso`, `from_iso`, `add_business_days`, `days_between`
- `tests/test_pricing.py` for `normalize_code`, `discount_percent`, `price_order` (including VAT, every discount code, and the bulk-code minimum)

Test every behaviour described in the docstrings and comments, with exact expected values (`assertEqual`), including rounding (half up), edge cases, and error cases (which exception is raised).

Do **not** modify any file under `shop/` — only create the three test files. The tests must pass against the current code. They will be scored by running them against deliberately broken versions of these modules: a good suite fails on each broken version.

Python 3.9+, standard library only. The full suite must pass: `python3 -m unittest discover -s tests -t .`
