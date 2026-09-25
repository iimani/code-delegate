#!/usr/bin/env python3
"""code-delegate benchmark harness.

Subcommands (see ../README.md and docs/benchmark-methodology.md):
  doctor     preflight: tools, Claude auth + context isolation, model reachability
  compare    Claude tokens for the same task with vs. without delegation (primary)
  scorecard  delegate-only quality matrix through bridge.sh (secondary)
  report     rebuild summary.md / summary.json for an existing results dir
  selftest   check every task's hidden tests fail on the fixture and pass on its solution

Python 3.9+, standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BENCH_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BENCH_DIR.parent.parent
TASKS_DIR = BENCH_DIR / "tasks"
FIXTURE_DIR = BENCH_DIR / "fixture"
FIXTURES = {"small": FIXTURE_DIR, "large": BENCH_DIR / "fixture-large"}
TIERS = ("small", "large")
RESULTS_DIR = Path(os.environ.get("BENCH_RESULTS_DIR") or BENCH_DIR / "results")
LIB_DIR = BENCH_DIR / "lib"
DRYRUN_DIR = LIB_DIR / "dryrun"
LOCAL_ENV_FILE = BENCH_DIR / "bench.local.env"

sys.path.insert(0, str(LIB_DIR))
import phases  # noqa: E402
import report  # noqa: E402

TEST_CMD = ["-m", "unittest", "discover", "-s", "tests", "-t", "."]
# Delegation settings from the operator's shell must never leak into runs.
OPERATOR_ENV_TO_DROP = ("CODE_DELEGATE_BACKEND", "CODE_DELEGATE_USAGE_LOG", "OPENCODE_DELEGATE_MODEL",
                        "CLAUDE_DELEGATE_MODEL", "CODEX_DELEGATE_MODEL", "CLAUDE_DELEGATE_SETTING_SOURCES")
ENV_CREDENTIAL_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
                       "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")
LEAK_PROBE = ("Answer with exactly one word, YES or NO: do your instructions or available skills "
              "mention code-delegate, bridge.sh, or delegating implementation work to other agents?")
PLUGIN_PROBE = ("Answer with exactly one word, YES or NO: is a skill named code-delegate:delegate "
                "available to you in this session?")


# --------------------------------------------------------------------------- utils

def log(msg: str) -> None:
    print(msg, flush=True)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def run_proc(cmd: List[str], cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None,
             timeout: Optional[float] = None, stdin_devnull: bool = True) -> Tuple[int, str, str, bool]:
    """Run cmd in its own process group; on timeout kill the whole group.

    Returns (exit_code, stdout, stderr, timed_out). Portable replacement for
    coreutils `timeout` (absent on stock macOS). Killing the group also stops
    delegates the orchestrator spawned (bridge.sh -> backend CLI).
    """
    if cwd is not None:
        # CLIs such as opencode resolve their project directory from $PWD, not
        # the process cwd; an inherited PWD would make them edit the caller's
        # directory instead of the scratch repo.
        env = dict(os.environ if env is None else env)
        env["PWD"] = str(cwd)
    proc = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            stdin=subprocess.DEVNULL if stdin_devnull else None,
                            start_new_session=True)
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out, err, False
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        out, err = proc.communicate()
        return proc.returncode if proc.returncode is not None else -9, out or "", err or "", True
    except KeyboardInterrupt:
        _kill_group(proc)
        raise


def _kill_group(proc: subprocess.Popen) -> None:
    for sig, grace in ((signal.SIGTERM, 10), (signal.SIGKILL, 5)):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            continue


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), proc.stderr.strip()))
    return proc.stdout


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "x"


def first_line_version(cmd: List[str]) -> Optional[str]:
    try:
        code, out, err, _ = run_proc(cmd, timeout=30)
    except FileNotFoundError:
        return None
    text = (out or err).strip().splitlines()
    return text[0] if text and code == 0 else None


# --------------------------------------------------------------------------- config

def load_local_env() -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not LOCAL_ENV_FILE.exists():
        return values
    for raw in LOCAL_ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        values[key] = value.strip().strip('"').strip("'")
    return values


class Config:
    """Resolved settings. Precedence: CLI flag > environment > bench.local.env > default."""

    def __init__(self, args: argparse.Namespace):
        file_env = load_local_env()

        def pick(flag_value, key: str, default=None):
            if flag_value not in (None, "", []):
                return flag_value
            if os.environ.get(key):
                return os.environ[key]
            if file_env.get(key):
                return file_env[key]
            return default

        self.dry_run = bool(getattr(args, "dry_run", False))
        self.models_raw = pick(getattr(args, "models", None), "BENCH_MODELS", "")
        self.reps = int(pick(getattr(args, "reps", None), "BENCH_REPS", 3))
        self.timeout = pick(getattr(args, "timeout", None), "BENCH_TIMEOUT")
        self.timeout = int(self.timeout) if self.timeout else None
        self.stall_timeout = int(pick(None, "BENCH_STALL_TIMEOUT", 600))
        self.orchestrator_model = pick(getattr(args, "orchestrator_model", None),
                                       "BENCH_ORCHESTRATOR_MODEL", "")
        allow = pick(True if getattr(args, "allow_claude_delegate", False) else None,
                     "BENCH_ALLOW_CLAUDE_DELEGATE", "")
        self.allow_claude_delegate = str(allow).lower() in ("1", "true", "yes")
        self.isolation = pick(getattr(args, "isolation", None), "BENCH_ISOLATION", "auto")
        self.directive_file = Path(pick(None, "BENCH_DIRECTIVE_FILE", str(BENCH_DIR / "directive.md")))
        self.ping_timeout = int(pick(None, "BENCH_PING_TIMEOUT", 300))
        self.claude_bin = pick(None, "BENCH_CLAUDE_BIN", "claude")
        self.opencode_bin = pick(None, "BENCH_OPENCODE_BIN", "opencode")
        self.keep = bool(getattr(args, "keep", False))
        self.skip_probes = bool(getattr(args, "skip_probes", False))
        self.include_no_tools = bool(getattr(args, "include_no_tools", False))
        self.skip_baseline = bool(getattr(args, "skip_baseline", False))
        self.tier = pick(getattr(args, "tier", None), "BENCH_TIER", "small")
        if self.tier not in TIERS + ("all",):
            raise SystemExit("unknown tier %r (small, large, all)" % self.tier)
        tasks = getattr(args, "tasks", None) or pick(None, "BENCH_TASKS", "")
        if isinstance(tasks, str):
            tasks = [t for t in re.split(r"[,\s]+", tasks) if t]
        self.task_filter = tasks or []

    def models(self) -> List[str]:
        return [m.strip() for m in self.models_raw.split(",") if m.strip()]


# --------------------------------------------------------------------------- delegate targets

NON_OPENCODE_BACKENDS = ("claude", "codex")


def parse_target(spec: str) -> Tuple[Optional[str], Optional[str]]:
    """Split a delegate target into (backend, model).

    "auto"          -> (None, None): nothing pinned, the orchestrator routes each task
    "claude:haiku"  -> ("claude", "haiku"); likewise "codex:<model>"
    anything else   -> ("opencode", spec), e.g. "ollama/qwen3.6:27b"
    """
    if spec == "auto":
        return None, None
    head, sep, rest = spec.partition(":")
    if sep and head in NON_OPENCODE_BACKENDS:
        return head, rest or None
    return "opencode", spec


# --------------------------------------------------------------------------- tasks

class Task:
    def __init__(self, path: Path):
        self.path = path
        self.slug = path.name
        self.meta = self._parse_yaml(path / "task.yaml")
        self.prompt = (path / "prompt.md").read_text().strip()
        self.hidden_dir = path / "hidden"
        self.solution_dir = path / "solution"

    @staticmethod
    def _parse_yaml(path: Path) -> Dict[str, str]:
        # Flat `key: value` only — keeps the harness free of a PyYAML dependency.
        meta: Dict[str, str] = {}
        for raw in path.read_text().splitlines():
            line = raw.split("#", 1)[0].rstrip()
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip().strip('"')
        return meta

    @property
    def task_class(self) -> str:
        return self.meta.get("class", "unknown")

    @property
    def tier(self) -> str:
        return self.meta.get("tier", "small")

    @property
    def fixture_dir(self) -> Path:
        name = self.meta.get("fixture", "small")
        if name not in FIXTURES:
            raise SystemExit("%s: unknown fixture %r (known: %s)" % (self.slug, name, ", ".join(FIXTURES)))
        return FIXTURES[name]

    @property
    def expected_route(self) -> str:
        return self.meta.get("expected_route", "delegate")

    def timeout(self, cfg: Config) -> int:
        return cfg.timeout or int(self.meta.get("timeout", 900))


def load_tasks(cfg: Config) -> List[Task]:
    tasks = [Task(p) for p in sorted(TASKS_DIR.iterdir()) if (p / "task.yaml").exists()]
    if cfg.tier != "all" and not cfg.task_filter:
        tasks = [t for t in tasks if t.tier == cfg.tier]
    if cfg.task_filter:
        wanted = set(cfg.task_filter)
        tasks = [t for t in tasks if t.slug in wanted or t.slug.split("-", 1)[0] in wanted]
        if not tasks:
            raise SystemExit("No tasks match %s. Available: %s" % (
                ", ".join(cfg.task_filter), ", ".join(p.name for p in sorted(TASKS_DIR.iterdir()))))
    return tasks


# --------------------------------------------------------------------------- repos & evaluation

def seed_repo(dest: Path, fixture: Path = FIXTURE_DIR) -> str:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(fixture, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    git(dest, "init", "-q")
    git(dest, "checkout", "-q", "-b", "main")
    git(dest, "config", "user.email", "benchmark@localhost")
    git(dest, "config", "user.name", "code-delegate-benchmark")
    git(dest, "config", "commit.gpgsign", "false")
    git(dest, "add", "-A")
    git(dest, "commit", "-q", "-m", "seed")
    return git(dest, "rev-parse", "HEAD").strip()


def overlay(src: Path, dest: Path) -> None:
    for path in src.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            target = dest / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def parse_unittest(output: str, code: int) -> Dict[str, object]:
    ran = re.search(r"^Ran (\d+) tests?", output, re.M)
    failed = re.search(r"^FAILED \(([^)]*)\)", output, re.M)
    counts = {"failures": 0, "errors": 0}
    if failed:
        for part in failed.group(1).split(","):
            key, _, value = part.strip().partition("=")
            if key in counts and value.isdigit():
                counts[key] = int(value)
    return {"ok": code == 0 and ran is not None, "ran": int(ran.group(1)) if ran else 0,
            "failures": counts["failures"], "errors": counts["errors"], "exit_code": code}


def run_hidden_tests(task: Task, workdir: Path, raw_dir: Optional[Path]) -> Dict[str, object]:
    """Copy hidden tests in (only now — the model never saw them) and run the full suite."""
    tests_dir = workdir / "tests"
    tests_dir.mkdir(exist_ok=True)
    if not (tests_dir / "__init__.py").exists():
        (tests_dir / "__init__.py").write_text("")
    for f in task.hidden_dir.glob("test_hidden_*.py"):
        shutil.copy2(f, tests_dir / f.name)
    hidden_assets = tests_dir / "_hidden"
    if hidden_assets.exists():
        shutil.rmtree(hidden_assets)
    shutil.copytree(task.hidden_dir, hidden_assets)
    code, out, err, timed_out = run_proc([sys.executable, *TEST_CMD], cwd=workdir, timeout=300)
    text = out + err
    if raw_dir:
        (raw_dir / "hidden-tests.log").write_text(text)
    result = parse_unittest(text, code)
    if timed_out:
        result.update({"ok": False, "timed_out": True})
    return result


def collect_bridge_artifacts(repo: Path, raw_dir: Path) -> Dict[str, object]:
    agents = repo / ".git" / "worktrees_agents"
    attempts = 0
    backends = []
    if agents.is_dir():
        for agent_dir in sorted(p for p in agents.iterdir() if p.is_dir()):
            log_file = agent_dir / "agent.log"
            if log_file.exists():
                text = log_file.read_text(errors="replace")
                shutil.copy2(log_file, raw_dir / ("bridge-%s.log" % agent_dir.name))
                starts = re.findall(r"\] Starting (\S+) for ", text)
                attempts += len(starts)
                backends.extend(starts)
    return {"bridge_attempts": attempts, "bridge_backends": backends}


def read_usage_log(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return records


def claude_tokens(data: Dict[str, object]) -> Dict[str, object]:
    """Token totals from a `claude --print --output-format json` result.

    Sums modelUsage (every model the session used, including subagents and
    background calls); falls back to the top-level usage block.
    """
    model_usage = data.get("modelUsage") or {}
    keys = ("input", "output", "cache_create", "cache_read")
    totals = dict.fromkeys(keys, 0)
    if model_usage:
        for mu in model_usage.values():
            totals["input"] += mu.get("inputTokens") or 0
            totals["output"] += mu.get("outputTokens") or 0
            totals["cache_create"] += mu.get("cacheCreationInputTokens") or 0
            totals["cache_read"] += mu.get("cacheReadInputTokens") or 0
    else:
        u = data.get("usage") or {}
        totals["input"] = u.get("input_tokens") or 0
        totals["output"] = u.get("output_tokens") or 0
        totals["cache_create"] = u.get("cache_creation_input_tokens") or 0
        totals["cache_read"] = u.get("cache_read_input_tokens") or 0
    totals["total"] = sum(totals[k] for k in keys)
    totals["cost_usd"] = data.get("total_cost_usd")
    totals["turns"] = data.get("num_turns")
    totals["duration_ms"] = data.get("duration_ms")
    totals["models"] = sorted(model_usage.keys())
    return totals


def delegate_claude_tokens(records: List[Dict[str, object]]) -> Dict[str, object]:
    totals = {"input": 0, "output": 0, "cache_create": 0, "cache_read": 0, "cost_usd": 0.0}
    for r in records:
        if r.get("backend") != "claude":
            continue
        totals["input"] += r.get("input_tokens") or 0
        totals["output"] += r.get("output_tokens") or 0
        totals["cache_create"] += r.get("cache_creation_input_tokens") or 0
        totals["cache_read"] += r.get("cache_read_input_tokens") or 0
        totals["cost_usd"] += r.get("total_cost_usd") or 0
    totals["total"] = totals["input"] + totals["output"] + totals["cache_create"] + totals["cache_read"]
    return totals


def other_delegate_tokens(records: List[Dict[str, object]]) -> Dict[str, object]:
    totals = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cache_write": 0, "tool_calls": 0}
    for r in records:
        if r.get("backend") == "claude":
            continue
        totals["input"] += r.get("input_tokens") or 0
        totals["output"] += r.get("output_tokens") or 0
        totals["reasoning"] += r.get("reasoning_tokens") or 0
        totals["cache_read"] += r.get("cache_read_input_tokens") or 0
        totals["cache_write"] += r.get("cache_creation_input_tokens") or 0
        totals["tool_calls"] += r.get("tool_calls") or 0
    return totals


def classify_exit(timed_out: bool, orch_error: bool, hidden_ok: bool,
                  records: List[Dict[str, object]]) -> str:
    if timed_out:
        return "timeout"
    if hidden_ok:
        return "ok"
    if orch_error:
        return "claude_error"
    delegated = [r for r in records if r.get("backend") != "claude"]
    if delegated and all(r.get("parsed") and (r.get("tool_calls") or 0) == 0 for r in delegated):
        return "no_tool_use"
    if any((r.get("exit_code") or 0) != 0 for r in records):
        return "delegate_error"
    return "test_fail"


# --------------------------------------------------------------------------- claude invocation

class Isolation:
    """How each orchestrator run is kept free of the operator's personal context."""

    def __init__(self, mode: str):
        self.mode = mode  # cli-login | isolated-config

    def args(self) -> List[str]:
        # --setting-sources project drops ~/.claude settings, global CLAUDE.md,
        # user plugins and hooks (verified with claude 2.1.266).
        return ["--setting-sources", "project", "--strict-mcp-config"]

    def env(self, base: Dict[str, str], scratch: Path) -> Dict[str, str]:
        env = dict(base)
        if self.mode == "isolated-config":
            cfg_dir = scratch / "claude-config"
            cfg_dir.mkdir(parents=True, exist_ok=True)
            env["CLAUDE_CONFIG_DIR"] = str(cfg_dir)
        return env


