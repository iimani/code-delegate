#!/usr/bin/env python3
"""Run a backend CLI and record its token usage.

Used by backends/*/run.sh only when CODE_DELEGATE_USAGE_LOG is set (the
benchmark sets it; normal delegation never does). The wrapped CLI emits a
machine-readable event stream; this script turns it back into readable log
lines on stdout (so bridge.sh's stall watcher still sees the log grow) and
appends one JSON record with the run's token usage to the usage log.

Usage:
  usage_wrap.py --format claude-stream|opencode-json|none \
                --backend NAME --model MODEL --log FILE -- CMD [ARGS...]

Exits with the wrapped command's exit code. SIGTERM/SIGINT (from the bridge
watcher) are forwarded to the child so a kill still stops the real agent.
"""
from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time


def _num(value):
    return value if isinstance(value, (int, float)) else 0


class ClaudeStream:
    """Parses `claude --print --output-format stream-json --verbose`."""

    def __init__(self):
        self.result = None
        self.tool_calls = 0

    def feed(self, event):
        etype = event.get("type")
        if etype == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") == "text" and block.get("text"):
                    print(block["text"])
                elif block.get("type") == "tool_use":
                    self.tool_calls += 1
                    print("[tool] %s" % block.get("name", "?"))
        elif etype == "result":
            self.result = event
            if event.get("result"):
                print(event["result"])

    def record(self):
        r = self.result or {}
        model_usage = r.get("modelUsage") or {}
        if model_usage:
            # modelUsage covers every model the session used (subagents,
            # background haiku calls), unlike the top-level usage block.
            tokens = {"input_tokens": 0, "output_tokens": 0,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
            for mu in model_usage.values():
                tokens["input_tokens"] += _num(mu.get("inputTokens"))
                tokens["output_tokens"] += _num(mu.get("outputTokens"))
                tokens["cache_creation_input_tokens"] += _num(mu.get("cacheCreationInputTokens"))
                tokens["cache_read_input_tokens"] += _num(mu.get("cacheReadInputTokens"))
        else:
            u = r.get("usage") or {}
            tokens = {k: _num(u.get(k)) for k in (
                "input_tokens", "output_tokens",
                "cache_creation_input_tokens", "cache_read_input_tokens")}
        tokens.update({
            "reasoning_tokens": None,
            "total_cost_usd": r.get("total_cost_usd"),
            "num_turns": r.get("num_turns"),
            "tool_calls": self.tool_calls,
            "parsed": self.result is not None,
        })
        return tokens


class OpencodeJson:
    """Parses `opencode run --format json` (one JSON event per line).

    Token counts live on step_finish events as part.tokens =
    {input, output, reasoning, cache: {read, write}} (verified with opencode
    1.17.7). Any event whose part is a tool invocation counts as a tool call.
    """

    def __init__(self):
        self.tokens = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0,
                       "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
        self.cost = 0.0
        self.steps = 0
        self.tool_calls = 0
        self.seen_tool_parts = set()

    def feed(self, event):
        etype = event.get("type") or ""
        part = event.get("part") or {}
        ptype = part.get("type") or ""
        if etype == "text" and part.get("text"):
            print(part["text"])
        elif etype == "step_finish" or ptype == "step-finish":
            self.steps += 1
            t = part.get("tokens") or {}
            cache = t.get("cache") or {}
            self.tokens["input_tokens"] += _num(t.get("input"))
            self.tokens["output_tokens"] += _num(t.get("output"))
            self.tokens["reasoning_tokens"] += _num(t.get("reasoning"))
            self.tokens["cache_read_input_tokens"] += _num(cache.get("read"))
            self.tokens["cache_creation_input_tokens"] += _num(cache.get("write"))
            self.cost += _num(part.get("cost"))
        if "tool" in etype or ptype == "tool":
            # A tool part can be reported more than once as its state changes;
            # count each part id once.
            pid = part.get("id") or part.get("callID") or id(event)
            if pid not in self.seen_tool_parts:
                self.seen_tool_parts.add(pid)
                self.tool_calls += 1
                print("[tool] %s" % (part.get("tool") or etype))

    def record(self):
        rec = dict(self.tokens)
        rec.update({"total_cost_usd": self.cost, "num_turns": self.steps,
                    "tool_calls": self.tool_calls, "parsed": self.steps > 0})
        return rec


class Passthrough:
    def feed(self, event):
        pass

    def record(self):
        return {"parsed": False}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", required=True, choices=["claude-stream", "opencode-json", "none"])
    ap.add_argument("--backend", required=True)
    ap.add_argument("--model", default="")
    ap.add_argument("--log", required=True)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    cmd = args.cmd[1:] if args.cmd and args.cmd[0] == "--" else args.cmd
    if not cmd:
        ap.error("missing command after --")

    parser = {"claude-stream": ClaudeStream, "opencode-json": OpencodeJson,
              "none": Passthrough}[args.format]()

    start = time.time()
    child = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, bufsize=1)

    def forward(signum, _frame):
        try:
            child.send_signal(signum)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGINT, forward)

    for line in child.stdout:
        stripped = line.strip()
        event = None
        if args.format != "none" and stripped.startswith("{"):
            try:
                event = json.loads(stripped)
            except ValueError:
                event = None
        if event is None:
            sys.stdout.write(line)
        else:
            parser.feed(event)
        sys.stdout.flush()

    code = child.wait()
    rec = {"backend": args.backend, "model": args.model or None,
           "exit_code": code, "duration_ms": int((time.time() - start) * 1000)}
    rec.update(parser.record())
    try:
        with open(args.log, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError as e:
        print("[usage_wrap] could not write usage log %s: %s" % (args.log, e), file=sys.stderr)
    sys.exit(code if code >= 0 else 128 - code)


if __name__ == "__main__":
    main()
