Replace the module-level `print` calls in `app/main.py`, `app/db.py` and `app/server.py` with a shared, injected logger, wired together by a small dependency-injection container. This changes how the modules are wired, not just what they print.

Target design:

- `app/container.py` defines:
  - `Logger` — a `typing.Protocol` with one method `info(self, message: str) -> None`.
  - `ConsoleLogger` — implements `Logger` by printing the message to standard output.
  - `Container` — holds exactly one logger and the modules built with it, exposed as attributes `logger`, `db` and `server`.
  - `build_container(logger=None) -> Container` — uses the given logger, or a new `ConsoleLogger` when omitted, and passes that same instance to every module.
- `app/db.py`: replace the module functions with class `Database(logger)` with methods `connect()` and `query(sql)`.
- `app/server.py`: replace the module functions with class `Server(logger)` with methods `start()` and `handle_request(path)`.
- `app/main.py`: `main(logger=None)` builds the container, then calls `db.connect()` and `server.start()`; keep the `if __name__ == "__main__"` entry point.
- Log messages keep their exact current text (for example `[db] running query: SELECT 1`), and main still logs `[boot] starting application` first, through the injected logger.
- None of these four files may call `print` except `ConsoleLogger`.

Python 3.9+, standard library only. Don't touch other modules. The full suite must pass: `python3 -m unittest discover -s tests -t .`
