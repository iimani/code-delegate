"""Tests for mcp/server.py (the `delegate` / `delegate_wait` MCP tools). No LLM needed.

Run: python3 -m unittest discover -s tests/mcp -p 'test_*.py'
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

FAKE_CONFIG = """name: fake
description: Scripted test backend
check_command: "true"
default_model: fake
models:
  - alias: fake
    id: fake
    description: "scripted"
    security_ok: false
capabilities:
  - single-file
tags:
  security_ok: false
  cross_file: true
  type_reasoning: false
cost_tier: free
"""

# Writes "ok" into the first file of the task's Files: header and commits it;
# sleeps first when the requirements mention "slow".
FAKE_RUN = """#!/bin/bash
set -euo pipefail
cd "$1"
target="$(grep -m1 '^Files:' .local_task.md 2>/dev/null | sed 's/^Files:[[:space:]]*//; s/,.*//' || true)"
[ -n "$target" ] || target="$(cat .fake_target)"
echo "$target" > .fake_target
if grep -q 'slow' .local_task.md 2>/dev/null; then sleep 8; fi
echo ok > "$target"
git add "$target" && git commit -qm "fake: $target"
"""


def make_plugin(dest: Path) -> Path:
    for part in ("bin", "backends", "mcp"):
        shutil.copytree(REPO_ROOT / part, dest / part)
    (dest / "backends" / "fake").mkdir()
    (dest / "backends" / "fake" / "config.yaml").write_text(FAKE_CONFIG)
    run = dest / "backends" / "fake" / "run.sh"
    run.write_text(FAKE_RUN)
    run.chmod(0o755)
    return dest


def make_repo(dest: Path) -> Path:
    dest.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@localhost"], ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=dest, check=True)
    (dest / "README.md").write_text("base\n")
    (dest / ".gitignore").write_text(".fake_*\n")
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=dest, check=True)
    return dest


class Session:
    """Drives one server process over stdio, like an MCP client."""

    def __init__(self, plugin: Path, cwd: Path):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        self.proc = subprocess.Popen([sys.executable, str(plugin / "mcp" / "server.py")], cwd=str(cwd), env=env,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.next_id = 1

    def request(self, method, params=None):
        msg_id = self.next_id
        self.next_id += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "method": method,
                                          "params": params or {}}) + "\n")
        self.proc.stdin.flush()
        response = json.loads(self.proc.stdout.readline())
        assert response["id"] == msg_id
        return response

    def call(self, tool, arguments):
        response = self.request("tools/call", {"name": tool, "arguments": arguments})
        result = response["result"]
        return result["content"][0]["text"], result["isError"]

    def close(self):
        self.proc.stdin.close()
        self.proc.stdout.close()
        self.proc.wait(timeout=10)


def task(name, files, **extra):
    t = {"name": name, "objective": "Write ok into %s." % files[0],
         "requirements": ["The file %s contains exactly: ok" % files[0]],
         "test": "grep -qx ok %s" % files[0], "files": files, "backend": "fake"}
    t.update(extra)
    return t


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(REPO_ROOT / "mcp"))
        import server
        self.server = server

    def rpc(self, lines):
        out = io.StringIO()
        self.server.serve(io.StringIO("\n".join(json.dumps(l) if not isinstance(l, str) else l for l in lines) + "\n"), out)
        return [json.loads(l) for l in out.getvalue().splitlines()]

    def test_initialize_negotiates_version(self):
        known, unknown = self.rpc([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
            {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}},
        ])
        self.assertEqual(known["result"]["protocolVersion"], "2024-11-05")
        self.assertEqual(unknown["result"]["protocolVersion"], self.server.SUPPORTED_PROTOCOLS[0])
        self.assertIn("tools", known["result"]["capabilities"])

    def test_notifications_get_no_response_and_errors_are_reported(self):
        responses = self.rpc([
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 3, "method": "ping"},
            {"jsonrpc": "2.0", "id": 4, "method": "nope"},
            "{not json",
        ])
        self.assertEqual(responses[0], {"jsonrpc": "2.0", "id": 3, "result": {}})
        self.assertEqual(responses[1]["error"]["code"], -32601)
        self.assertEqual(responses[2]["error"]["code"], -32700)

    def test_tools_list(self):
        (resp,) = self.rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
        tools = {t["name"]: t for t in resp["result"]["tools"]}
        self.assertEqual(set(tools), {"delegate", "delegate_wait"})
        self.assertIn("LARGE work", tools["delegate"]["description"])
        task_schema = tools["delegate"]["inputSchema"]["properties"]["tasks"]["items"]
        self.assertEqual(set(task_schema["required"]), {"name", "objective", "requirements", "test"})

    def test_task_file_text(self):
        text = self.server.task_file_text("feat-x", {"name": "feat x", "objective": "Do x.",
                                                     "requirements": ["a", "b\nc"], "test": "make test",
                                                     "files": ["a.py", "b.py"], "model": "m"})
        self.assertEqual(text, "---\nBranch: delegate/feat-x\nTest: make test\nFiles: a.py, b.py\nModel: m\n---\n\n"
                               "## Objective\nDo x.\n\n## Requirements\n- a\n- b c\n")

    def test_invalid_inputs(self):
        bad = [
            {"name": "x", "objective": "o", "requirements": ["r"], "test": "a\nb"},
            {"name": "x", "objective": "o", "requirements": [], "test": "t"},
            {"name": "!!!", "objective": "o", "requirements": ["r"], "test": "t"},
            {"name": "x", "objective": "", "requirements": ["r"], "test": "t"},
        ]
        for t in bad:
            with self.assertRaises(self.server.ToolError, msg=t):
                self.server.task_file_text(self.server.slugify(t["name"]), t)


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.plugin = make_plugin(self.tmp / "plugin")
        self.repo = make_repo(self.tmp / "repo")
        self.session = Session(self.plugin, self.repo)
        self.session.request("initialize", {"protocolVersion": "2025-06-18"})

    def tearDown(self):
        self.session.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_delegate_applies_uncommitted(self):
        text, is_error = self.session.call("delegate", {"tasks": [task("One", ["one.txt"])]})
        self.assertFalse(is_error, text)
        self.assertIn("== one: pass", text)
        self.assertEqual((self.repo / "one.txt").read_text(), "ok\n")
        status = subprocess.run(["git", "status", "--porcelain", "one.txt"], cwd=self.repo,
                                capture_output=True, text=True).stdout
        self.assertEqual(status.strip(), "?? one.txt")

    def test_parallel_tasks(self):
        text, _ = self.session.call("delegate", {"tasks": [task("a", ["a.txt"]), task("b", ["b.txt"])]})
        self.assertIn("== a: pass", text)
        self.assertIn("== b: pass", text)

    def test_running_then_wait(self):
        text, _ = self.session.call("delegate", {"tasks": [task("slow one", ["s.txt"], requirements=["slow"])],
                                                 "max_wait_seconds": 10})
        if "== slow-one: running" in text:
            text, _ = self.session.call("delegate_wait", {"names": ["slow one"], "max_wait_seconds": 60})
        self.assertIn("== slow-one: pass", text)

    def test_invalid_input_is_a_tool_error(self):
        text, is_error = self.session.call("delegate", {"tasks": [task("x", ["x.txt"], test="a\nb")]})
        self.assertTrue(is_error)
        self.assertIn("single", text)
        self.assertEqual(list(self.repo.glob(".local_task_*")), [], "nothing written on invalid input")

    def test_outside_git_repo(self):
        outside = self.tmp / "plain"
        outside.mkdir()
        session = Session(self.plugin, outside)
        try:
            text, is_error = session.call("delegate", {"tasks": [task("x", ["x.txt"])]})
        finally:
            session.close()
        self.assertTrue(is_error)
        self.assertIn("git repository", text)


if __name__ == "__main__":
    unittest.main()