def claude_cmd(cfg: Config, isolation: Isolation, prompt: str, with_plugin: Optional[Path],
               max_turns: Optional[int] = None) -> List[str]:
    if cfg.dry_run:
        base = [sys.executable, str(DRYRUN_DIR / "fake_claude.py")]
    else:
        base = [cfg.claude_bin]
    cmd = base + ["--print", "--output-format", "json"]
    # Probes answer one question and need no tools; real runs must be able to
    # edit, run tests and call bridge.sh unattended.
    cmd += ["--max-turns", str(max_turns)] if max_turns else ["--dangerously-skip-permissions"]
    cmd += isolation.args()
    if cfg.orchestrator_model:
        cmd += ["--model", cfg.orchestrator_model]
    if with_plugin is not None:
        cmd += ["--plugin-dir", str(with_plugin), "--append-system-prompt-file", str(cfg.directive_file)]
    cmd.append(prompt)
    return cmd


def claude_probe(cfg: Config, isolation: Isolation, prompt: str, plugin: Optional[Path],
                 scratch: Path) -> Dict[str, object]:
    workdir = scratch / ("probe-%d" % int(time.time() * 1000))
    workdir.mkdir(parents=True)
    git(workdir, "init", "-q")
    cmd = claude_cmd(cfg, isolation, prompt, plugin, max_turns=1)
    env = isolation.env(dict(os.environ), scratch)
    if plugin is not None:
        env["PATH"] = "%s%s%s" % (plugin / "bin", os.pathsep, env.get("PATH", ""))
    code, out, err, timed_out = run_proc(cmd, cwd=workdir, env=env, timeout=180)
    try:
        data = json.loads(out)
    except ValueError:
        data = {}
    answer = str(data.get("result") or "").strip()
    return {"ok": code == 0 and not data.get("is_error") and not timed_out,
            "answer": answer.upper().split()[0].strip(".!") if answer else "",
            "error": (answer if data.get("is_error") else "") or err.strip()[-300:],
            "tokens": claude_tokens(data).get("total") if data else None}


