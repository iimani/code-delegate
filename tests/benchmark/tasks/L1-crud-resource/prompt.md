Add a **suppliers** resource to the `shop` service, following the existing patterns for customers exactly (read them first: model, repository, service, API handlers, serializers, app wiring, CLI and tests).

Requirements:

- **Model** `Supplier` in `shop/models/supplier.py` with fields `id`, `name`, `email`, `country`, `created_at`; export it from `shop.models`.
- **Storage**: a `suppliers` table in `shop/db.py` (`id` primary key, `name`, `email` unique, `country`, `created_at`).
- **Repository** `SupplierRepository` in `shop/repositories/supplier_repo.py` with `add`, `get`, `get_by_email`, `list_all` (ordered by name, then id).
- **Service** `SupplierService(suppliers, clock)` in `shop/services/supplier_service.py`, using the `(value, error)` convention from `shop/errors.py`:
  - `create(name, email, country)`: name is whitespace-normalized and validated like customer names; email validated like customer emails; `country` must be exactly two ASCII letters and is stored upper-case (`"ch"` → `"CH"`). Invalid input → `INVALID`. An email already used by another supplier → `CONFLICT`. Ids start with `sup_`. `created_at` comes from the clock.
  - `get(supplier_id)` → `NOT_FOUND` when missing.
  - `list()` → all suppliers ordered by name.
- **App**: `App` exposes `supplier_repo` and `supplier_service`.
- **API**: `POST /suppliers` (JSON body `name`, `email`, `country`; 201 on success), `GET /suppliers`, `GET /suppliers/{id}`. Supplier JSON has keys `id`, `name`, `email`, `country`, `created_at` (ISO string, same format as customers). Errors use the existing error responses (400 / 404 / 409).
- **CLI**: `suppliers add NAME EMAIL COUNTRY` prints the new id; `suppliers list` prints one line per supplier: `id<TAB>name<TAB>email<TAB>country`. Service errors print `error: <message>` to stderr and exit 1, like the other commands.
- **Tests**: `tests/test_suppliers.py` covering the service, API and CLI.

Python 3.9+, standard library only. Don't change existing behaviour. The full suite must pass: `python3 -m unittest discover -s tests -t .`
