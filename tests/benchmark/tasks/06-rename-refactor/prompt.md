Rename the function `calc_total` in `app/pricing.py` to `order_subtotal`, and update every caller and test that uses it (`app/orders.py`, `tests/test_orders.py`).

- Behaviour must not change.
- Do not leave a compatibility alias: after the change, the name `calc_total` must not appear anywhere in `app/` or `tests/`.
- Don't change any other names.

Python 3.9+, standard library only. The full suite must pass: `python3 -m unittest discover -s tests -t .`