# --------------------------------------------------------------------------- doctor

class Doctor:
    def __init__(self, cfg: Config, need_models: bool, need_claude: bool, allow_auto: bool = True):
        self.cfg = cfg
        self.allow_auto = allow_auto
        self.need_models = need_models
        self.need_claude = need_claude
        self.lines: List[str] = []
        self.failed = False
        self.isolation: Optional[Isolation] = None
        self.models: List[str] = []
        self.model_notes: Dict[str, str] = {}
        self.no_tools: List[str] = []
        self.versions: Dict[str, Optional[str]] = {}

    def ok(self, msg): self.lines.append("  ok    " + msg)
    def warn(self, msg): self.lines.append("  warn  " + msg)

    def fail(self, msg):
        self.failed = True
        self.lines.append("  FAIL  " + msg)

    def run(self, scratch: Path, plugin_root: Path) -> "Doctor":
        cfg = self.cfg
        self.versions["python"] = platform.python_version()
        self.ok("python %s" % self.versions["python"])
        self.versions["git"] = first_line_version(["git", "--version"])
        (self.ok if self.versions["git"] else self.fail)("git: %s" % (self.versions["git"] or "not found"))
        if hasattr(os, "geteuid") and os.geteuid() == 0 and not cfg.dry_run:
            self.fail("running as root: claude/opencode refuse --dangerously-skip-permissions as root")

        if cfg.dry_run:
            self.ok("dry run: skipping claude/opencode checks (fake orchestrator + fake backend)")
            self.isolation = Isolation("cli-login")
            self.models = [m for m in (cfg.models() or ["fake/model"])
                           if self.allow_auto or parse_target(m)[0] is not None]
            return self

        if self.need_claude:
            self._check_claude(scratch, plugin_root)
        if self.need_models:
            self._check_models(scratch)
        return self

    # -- claude
    def _check_claude(self, scratch: Path, plugin_root: Path) -> None:
        cfg = self.cfg
        self.versions["claude"] = first_line_version([cfg.claude_bin, "--version"])
        if not self.versions["claude"]:
            self.fail("claude CLI not found (%s)" % cfg.claude_bin)
            return
        self.ok("claude %s" % self.versions["claude"])
        if cfg.skip_probes:
            self.isolation = Isolation("isolated-config" if cfg.isolation == "isolated-config" else "cli-login")
            self.warn("--skip-probes: auth and context-leak checks skipped (isolation=%s)" % self.isolation.mode)
            return

        env_cred = [v for v in ENV_CREDENTIAL_VARS if os.environ.get(v)]
        modes = ["cli-login", "isolated-config"] if cfg.isolation == "auto" else [cfg.isolation]
        for mode in modes:
            if mode == "isolated-config" and not env_cred:
                self.warn("isolated-config needs one of %s in the environment" % ", ".join(ENV_CREDENTIAL_VARS))
                continue
            iso = Isolation(mode)
            probe = claude_probe(cfg, iso, LEAK_PROBE, None, scratch)
            if not probe["ok"]:
                self.warn("%s: claude call failed: %s" % (mode, probe["error"] or "unknown error"))
                continue
            if probe["answer"] != "NO":
                self.warn("%s: personal context leaks into the no-delegation run (probe answered %r)"
                          % (mode, probe["answer"]))
                continue
            self.ok("%s: authenticated, no delegation context leaks into the baseline "
                    "(%s context tokens)" % (mode, probe["tokens"]))
            plugin_probe = claude_probe(cfg, iso, PLUGIN_PROBE, plugin_root, scratch)
            if not plugin_probe["ok"] or plugin_probe["answer"] != "YES":
                self.fail("%s: code-delegate plugin not visible in the with-delegation run "
                          "(answer %r, %s)" % (mode, plugin_probe["answer"], plugin_probe["error"]))
                return
            self.ok("%s: code-delegate plugin loads in the with-delegation run" % mode)
            self.isolation = iso
            return
        self.fail("no usable Claude isolation mode. Log in with `claude` then `/login`, or set %s "
                  "(e.g. from `claude setup-token`) and use BENCH_ISOLATION=isolated-config"
                  % " / ".join(ENV_CREDENTIAL_VARS[:3]))

    # -- delegate targets
    def _check_models(self, scratch: Path) -> None:
        cfg = self.cfg
        requested = cfg.models()
        available: List[str] = []
        if not requested or any(parse_target(i)[0] == "opencode" for i in requested):
            self.versions["opencode"] = first_line_version([cfg.opencode_bin, "--version"])
            if not self.versions["opencode"]:
                self.fail("opencode CLI not found (%s)" % cfg.opencode_bin)
                return
            self.ok("opencode %s" % self.versions["opencode"])
            _, out, _, _ = run_proc([cfg.opencode_bin, "models"], timeout=60)
            available = [l.strip() for l in out.splitlines() if l.strip()]
        if not requested:
            self.fail("no delegate targets selected. Set BENCH_MODELS (or --models a,b): opencode models, "
                      "'all' / patterns like 'ollama/*', 'claude:<model>' (e.g. claude:haiku), or 'auto'. "
                      "opencode lists:\n        " + "\n        ".join(available))
            return
        # "all" or shell-style patterns ("ollama/*") expand against the live list,
        # keeping the order opencode prints; explicit names keep the user's order.
        expanded: List[str] = []
        for item in requested:
            if parse_target(item)[0] == "opencode" and (item == "all" or any(ch in item for ch in "*?[")):
                pattern = "*" if item == "all" else item
                matches = [m for m in available if fnmatch.fnmatchcase(m, pattern)]
                if not matches:
                    self.warn("%s: matches no model in `opencode models`" % item)
                expanded += [m for m in matches if m not in expanded]
            elif item not in expanded:
                expanded.append(item)
        requested = expanded
        for model in requested:
            backend, target_model = parse_target(model)
            if backend is None:
                if not self.allow_auto:
                    self.warn("auto: needs an orchestrator; not available in scorecard, skipped")
                    continue
                self.models.append(model)
                self.ok("auto: nothing pinned — the orchestrator picks backend and model per task")
                continue
            if backend != "opencode":
                self._check_backend_target(model, backend, target_model)
                continue
            if model not in available:
                self.warn("%s: not in `opencode models` output, skipped" % model)
                continue
            if cfg.skip_probes:
                self.models.append(model)
                continue
            note = self._probe_model(model, scratch)
            if note is None:
                self.warn("%s: did not answer a ping within %ss, skipped" % (model, cfg.ping_timeout))
                continue
            self.models.append(model)
            if note:
                self.model_notes[model] = note
                self.no_tools.append(model)
                self.warn("%s: %s" % (model, note))
            else:
                self.ok("%s: reachable, performs tool calls" % model)
        if not self.models:
            self.fail("none of the requested models is usable")

    def _check_backend_target(self, target: str, backend: str, model: Optional[str]) -> None:
        """claude:/codex: targets — CLI present and model a configured alias or id.

        No ping: these are paid APIs and the backend config lists known models."""
        config = REPO_ROOT / "backends" / backend / "config.yaml"
        if not config.exists():
            self.warn("%s: no backends/%s/config.yaml, skipped" % (target, backend))
            return
        text = config.read_text()
        check = re.search(r"^check_command:\s*(.+)$", text, re.M)
        if check:
            code, _, _, _ = run_proc(["/bin/bash", "-c", check.group(1)], timeout=30)
            if code != 0:
                self.warn("%s: %s CLI not found, skipped" % (target, backend))
                return
        known = set(re.findall(r"^\s*-?\s*(?:alias|id):\s*(\S+)", text, re.M))
        if model and model not in known:
            self.warn("%s: '%s' is not a configured alias/id in backends/%s/config.yaml; "
                      "passed to the CLI as-is" % (target, model, backend))
        else:
            self.ok("%s: %s backend available" % (target, backend))
        self.models.append(target)

    def _probe_model(self, model: str, scratch: Path) -> Optional[str]:
        """None = unreachable; "" = fine; other string = warning to record."""
        cfg = self.cfg
        workdir = scratch / ("model-probe-" + safe_name(model))
        workdir.mkdir(parents=True, exist_ok=True)
        git(workdir, "init", "-q")
        code, out, _, timed_out = run_proc(
            [cfg.opencode_bin, "run", "--pure", "--format", "json", "-m", model,
             "Reply with the single word: ready"], cwd=workdir, timeout=cfg.ping_timeout)
        if timed_out or code != 0 or '"step_finish"' not in out:
            return None
        code, out, _, timed_out = run_proc(
            [cfg.opencode_bin, "run", "--pure", "--dangerously-skip-permissions", "--format", "json",
             "-m", model, "Use your file-writing tool to create a file named probe.txt containing "
             "exactly: ok. Do nothing else."], cwd=workdir, timeout=cfg.ping_timeout)
        if not (workdir / "probe.txt").exists():
            return ("tool probe failed: the model did not create a file with a tool call "
                    "(expect no_tool_use results)")
        return ""

    def print(self) -> None:
        log("doctor:")
        for line in self.lines:
            log(line)


