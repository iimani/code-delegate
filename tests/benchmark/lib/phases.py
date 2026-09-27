"""Split an orchestrator session into phases, from its Claude Code transcript.

Each API call (one assistant message id) is assigned to one phase from the
tool calls it made, and charged its context tokens (input + cache reads +
cache writes) and output tokens. This shows *where* the orchestrator's tokens
go: exploring, loading the skill, writing specs, dispatching, reviewing,
integrating delegate work, or coding itself.

Standard library only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

# Highest priority first: a call that both writes a task file and runs the
# bridge counts as "dispatch".
PHASES = ["dispatch", "spec", "code", "integrate", "test", "review", "discover", "skill",
          "explore", "subagent", "other", "summary"]

_BRIDGE_RUN = re.compile(r"bridge\.sh\s+(?!-)")
_BRIDGE_INFO = re.compile(r"bridge\.sh\s+--(models|backends|security-check|suggest)")
_BRIDGE_WATCH = re.compile(r"bridge\.sh\s+--(logs|status|cleanup)")
_GIT_INTEGRATE = re.compile(r"\bgit\b[^|;&]*\b(merge|cherry-pick|checkout|commit|add|rebase|apply|am|restore)\b")
_TESTS = re.compile(r"\b(unittest|pytest|npm test|go test|cargo test)\b")
_TASK_FILE = re.compile(r"\.local_(task|feedback)_")


def classify_tool(name: str, tool_input: dict) -> str:
    command = str(tool_input.get("command") or "")
    path = str(tool_input.get("file_path") or tool_input.get("path") or "")
    if name == "Skill":
        return "skill"
    if name.startswith("mcp__") and re.search(r"__delegate(_wait)?$", name):
        return "dispatch"
    if name in ("Task", "Agent"):
        return "subagent"
    if name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return "spec" if _TASK_FILE.search(path) else "code"
    if name in ("Read", "Grep", "Glob", "LS"):
        return "review" if "worktrees_agents" in path else "explore"
    if name == "Bash":
        if _BRIDGE_INFO.search(command):
            return "discover"
        if _BRIDGE_WATCH.search(command):
            return "review"
        if _BRIDGE_RUN.search(command):
            return "dispatch"
        if _TASK_FILE.search(command):
            return "spec"
        # A command that edits code (possibly also testing and committing) is coding;
        # one that commits/merges delegate work without editing is integration.
        if re.search(r"(<<|>\s*\S+\.py\b|\bsed\s+-i|\bpython3?\s+-\s)", command):
            return "code"
        if _GIT_INTEGRATE.search(command) or re.search(r"\bcp\b.*worktrees_agents", command):
            return "integrate"
        if _TESTS.search(command):
            return "test"
        if "worktrees_agents" in command or re.search(r"\bgit\b[^|;&]*\b(diff|log|show|status)\b", command):
            return "review"
        return "explore"
    return "other"


def _calls(lines: Iterable[str]) -> List[dict]:
    """Collapse transcript lines into API calls keyed by assistant message id."""
    calls: Dict[str, dict] = {}
    order: List[str] = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") != "assistant" or entry.get("isSidechain"):
            continue
        message = entry.get("message") or {}
        mid = message.get("id") or entry.get("uuid")
        usage = message.get("usage") or {}
        if mid not in calls:
            calls[mid] = {"context": (usage.get("input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0)
                          + (usage.get("cache_creation_input_tokens") or 0),
                          "output": usage.get("output_tokens") or 0, "tools": []}
            order.append(mid)
        else:
            calls[mid]["output"] = max(calls[mid]["output"], usage.get("output_tokens") or 0)
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls[mid]["tools"].append((block.get("name") or "", block.get("input") or {}))
    return [calls[m] for m in order]


def phase_breakdown(transcript: Path) -> Optional[Dict[str, Dict[str, int]]]:
    """{phase: {"calls", "context", "output", "total"}} for one transcript, or None if unreadable."""
    try:
        lines = transcript.read_text().splitlines()
    except OSError:
        return None
    result: Dict[str, Dict[str, int]] = {}
    for call in _calls(lines):
        phases = [classify_tool(n, i) for n, i in call["tools"]] or ["summary"]
        phase = min(phases, key=PHASES.index)
        bucket = result.setdefault(phase, {"calls": 0, "context": 0, "output": 0, "total": 0})
        bucket["calls"] += 1
        bucket["context"] += call["context"]
        bucket["output"] += call["output"]
        bucket["total"] += call["context"] + call["output"]
    return result


def find_transcript(session_id: str, config_dirs: Iterable[Path]) -> Optional[Path]:
    """Locate <config>/projects/*/<session_id>.jsonl."""
    if not session_id:
        return None
    for base in config_dirs:
        projects = Path(base) / "projects"
        if projects.is_dir():
            for match in projects.glob("*/%s.jsonl" % session_id):
                return match
    return None
