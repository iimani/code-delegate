import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

from app import logger


def _capture(*args, **kwargs):
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = logger.log(*args, **kwargs)
    return result, buf.getvalue()


def _parse_ts(value):
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


class HiddenLoggerTests(unittest.TestCase):
    def test_writes_one_json_line(self):
        result, out = _capture("info", "hello")
        self.assertIsNone(result)
        self.assertTrue(out.endswith("\n"))
        lines = out.splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["level"], "info")
        self.assertEqual(record["message"], "hello")
        self.assertEqual(record["context"], {})

    def test_context_is_included(self):
        _, out = _capture("error", "boom", {"user": 7, "tags": ["a"]})
        self.assertEqual(json.loads(out)["context"], {"user": 7, "tags": ["a"]})

    def test_context_keyword(self):
        _, out = _capture("warn", "w", context={"k": "v"})
        self.assertEqual(json.loads(out)["context"], {"k": "v"})

    def test_all_levels_accepted(self):
        for level in ("debug", "info", "warn", "error"):
            _, out = _capture(level, "m")
            self.assertEqual(json.loads(out)["level"], level)

    def test_invalid_level_raises(self):
        for level in ("fatal", "INFO", ""):
            with self.assertRaises(ValueError):
                _capture(level, "m")

    def test_timestamp_is_current_utc_iso8601(self):
        _, out = _capture("info", "t")
        ts = _parse_ts(json.loads(out)["timestamp"])
        self.assertLess(abs(datetime.now(timezone.utc) - ts), timedelta(minutes=5))

    def test_one_line_per_call(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            logger.log("info", "a")
            logger.log("info", "multi\nline message")
        lines = buf.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[1])["message"], "multi\nline message")


if __name__ == "__main__":
    unittest.main()