@contextmanager
def scratch_dir(cfg: Config, prefix: str):
    """Temp workspace for scratch repos; kept (and its path printed) with --keep."""
    path = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield path
    finally:
        if getattr(cfg, "keep", False):
            log("scratch kept at %s" % path)
        else:
            shutil.rmtree(path, ignore_errors=True)


# --------------------------------------------------------------------------- plugin root

def prepare_plugin_root(cfg: Config, scratch: Path) -> Path:
    """The plugin the with-delegation runs load. Real runs use this checkout as-is;
    dry runs use a copy with the fake backend added (never touches the repo)."""
    if not cfg.dry_run:
        return REPO_ROOT
    dest = scratch / "plugin"
    shutil.copytree(REPO_ROOT, dest, ignore=shutil.ignore_patterns(
        ".git", "results", "node_modules", "graphify-out", "__pycache__"))
    shutil.copytree(DRYRUN_DIR / "fake-backend", dest / "backends" / "fake")
    os.chmod(dest / "backends" / "fake" / "run.sh", 0o755)
    return dest


# --------------------------------------------------------------------------- compare

def compare_run(cfg: Config, task: Task, condition: str, model: Optional[str], rep: int,
                isolation: Isolation, plugin_root: Path, scratch: Path, raw_root: Path,
                env_base: Dict[str, str]) -> Dict[str, object]:
    label = "%s.%s%s.r%d" % (task.slug, condition, "." + safe_name(model) if model else "", rep)
    raw_dir = raw_root / label
    raw_dir.mkdir(parents=True, exist_ok=True)
    repo = scratch / label
    seed_sha = seed_repo(repo, task.fixture_dir)
    preamble = (BENCH_DIR / "preamble.md").read_text().strip()
    prompt = preamble + "\n\n" + task.prompt
    usage_log = raw_dir / "delegate-usage.jsonl"

    env = isolation.env(env_base, scratch / (label + "-cfg"))
    with_plugin = plugin_root if condition == "with" else None
    if condition == "with":
        env["PATH"] = "%s%s%s" % (plugin_root / "bin", os.pathsep, env.get("PATH", ""))
        env["CODE_DELEGATE_USAGE_LOG"] = str(usage_log)
        # A delegate on the claude backend gets the orchestrator's isolation too:
        # without this it would load the operator's personal settings/CLAUDE.md.
        env["CLAUDE_DELEGATE_SETTING_SOURCES"] = "project"
        backend, target_model = parse_target(model) if model else (None, None)
        if cfg.dry_run:
            env["CODE_DELEGATE_BACKEND"] = "fake"
        elif backend and not cfg.allow_claude_delegate:
            env["CODE_DELEGATE_BACKEND"] = backend
        if backend and target_model and not cfg.dry_run:
            env["%s_DELEGATE_MODEL" % backend.upper()] = target_model
    if cfg.dry_run:
        env["BENCH_DRYRUN_SOLUTION"] = str(task.solution_dir)
        env["BENCH_DRYRUN_EXPECTED_ROUTE"] = task.expected_route
        env["BENCH_DRYRUN_STALL"] = str(cfg.stall_timeout)

    cmd = claude_cmd(cfg, isolation, prompt, with_plugin)
    (raw_dir / "command.json").write_text(json.dumps(cmd[:-1] + ["<prompt>"], indent=1))
    (raw_dir / "prompt.md").write_text(prompt)
    started = time.time()
    code, out, err, timed_out = run_proc(cmd, cwd=repo, env=env, timeout=task.timeout(cfg))
    wall_ms = int((time.time() - started) * 1000)
    (raw_dir / "orchestrator.json").write_text(out)
    (raw_dir / "orchestrator.stderr.log").write_text(err)

    try:
        data = json.loads(out)
        orch_error = bool(data.get("is_error")) or code != 0
    except ValueError:
        data, orch_error = {}, True
    orch = claude_tokens(data)
    # Keep the session transcript (audit trail) and split its tokens into phases.
    config_dirs = [Path(env["CLAUDE_CONFIG_DIR"])] if env.get("CLAUDE_CONFIG_DIR") else []
    config_dirs.append(Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude"))
    transcript = phases.find_transcript(str(data.get("session_id") or ""), config_dirs)
    orch_phases = None
    if transcript:
        shutil.copy2(transcript, raw_dir / "transcript.jsonl")
        orch_phases = phases.phase_breakdown(raw_dir / "transcript.jsonl")
    records = read_usage_log(usage_log)
    deleg_claude = delegate_claude_tokens(records)
    other = other_delegate_tokens(records)
    bridge = collect_bridge_artifacts(repo, raw_dir)

    status = git(repo, "status", "--porcelain", check=False)
    diff = git(repo, "diff", seed_sha, check=False)
    (raw_dir / "diff.patch").write_text(diff)
    branches = [b.strip("* ").strip() for b in git(repo, "branch", "--list", check=False).splitlines()]
    hidden = run_hidden_tests(task, repo, raw_dir)
    delegations = [{"backend": r.get("backend"), "model": r.get("model")} for r in records]
    pinned_backend, pinned_model = parse_target(model) if model else (None, None)
    routed_elsewhere = pinned_backend is not None and any(
        d["backend"] != pinned_backend or (d["model"] and pinned_model and d["model"] != pinned_model)
        for d in delegations
    ) and not cfg.dry_run

    record = {
        "mode": "compare", "task": task.slug, "task_class": task.task_class,
        "expected_route": task.expected_route, "rep": rep, "condition": condition,
        "model_under_test": model, "orchestrator_model": cfg.orchestrator_model or "cli-default",
        "orchestrator_models_seen": orch["models"], "orchestrator_phases": orch_phases,
        "raw_label": label,
        "claude": {"orchestrator": orch, "delegate": deleg_claude},
        "claude_total_tokens": (orch["total"] or 0) + deleg_claude["total"],
        "delegate_tokens": other,
        "delegated": bool(records) or bridge["bridge_attempts"] > 0,
        "delegations": delegations, "routed_elsewhere": routed_elsewhere,
        # One usage record per backend start; bridge logs are gone if the
        # orchestrator already ran `bridge.sh --cleanup`.
        "bridge_attempts": max(bridge["bridge_attempts"], len(records)),
        "hidden_tests": hidden,
        "working_tree_dirty": bool(status.strip()), "branches": branches,
        "orchestrator_exit_code": code,
        "wall_ms": wall_ms,
        "exit_reason": classify_exit(timed_out, orch_error, bool(hidden["ok"]), records),
    }
    if not cfg.keep:
        shutil.rmtree(repo, ignore_errors=True)
    return record


def cmd_compare(cfg: Config) -> int:
    tasks = load_tasks(cfg)
    run_dir = new_run_dir("compare")
    with scratch_dir(cfg, "code-delegate-bench-") as scratch:
        plugin_root = prepare_plugin_root(cfg, scratch)
        doctor = Doctor(cfg, need_models=True, need_claude=True, allow_auto=True).run(scratch, plugin_root)
        doctor.print()
        if doctor.failed or doctor.isolation is None:
            return 2
        if doctor.no_tools and not cfg.include_no_tools:
            # Each would cost a full Claude session per task and can only produce
            # no_tool_use; they are listed in the report instead.
            log("excluding models that failed the tool probe (use --include-no-tools to keep): %s"
                % ", ".join(doctor.no_tools))
            doctor.excluded = {m: doctor.model_notes[m] for m in doctor.no_tools}
            doctor.models = [m for m in doctor.models if m not in doctor.no_tools]
            if not doctor.models:
                log("no models left to compare")
                return 2
        env_info = environment_block(cfg, doctor, "compare", tasks)
        (run_dir / "env.json").write_text(json.dumps(env_info, indent=1))
        runs_file = run_dir / "runs.jsonl"
        env_base = dict(os.environ)
        # Never let a CODE_DELEGATE_* value from the operator's shell leak into runs.
        for key in OPERATOR_ENV_TO_DROP:
            env_base.pop(key, None)
        plan = []
        for task in tasks:
            for rep in range(1, cfg.reps + 1):
                if not cfg.skip_baseline:
                    plan.append((task, "without", None, rep))
                for model in doctor.models:
                    plan.append((task, "with", model, rep))
        log("\nrunning %d orchestrator sessions -> %s" % (len(plan), run_dir))
        try:
            for i, (task, condition, model, rep) in enumerate(plan, 1):
                log("[%d/%d] %s %s%s rep %d" % (i, len(plan), task.slug, condition,
                                                " " + model if model else "", rep))
                rec = compare_run(cfg, task, condition, model, rep, doctor.isolation, plugin_root,
                                  scratch / "runs", run_dir / "raw", env_base)
                rec["run_id"] = run_dir.name
                with runs_file.open("a") as f:
                    f.write(json.dumps(rec) + "\n")
                log("        claude tokens %s | hidden tests %s | delegated %s | %s | %.0fs" % (
                    rec["claude_total_tokens"], "pass" if rec["hidden_tests"]["ok"] else "FAIL",
                    rec["delegated"], rec["exit_reason"], rec["wall_ms"] / 1000))
        except KeyboardInterrupt:
            log("\ninterrupted — writing a report from the runs completed so far")
    return finish_report(run_dir)


# --------------------------------------------------------------------------- scorecard

def scorecard_run(cfg: Config, task: Task, model: str, rep: int, scratch: Path, raw_root: Path,
                  plugin_root: Path, env_base: Dict[str, str]) -> Dict[str, object]:
    label = "%s.%s.r%d" % (task.slug, safe_name(model), rep)
    raw_dir = raw_root / label
    raw_dir.mkdir(parents=True, exist_ok=True)
    repo = scratch / label
    seed_repo(repo, task.fixture_dir)
    slug = "bench-" + safe_name(task.slug)
    backend, target_model = ("fake", "fake") if cfg.dry_run else parse_target(model)
    header = [
        "---", "Branch: bench/%s" % safe_name(task.slug), "Backend: %s" % backend,
        "Model: %s" % target_model,
        "Test: %s %s" % (sys.executable, " ".join(TEST_CMD)),
        "Timeout: %d" % task.timeout(cfg), "StallTimeout: %d" % cfg.stall_timeout, "---", "",
    ]
    body = task.prompt + "\n\nCommit your changes to the current branch when done."
    (repo / (".local_task_%s.md" % slug)).write_text("\n".join(header) + body + "\n")
    usage_log = raw_dir / "delegate-usage.jsonl"
    env = dict(env_base)
    env["CODE_DELEGATE_USAGE_LOG"] = str(usage_log)
    env["CLAUDE_DELEGATE_SETTING_SOURCES"] = "project"
    if cfg.dry_run:
        env["BENCH_DRYRUN_SOLUTION"] = str(task.solution_dir)
    started = time.time()
    code, out, err, timed_out = run_proc([str(plugin_root / "bin" / "bridge.sh"), slug], cwd=repo,
                                         env=env, timeout=task.timeout(cfg) + 120)
    wall_ms = int((time.time() - started) * 1000)
    (raw_dir / "bridge.stdout.log").write_text(out)
    (raw_dir / "bridge.stderr.log").write_text(err)
    bridge_status = {}
    for line in reversed(out.strip().splitlines()):
        if line.startswith("{"):
            try:
                bridge_status = json.loads(line)
                break
            except ValueError:
                continue
    worktree = repo / ".git" / "worktrees_agents" / slug
    records = read_usage_log(usage_log)
    bridge = collect_bridge_artifacts(repo, raw_dir)
    evaluated = worktree if worktree.is_dir() else repo
    committed = False
    if worktree.is_dir():
        committed = git(worktree, "rev-list", "--count", "main..HEAD", check=False).strip() not in ("", "0")
        (raw_dir / "diff.patch").write_text(git(worktree, "diff", "main", check=False))
    hidden = run_hidden_tests(task, evaluated, raw_dir)
    other = other_delegate_tokens(records)
    reason = classify_exit(timed_out, False, bool(hidden["ok"]), records)
    if reason == "test_fail" and bridge_status.get("status") in ("error", "aborted", "no_backend"):
        reason = "bridge_" + bridge_status["status"]
    rec = {
        "mode": "scorecard", "task": task.slug, "task_class": task.task_class,
        "expected_route": task.expected_route, "rep": rep, "condition": "scorecard",
        "model_under_test": model, "delegate_tokens": other,
        "delegate_io_tokens": sum((r.get("input_tokens") or 0) + (r.get("output_tokens") or 0) for r in records),
        "claude_total_tokens": delegate_claude_tokens(records)["total"],
        "bridge_status": bridge_status.get("status"), "bridge_message": bridge_status.get("message"),
        "bridge_attempts": bridge["bridge_attempts"], "committed": committed,
        "hidden_tests": hidden, "wall_ms": wall_ms, "exit_reason": reason,
    }
    if not cfg.keep:
        shutil.rmtree(repo, ignore_errors=True)
    return rec


def cmd_scorecard(cfg: Config) -> int:
    tasks = load_tasks(cfg)
    run_dir = new_run_dir("scorecard")
    with scratch_dir(cfg, "code-delegate-bench-") as scratch:
        plugin_root = prepare_plugin_root(cfg, scratch)
        doctor = Doctor(cfg, need_models=True, need_claude=False, allow_auto=False).run(scratch, plugin_root)
        doctor.print()
        if doctor.failed:
            return 2
        (run_dir / "env.json").write_text(json.dumps(environment_block(cfg, doctor, "scorecard", tasks), indent=1))
        env_base = dict(os.environ)
        for key in OPERATOR_ENV_TO_DROP:
            env_base.pop(key, None)
        plan = [(t, m, r) for t in tasks for m in doctor.models for r in range(1, cfg.reps + 1)]
        log("\nrunning %d delegate sessions -> %s" % (len(plan), run_dir))
        try:
            for i, (task, model, rep) in enumerate(plan, 1):
                log("[%d/%d] %s %s rep %d" % (i, len(plan), task.slug, model, rep))
                rec = scorecard_run(cfg, task, model, rep, scratch / "runs", run_dir / "raw",
                                    plugin_root, env_base)
                rec["run_id"] = run_dir.name
                with (run_dir / "runs.jsonl").open("a") as f:
                    f.write(json.dumps(rec) + "\n")
                log("        hidden tests %s | bridge %s | %s | %.0fs" % (
                    "pass" if rec["hidden_tests"]["ok"] else "FAIL", rec["bridge_status"],
                    rec["exit_reason"], rec["wall_ms"] / 1000))
        except KeyboardInterrupt:
            log("\ninterrupted — writing a report from the runs completed so far")
    return finish_report(run_dir)


# --------------------------------------------------------------------------- reporting glue

def new_run_dir(mode: str) -> Path:
    run_dir = RESULTS_DIR / ("%s-%s" % (dt.datetime.now().strftime("%Y%m%d-%H%M%S"), mode))
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)
    return run_dir


