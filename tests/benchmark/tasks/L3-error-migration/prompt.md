The `shop` service layer reports failures by returning `(value, error)` tuples (see `shop/errors.py`). Migrate the whole code base to **exceptions** instead.

Target design:

- `shop/errors.py` defines `ServiceError(Exception)` with attributes `kind` and `message` (`str(exc)` is the message), and three subclasses:
  - `NotFoundError` — `kind == "not_found"`
  - `ValidationError` — `kind == "invalid"`
  - `ConflictError` — `kind == "conflict"`

  Each is raised as `SubclassName(message)`. Keep the `NOT_FOUND`, `INVALID`, `CONFLICT` constants. Remove `ok`, `fail`, `Error` and `Result` completely.
- Every service method (`CustomerService`, `ProductService`, `InventoryService`, `OrderService`) returns its value directly and raises the matching error where it used to return an error tuple, with the same messages. Behaviour is otherwise unchanged. In particular, `OrderService.place` still releases earlier reservations when a later one fails.
- API handlers catch `ServiceError` and produce the same HTTP responses as today (status and JSON body), via `shop/api/responses.py`'s `error_response`, which now takes a `ServiceError`.
- `sales_report` lets the service's `ValidationError` propagate (it currently converts the error to `ValueError`).
- The CLI keeps its behaviour: service errors print `error: <message>` to stderr and exit 1.
- Update every test and test helper (`tests/support.py` included) to the new style (`assertRaises` instead of checking tuples).

No code under `shop/` may use the tuple convention afterwards.

Python 3.9+, standard library only. The full suite must pass: `python3 -m unittest discover -s tests -t .`
