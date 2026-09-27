import ast
import io
import pathlib
import unittest
from contextlib import redirect_stdout

from app import container as container_mod
from app import main as main_mod
from app.container import ConsoleLogger, build_container
from app.db import Database
from app.server import Server

ROOT = pathlib.Path(__file__).resolve().parent.parent


class Recorder:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(message)


def _print_calls(path):
    tree = ast.parse(path.read_text())
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            calls.append(node)
    return tree, calls


class HiddenContainerTests(unittest.TestCase):
    def test_single_shared_logger(self):
        rec = Recorder()
        c = build_container(rec)
        self.assertIs(c.logger, rec)
        self.assertIsInstance(c.db, Database)
        self.assertIsInstance(c.server, Server)
        c.db.connect()
        c.db.query("SELECT 1")
        c.server.start()
        c.server.handle_request("/health")
        self.assertEqual(rec.messages, [
            "[db] connecting to database",
            "[db] running query: SELECT 1",
            "[server] listening on port 8080",
            "[server] handling request: /health",
        ])

    def test_default_logger_is_console(self):
        c = build_container()
        self.assertIsInstance(c.logger, ConsoleLogger)
        buf = io.StringIO()
        with redirect_stdout(buf):
            c.db.connect()
        self.assertIn("[db] connecting to database", buf.getvalue())

    def test_main_uses_injected_logger(self):
        rec = Recorder()
        buf = io.StringIO()
        with redirect_stdout(buf):
            main_mod.main(rec)
        self.assertEqual(rec.messages, [
            "[boot] starting application",
            "[db] connecting to database",
            "[server] listening on port 8080",
        ])
        self.assertEqual(buf.getvalue(), "")

    def test_modules_have_no_print(self):
        for name in ("main.py", "db.py", "server.py"):
            _, calls = _print_calls(ROOT / "app" / name)
            self.assertEqual(calls, [], f"app/{name} still calls print")

    def test_only_console_logger_prints(self):
        tree, calls = _print_calls(ROOT / "app" / "container.py")
        allowed = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "ConsoleLogger":
                allowed |= {id(n) for n in ast.walk(node)}
        self.assertTrue(all(id(c) in allowed for c in calls),
                        "print used outside ConsoleLogger in app/container.py")

    def test_logger_protocol(self):
        import typing
        self.assertTrue(hasattr(container_mod, "Logger"))
        self.assertIn(typing.Protocol, getattr(container_mod.Logger, "__mro__", ()))


if __name__ == "__main__":
    unittest.main()