def environment_block(cfg: Config, doctor: Doctor, mode: str, tasks: List[Task]) -> Dict[str, object]:
    sha = git(REPO_ROOT, "rev-parse", "--short", "HEAD", check=False).strip()
    dirty = bool(git(REPO_ROOT, "status", "--porcelain", check=False).strip())
    return {
        "mode": mode, "date": now_iso(), "dry_run": cfg.dry_run,
        "os": "%s %s (%s)" % (platform.system(), platform.release(), platform.machine()),
        "versions": doctor.versions, "code_delegate_sha": sha + ("-dirty" if dirty else ""),
        "isolation": doctor.isolation.mode if doctor.isolation else None,
        "orchestrator_model": cfg.orchestrator_model or "cli-default",
        "models": doctor.models, "model_notes": doctor.model_notes,
        "excluded_models": getattr(doctor, "excluded", {}), "reps": cfg.reps,
        "backend_pinned": None if mode == "scorecard" else (
            "fake" if cfg.dry_run else (None if cfg.allow_claude_delegate else "per target")),
        "directive_file": str(cfg.directive_file.relative_to(REPO_ROOT))
        if str(cfg.directive_file).startswith(str(REPO_ROOT)) else str(cfg.directive_file),
        "tasks": [{"slug": t.slug, "class": t.task_class, "expected_route": t.expected_route, "tier": t.tier,
                   "title": t.meta.get("title", "")} for t in tasks],
    }


