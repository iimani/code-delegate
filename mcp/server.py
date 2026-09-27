#!/usr/bin/env python3
"""code-delegate MCP server: the `delegate` and `delegate_wait` tools.

A minimal Model Context Protocol server over stdio (newline-delimited
JSON-RPC 2.0), standard library only. Each tool writes code-delegate task
files and runs the fast path (`bridge.sh run` / `bridge.sh wait`), returning
its compact report. One tool call replaces the skill + shell steps the
orchestrator otherwise needs, and the tool description carries the routing
rules, so they reach every user who installs the plugin.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
BRIDGE = PLUGIN_ROOT / "bin" / "bridge.sh"
SERVER_INFO = {"name": "code-delegate", "version": "1.4.0"}
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_MAX_WAIT = 540  # under Claude Code's usual 10-minute ceiling for a single call
DIFF_LINES = 300        # applied diff shown inline, so reviewing needs no extra file reads
MAX_WAIT_LIMIT = 3300

DELEGATE_DESCRIPTION = """\
Hand coding work to a delegate agent (the user's configured backend, e.g. a local or company \
model via opencode) and get back a compact result. Tasks run in parallel in isolated git \
worktrees; each gets one automatic fix round if its test fails; passing work is applied to the \
working tree UNCOMMITTED.

When to use it: every step you take re-sends your whole context, so delegating only pays off \
for LARGE work that would take you many steps: a feature or module spanning several files, a \
mechanical migration across many files, a test suite, bulk boilerplate. Do small or single-spot \
changes yourself. Never delegate auth, crypto, secret handling or trust-boundary validation \
to a local model.

How: don't read implementation files to write the task: find the relevant paths with ls/grep \
and describe requirements (behaviour, names/signatures, edge cases, constraints), not code; the \
delegate reads the code itself. Split independent parts into separate tasks. `test` is one shell \
command that proves the task is done (prefer the project's full test command). List `files` \
the task will touch to protect your uncommitted edits. Leave backend/model empty unless needed.

