# shop — benchmark fixture (large)

A small order/inventory service used by the large benchmark tasks. Standard
library only, Python 3.9+. Not a real application.

Layers:

    shop/util/          money (integer cents), dates, ids, text helpers
    shop/models/        dataclasses
    shop/db.py          sqlite3 schema and connection
    shop/repositories/  SQL access, one repository per table group
    shop/services/      business rules; return (value, error) tuples (see shop/errors.py)
    shop/api/           request routing and JSON handlers (framework-free)
    shop/reports/       tabular reports
    shop/cli/           command-line interface
    shop/app.py         wires everything together

Conventions:

- Money is always an ``int`` number of cents.
- Timestamps are timezone-naive UTC ``datetime`` values, stored as ISO 8601 text.
- Service methods never raise for expected failures; they return
  ``(value, None)`` on success and ``(None, Error)`` on failure.

Run the tests from this directory:

    python3 -m unittest discover -s tests -t .