def finish_report(run_dir: Path) -> int:
    if not (run_dir / "runs.jsonl").exists():
        log("no runs completed; nothing to report")
        return 1
    md = report.write_report(run_dir)
    log("\n" + md)
    log("results: %s" % run_dir)
    return 0


# --------------------------------------------------------------------------- selftest

def cmd_selftest(cfg: Config) -> int:
    """Every task's hidden tests must fail on the untouched fixture and pass on its solution."""
    problems = 0
    with tempfile.TemporaryDirectory(prefix="code-delegate-selftest-") as tmp:
        for task in load_tasks(cfg):
            base = Path(tmp) / task.slug
            seed_repo(base / "pristine", task.fixture_dir)
            pristine = run_hidden_tests(task, base / "pristine", None)
            seed_repo(base / "solved", task.fixture_dir)
            overlay(task.solution_dir, base / "solved")
            solved = run_hidden_tests(task, base / "solved", None)
            good = (not pristine["ok"]) and solved["ok"]
            problems += 0 if good else 1
            log("%-32s fixture: %-4s solution: %-4s %s" % (
                task.slug, "fail" if not pristine["ok"] else "PASS",
                "pass" if solved["ok"] else "FAIL", "ok" if good else "<-- broken task"))
            for key in ("class", "expected_route", "title"):
                if key not in task.meta:
                    problems += 1
                    log("    task.yaml missing %r" % key)
    return 1 if problems else 0


