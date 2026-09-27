Implement these three **independent** features in the `shop` service. Keep the existing `(value, error)` convention from `shop/errors.py`.

**1. Product search**
- `ProductService.search(query) -> (list, error)`: case-insensitive substring match against product name **or** SKU; only active products; ordered by SKU. A query that is empty or only whitespace → `INVALID`.
- API: `GET /products?q=<query>` returns the matching products (same JSON as the product list). Without `q`, the endpoint behaves exactly as today (including `active=1`). A blank `q` → 400.

**2. Customer email normalization**
- `CustomerService.create` trims surrounding whitespace from the email and lower-cases it **before** validation and the duplicate check, and stores the normalized value. So `"  Bob@Example.COM "` is stored as `"bob@example.com"` and conflicts with an existing `bob@example.com`.

**3. Order cancellation**
- `OrderService.cancel(order_id) -> (order, error)`: only a `placed` order can be cancelled (otherwise `CONFLICT`); a missing order → `NOT_FOUND`. Cancelling releases the reserved stock of every line and sets the status to `"cancelled"` (constant `CANCELLED` in `shop/models/order.py`), persisted.
- API: `POST /orders/{id}/cancel` returns the updated order (200), or the usual 404/409 error responses.
- Cancelled orders already don't count in the reports, so no report changes are needed.

Add tests for each feature (`tests/test_search.py`, `tests/test_email_normalization.py`, `tests/test_cancel.py`).

Python 3.9+, standard library only. Don't change other behaviour. The full suite must pass: `python3 -m unittest discover -s tests -t .`
