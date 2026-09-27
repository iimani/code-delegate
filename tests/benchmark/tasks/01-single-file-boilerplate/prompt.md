Add a structured JSON logger module at `app/logger.py`.

It must export one function:

    log(level, message, context=None)

- `level` must be one of "debug", "info", "warn", "error"; any other value raises `ValueError`.
- Each call writes exactly one line to standard output (resolve `sys.stdout` at call time, not import time) containing a single JSON object, followed by a newline.
- The JSON object has the keys `timestamp` (current UTC time as an ISO 8601 string), `level`, `message`, and `context` (the given dict, or `{}` when omitted).
- The function returns `None`.

This is a new, single file. Nothing else in the project needs to change. Python 3.9+, standard library only.