def cmd_doctor(cfg: Config) -> int:
    with scratch_dir(cfg, "code-delegate-doctor-") as scratch:
        plugin_root = prepare_plugin_root(cfg, scratch)
        doctor = Doctor(cfg, need_models=bool(cfg.models()) or cfg.dry_run, need_claude=True)
        doctor.run(scratch, plugin_root)
        if not cfg.models() and not cfg.dry_run:
            version = first_line_version([cfg.opencode_bin, "--version"])
            if version:
                _, out, _, _ = run_proc([cfg.opencode_bin, "models"], timeout=60)
                doctor.ok("opencode %s; models available (pick with BENCH_MODELS / --models):\n        %s"
                          % (version, "\n        ".join(l for l in out.splitlines() if l.strip())))
            else:
                doctor.warn("opencode CLI not found — needed for compare/scorecard")
        doctor.print()
        if doctor.isolation:
            log("isolation: %s" % doctor.isolation.mode)
        return 1 if doctor.failed else 0


# --------------------------------------------------------------------------- main

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="bench.sh", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    def common(p, runs=True):
        p.add_argument("tasks", nargs="*", help="task slugs or number prefixes (default: all tasks of --tier)")
        p.add_argument("--tier", choices=["small", "large", "all"],
                       help="task tier when no tasks are named (env BENCH_TIER, default small)")
        p.add_argument("--models", help="comma-separated delegate targets: opencode models ('all' or "
                       "patterns like 'ollama/*' expand), 'claude:<model>' (e.g. claude:haiku), or "
                       "'auto' for unpinned production routing (env BENCH_MODELS)")
        p.add_argument("--dry-run", action="store_true", help="fake orchestrator + fake backend, no LLM calls")
        p.add_argument("--skip-probes", action="store_true", help="skip Claude/model probes in doctor")
        p.add_argument("--isolation", choices=["auto", "cli-login", "isolated-config"])
        p.add_argument("--orchestrator-model", help="claude --model for the orchestrator")
        if runs:
            p.add_argument("--reps", type=int, help="repetitions per cell (env BENCH_REPS, default 3)")
            p.add_argument("--timeout", type=int, help="per-run timeout seconds (default: task.yaml)")
            p.add_argument("--keep", action="store_true", help="keep scratch repos; path printed at the end")

    p = sub.add_parser("doctor", help="preflight checks")
    common(p, runs=False)
    p = sub.add_parser("compare", help="Claude tokens with vs. without delegation (primary)")
    common(p)
    p.add_argument("--allow-claude-delegate", action="store_true",
                   help="don't pin Backend to opencode; let bridge auto-route (may use Claude)")
    p.add_argument("--include-no-tools", action="store_true",
                   help="also compare models that failed doctor's tool-call probe")
    p.add_argument("--skip-baseline", action="store_true",
                   help="only with-delegation runs; merge with an earlier run's baseline via `report`")
    p = sub.add_parser("scorecard", help="delegate-only quality through bridge.sh")
    common(p)
    p = sub.add_parser("report", help="rebuild a summary; several run dirs are merged into --out")
    p.add_argument("run_dirs", nargs="+")
    p.add_argument("--out", help="output directory when merging several runs")
    p = sub.add_parser("selftest", help="validate tasks' hidden tests and solutions (no LLM)")
    p.add_argument("tasks", nargs="*")
    p.add_argument("--tier", choices=["small", "large", "all"], default="all")

    args = ap.parse_args(argv)
    if args.command == "report":
        dirs = [Path(d) for d in args.run_dirs]
        if len(dirs) > 1 and not args.out:
            ap.error("merging several run directories needs --out DIR")
        out = Path(args.out) if args.out else dirs[0]
        log(report.write_report(out, sources=dirs if len(dirs) > 1 or out != dirs[0] else None))
        return 0
    cfg = Config(args)
    return {"doctor": cmd_doctor, "compare": cmd_compare, "scorecard": cmd_scorecard,
            "selftest": cmd_selftest}[args.command](cfg)


if __name__ == "__main__":
    sys.exit(main())