Result per task: pass (applied; the diff is included below the report, up to 300 lines: review it \
there instead of re-reading files, then commit and summarise in the same step), \
running (call delegate_wait), fail/aborted/apply_conflict (failing output shown, worktree kept: \
fix it yourself or retry with another model), no_changes, error."""

WAIT_DESCRIPTION = """\
Keep waiting for delegated tasks that `delegate` reported as `running`, and return their \
result in the same format."""

TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Short task name, e.g. \"supplier-resource\" (letters, digits, dashes)."},
        "objective": {"type": "string", "description": "One sentence: what this achieves."},
        "requirements": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                         "description": "Bullet requirements: behaviour, names/signatures, edge cases, constraints. No code."},
        "test": {"type": "string", "description": "One shell command that passes only when the task is done."},
        "files": {"type": "array", "items": {"type": "string"}, "description": "Paths the task will create or modify (optional)."},
        "backend": {"type": "string", "description": "Optional: opencode, claude or codex. Default: the user's configured backend."},
        "model": {"type": "string", "description": "Optional backend model id or alias."},
    },
    "required": ["name", "objective", "requirements", "test"],
}

TOOLS = [
    {
        "name": "delegate",
        "description": DELEGATE_DESCRIPTION,
        "inputSchema": {
            "type": "object",
            "properties": {
                "tasks": {"type": "array", "items": TASK_SCHEMA, "minItems": 1},
                "max_wait_seconds": {"type": "integer", "minimum": 10, "maximum": MAX_WAIT_LIMIT,
                                     "description": "Return after this long even if tasks are still running (default 540)."},
            },
            "required": ["tasks"],
        },
    },
    {
        "name": "delegate_wait",
        "description": WAIT_DESCRIPTION,
        "inputSchema": {
            "type": "object",
            "properties": {
                "names": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "max_wait_seconds": {"type": "integer", "minimum": 10, "maximum": MAX_WAIT_LIMIT},
            },
            "required": ["names"],
        },
    },
]


class ToolError(Exception):
    """Invalid tool input; reported to the model as an error result."""


# --------------------------------------------------------------------------- tool logic

def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    if not slug:
        raise ToolError("task name %r has no letters or digits" % name)
    return slug[:48]


def project_root(cwd: Optional[str] = None) -> Path:
    start = cwd or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ToolError("not inside a git repository (%s); delegation needs one" % start)
    return Path(proc.stdout.strip())


def task_file_text(slug: str, task: Dict[str, Any]) -> str:
    test = str(task.get("test") or "").strip()
    if not test or "\n" in test:
        raise ToolError("task %r: `test` must be a single, non-empty command" % task.get("name"))
    requirements = task.get("requirements") or []
    if not isinstance(requirements, list) or not all(isinstance(r, str) and r.strip() for r in requirements) \
            or not requirements:
        raise ToolError("task %r: `requirements` must be a non-empty list of strings" % task.get("name"))
    objective = str(task.get("objective") or "").strip()
    if not objective:
        raise ToolError("task %r: `objective` is required" % task.get("name"))
    header = ["---", "Branch: delegate/%s" % slug, "Test: %s" % test]
    files = [str(f).strip() for f in (task.get("files") or []) if str(f).strip()]
    if files:
        header.append("Files: %s" % ", ".join(files))
    for key, field in (("Backend", "backend"), ("Model", "model")):
        value = str(task.get(field) or "").strip()
        if value:
            if "\n" in value:
                raise ToolError("task %r: `%s` must be a single line" % (task.get("name"), field))
            header.append("%s: %s" % (key, value))
    header.append("---")
    body = ["", "## Objective", objective, "", "## Requirements"]
    body += ["- %s" % r.strip().replace("\n", " ") for r in requirements]
    return "\n".join(header + body) + "\n"


def clamp_wait(value: Any) -> int:
    if value is None:
        return DEFAULT_MAX_WAIT
    try:
        return max(10, min(int(value), MAX_WAIT_LIMIT))
    except (TypeError, ValueError):
        raise ToolError("max_wait_seconds must be an integer")


def run_bridge(root: Path, mode: str, slugs: List[str], max_wait: int) -> str:
    cmd = [str(BRIDGE), mode, *slugs, "--max-wait", str(max_wait)]
    try:
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=max_wait + 120)
    except subprocess.TimeoutExpired:
        return "bridge.sh %s did not return in time; call delegate_wait with the same names." % mode
    output = proc.stdout.strip()
    if proc.stderr.strip() and not output:
        output = proc.stderr.strip()
    return output or "bridge.sh %s returned no output (exit %d)" % (mode, proc.returncode)


def with_diffs(root: Path, report: str) -> str:
    """Append the applied diff of every passed task (truncated) to the bridge report."""
    statuses = []
    for line in reversed(report.splitlines()):
        if line.startswith("[{"):
            try:
                statuses = json.loads(line)
            except ValueError:
                statuses = []
            break
    parts = [report]
    for entry in statuses:
        if entry.get("status") != "pass":
            continue
        patch = root / ".git" / "worktrees_agents" / ".results" / ("%s.patch" % entry.get("slug"))
        if not patch.exists():
            continue
        lines = patch.read_text(errors="replace").splitlines()
        shown = lines[:DIFF_LINES]
        parts.append("\n--- applied diff: %s ---\n%s" % (entry["slug"], "\n".join(shown)))
        if len(lines) > DIFF_LINES:
            parts.append("... %d more diff lines not shown (git diff to see them)" % (len(lines) - DIFF_LINES))
    return "\n".join(parts)


def tool_delegate(args: Dict[str, Any]) -> str:
    tasks = args.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ToolError("`tasks` must be a non-empty list")
    root = project_root(args.get("cwd"))
    slugs: List[str] = []
    texts = []
    for task in tasks:
        if not isinstance(task, dict):
            raise ToolError("each task must be an object")
        slug = slugify(str(task.get("name") or ""))
        if slug in slugs:
            raise ToolError("duplicate task name %r" % task.get("name"))
        slugs.append(slug)
        texts.append(task_file_text(slug, task))
    # Validate everything before writing anything.
    for slug, text in zip(slugs, texts):
        (root / (".local_task_%s.md" % slug)).write_text(text)
    return with_diffs(root, run_bridge(root, "run", slugs, clamp_wait(args.get("max_wait_seconds"))))


def tool_delegate_wait(args: Dict[str, Any]) -> str:
    names = args.get("names")
    if not isinstance(names, list) or not names:
        raise ToolError("`names` must be a non-empty list")
    root = project_root(args.get("cwd"))
    return with_diffs(root, run_bridge(root, "wait", [slugify(str(n)) for n in names],
                                       clamp_wait(args.get("max_wait_seconds"))))


HANDLERS = {"delegate": tool_delegate, "delegate_wait": tool_delegate_wait}


# --------------------------------------------------------------------------- JSON-RPC plumbing

def handle(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a response for a request, or None for notifications."""
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}
    if msg_id is None:  # notification (e.g. notifications/initialized)
        return None

    def result(value):
        return {"jsonrpc": "2.0", "id": msg_id, "result": value}

    def error(code, text):
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": text}}

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]
        return result({"protocolVersion": version, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO})
    if method == "ping":
        return result({})
    if method == "tools/list":
        return result({"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        handler = HANDLERS.get(name)
        if handler is None:
            return error(-32602, "unknown tool: %s" % name)
        try:
            text = handler(params.get("arguments") or {})
            return result({"content": [{"type": "text", "text": text}], "isError": False})
        except ToolError as e:
            return result({"content": [{"type": "text", "text": "error: %s" % e}], "isError": True})
        except Exception as e:  # never crash the server on a tool failure
            return result({"content": [{"type": "text", "text": "internal error: %s" % e}], "isError": True})
    return error(-32601, "method not found: %s" % method)


def serve(stdin=sys.stdin, stdout=sys.stdout) -> None:
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            response = handle(message) if isinstance(message, dict) else \
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()


if __name__ == "__main__":
    serve()
