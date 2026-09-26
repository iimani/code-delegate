#!/usr/bin/env python3
"""Stand-in for `claude --print --output-format json` in `bench.sh --dry-run`.

Exercises the harness end to end without any LLM: the "without" condition
applies the task's reference solution directly; the "with" condition (seen as
--plugin-dir) writes a code-delegate task file, runs the real bridge.sh with
the fake backend, and merges the result — unless the task's expected route is
"direct", where it implements directly like a correctly-routing orchestrator.
Token numbers are synthetic and fixed.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def apply_solution():
    shutil.copytree(os.environ["BENCH_DRYRUN_SOLUTION"], ".", dirs_exist_ok=True)
    git("add", "-A")
    git("commit", "-q", "-m", "fake orchestrator: reference solution")


def emit(input_tokens, output_tokens, cache_read, turns):
    print(json.dumps({
        "type": "result", "is_error": False, "num_turns": turns, "duration_ms": 10,
        "total_cost_usd": 0.0, "result": "done",
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens,
                  "cache_creation_input_tokens": 0, "cache_read_input_tokens": cache_read},
        "modelUsage": {"fake-orchestrator": {
            "inputTokens": input_tokens, "outputTokens": output_tokens,
            "cacheCreationInputTokens": 0, "cacheReadInputTokens": cache_read}},
    }))


def main():
    args = sys.argv[1:]
    if "--max-turns" in args:  # doctor probes
        emit(10, 1, 0, 1)
        return
    with_plugin = "--plugin-dir" in args
    if not with_plugin or os.environ.get("BENCH_DRYRUN_EXPECTED_ROUTE") == "direct":
        apply_solution()
        emit(20000, 6000, 30000, 12)
        return
    slug = "dry-task"
    Path(".local_task_%s.md" % slug).write_text(
        "---\nBranch: bench/dry\nTest: %s -m unittest discover -s tests -t .\nStallTimeout: %s\n---\n\n"
        "Dry-run task.\n" % (sys.executable, os.environ.get("BENCH_DRYRUN_STALL", "600")))
    proc = subprocess.run(["bridge.sh", slug], capture_output=True, text=True)
    sys.stderr.write(proc.stdout + proc.stderr)
    status = json.loads(proc.stdout.strip().splitlines()[-1])
    if status.get("status") != "pass":
        emit(8000, 1500, 12000, 6)
        return
    git("merge", "-q", "--no-edit", status["branch"])
    emit(8000, 1500, 12000, 6)


if __name__ == "__main__":
    main()
