"""Unit tests for the benchmark harness and lib/usage_wrap.py (no LLM calls).

Run: python3 -m unittest discover -s tests/benchmark/lib -p 'test_*.py'
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

LIB = Path(__file__).resolve().parent
sys.path.insert(0, str(LIB))
sys.path.insert(0, str(LIB.parents[2] / "lib"))

import bench  # noqa: E402
import report  # noqa: E402
import usage_wrap  # noqa: E402

# Captured from `opencode run --format json` (opencode 1.17.7, ollama/qwen2.5-coder:14b):
# the model printed its tool call as text instead of calling the tool.
OPENCODE_TEXT_TOOL_CALL = [
    {"type": "step_start", "part": {"type": "step-start"}},
    {"type": "text", "part": {"type": "text", "text": "{\"name\": \"write\"}"}},
    {"type": "step_finish", "part": {"type": "step-finish", "reason": "stop",
                                     "tokens": {"total": 7740, "input": 7660, "output": 75, "reasoning": 0,
                                                "cache": {"write": 0, "read": 5}}, "cost": 0}},
]


class UsageWrapTests(unittest.TestCase):
    def test_opencode_tokens_and_no_tool_calls(self):
        p = usage_wrap.OpencodeJson()
        with redirect_stdout(io.StringIO()):
            for e in OPENCODE_TEXT_TOOL_CALL:
                p.feed(e)
        rec = p.record()
        self.assertEqual((rec["input_tokens"], rec["output_tokens"], rec["cache_read_input_tokens"]), (7660, 75, 5))
        self.assertEqual(rec["tool_calls"], 0)
        self.assertTrue(rec["parsed"])

    def test_opencode_counts_each_tool_part_once(self):
        p = usage_wrap.OpencodeJson()
        with redirect_stdout(io.StringIO()):
            p.feed({"type": "tool_use", "part": {"id": "a", "type": "tool", "tool": "write"}})
            p.feed({"type": "tool_use", "part": {"id": "a", "type": "tool", "tool": "write"}})
            p.feed({"type": "tool_use", "part": {"id": "b", "type": "tool", "tool": "bash"}})
        self.assertEqual(p.record()["tool_calls"], 2)

    def test_claude_stream_sums_model_usage(self):
        p = usage_wrap.ClaudeStream()
        with redirect_stdout(io.StringIO()):
            p.feed({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit"}]}})
            p.feed({"type": "result", "result": "ok", "total_cost_usd": 1.0, "num_turns": 3,
                    "modelUsage": {"a": {"inputTokens": 1, "outputTokens": 2, "cacheReadInputTokens": 3,
                                         "cacheCreationInputTokens": 4},
                                   "b": {"inputTokens": 10, "outputTokens": 20}}})
        rec = p.record()
        self.assertEqual((rec["input_tokens"], rec["output_tokens"]), (11, 22))
        self.assertEqual(rec["tool_calls"], 1)


class HarnessTests(unittest.TestCase):
    def test_parse_unittest(self):
        ok = bench.parse_unittest("....\nRan 4 tests in 0.01s\n\nOK\n", 0)
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["ran"], 4)
        bad = bench.parse_unittest("Ran 5 tests in 0.1s\n\nFAILED (failures=2, errors=1)\n", 1)
        self.assertEqual((bad["ok"], bad["failures"], bad["errors"]), (False, 2, 1))
        crashed = bench.parse_unittest("ImportError: boom\n", 1)
        self.assertFalse(crashed["ok"])

    def test_claude_tokens_prefers_model_usage(self):
        t = bench.claude_tokens({"usage": {"input_tokens": 999},
                                 "modelUsage": {"x": {"inputTokens": 1, "outputTokens": 2,
                                                      "cacheCreationInputTokens": 3,
                                                      "cacheReadInputTokens": 4}}})
        self.assertEqual(t["total"], 10)

    def test_claude_tokens_falls_back_to_usage(self):
        t = bench.claude_tokens({"usage": {"input_tokens": 5, "output_tokens": 1}})
        self.assertEqual(t["total"], 6)

    def test_classify_exit(self):
        no_tools = [{"backend": "opencode", "parsed": True, "tool_calls": 0, "exit_code": 0}]
        self.assertEqual(bench.classify_exit(False, False, False, no_tools), "no_tool_use")
        self.assertEqual(bench.classify_exit(False, False, True, no_tools), "ok")
        self.assertEqual(bench.classify_exit(True, False, False, []), "timeout")
        self.assertEqual(bench.classify_exit(False, True, False, []), "claude_error")
        crashed = [{"backend": "opencode", "parsed": True, "tool_calls": 3, "exit_code": 1}]
        self.assertEqual(bench.classify_exit(False, False, False, crashed), "delegate_error")
        self.assertEqual(bench.classify_exit(False, False, False, []), "test_fail")

    def test_delegate_token_split(self):
        recs = [{"backend": "claude", "input_tokens": 10, "output_tokens": 5},
                {"backend": "opencode", "input_tokens": 100, "output_tokens": 50, "tool_calls": 4}]
        self.assertEqual(bench.delegate_claude_tokens(recs)["total"], 15)
        other = bench.other_delegate_tokens(recs)
        self.assertEqual((other["input"], other["tool_calls"]), (100, 4))

    def test_run_proc_sets_pwd_to_cwd(self):
        # opencode resolves its project dir from $PWD; an inherited PWD made
        # it write into the caller's directory instead of the scratch repo.
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _, _ = bench.run_proc(
                [sys.executable, "-c", "import os; print(os.environ['PWD'])"], cwd=Path(tmp),
                env={"PWD": "/somewhere/else", "PATH": "/usr/bin:/bin"})
            self.assertEqual((code, out.strip()), (0, tmp))

    def test_local_env_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "bench.local.env"
            f.write_text("# comment\nBENCH_MODELS='a/b,c/d'\nexport BENCH_REPS=5\n\nJUNK\n")
            orig = bench.LOCAL_ENV_FILE
            bench.LOCAL_ENV_FILE = f
            try:
                self.assertEqual(bench.load_local_env(), {"BENCH_MODELS": "a/b,c/d", "BENCH_REPS": "5"})
            finally:
                bench.LOCAL_ENV_FILE = orig


def _run(task, condition, model, rep, tokens, ok, delegated=False, reason=None):
    return {"task": task, "task_class": "c", "expected_route": "delegate", "condition": condition,
            "model_under_test": model, "rep": rep, "claude_total_tokens": tokens,
            "claude": {"orchestrator": {"input": tokens, "output": 0, "cache_create": 0, "cache_read": 0},
                       "delegate": {"total": 0}},
            "hidden_tests": {"ok": ok}, "delegated": delegated, "wall_ms": 1000,
            "exit_reason": reason or ("ok" if ok else "test_fail")}


class ReportTests(unittest.TestCase):
    def test_correct_savings_ignore_failing_runs(self):
        env = {"models": ["m"], "tasks": [{"slug": "t", "class": "c", "expected_route": "delegate"}], "reps": 3}
        runs = [_run("t", "without", None, r, 100, True) for r in (1, 2, 3)]
        # with-delegation: two cheap failing runs, one passing run at 80
        runs += [_run("t", "with", "m", 1, 10, False, True), _run("t", "with", "m", 2, 20, False, True),
                 _run("t", "with", "m", 3, 80, True, True)]
        data = report.build_compare(runs, env)
        cell = data["tasks"][0]["with"]["m"]
        self.assertAlmostEqual(cell["delta_pct"], -0.8)          # all runs: median 20 vs 100
        self.assertAlmostEqual(cell["correct_delta_pct"], -0.2)  # passing only: 80 vs 100
        self.assertEqual(cell["passed"], 1)
        md = report.compare_markdown(data, env)
        self.assertIn("-20%", md)

    def test_scorecard_suggests_first_qualifying_model(self):
        env = {"models": ["small", "big"], "tasks": [{"slug": "t", "class": "c", "expected_route": "delegate"}]}
        runs = [dict(_run("t", "scorecard", "small", r, 0, r == 1), mode="scorecard") for r in (1, 2, 3)]
        runs += [dict(_run("t", "scorecard", "big", r, 0, True), mode="scorecard") for r in (1, 2, 3)]
        data = report.build_scorecard(runs, env)
        self.assertEqual(data["suggested_routing"]["c"], "big")

    def test_merge_runs_combines_baseline_and_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, out = Path(tmp, "a"), Path(tmp, "b"), Path(tmp, "out")
            task = {"slug": "t", "class": "c", "expected_route": "delegate"}
            for d, models, runs in ((a, ["m1"], [_run("t", "without", None, 1, 100, True),
                                                  _run("t", "with", "m1", 1, 50, True, True)]),
                                    (b, ["claude:haiku"], [_run("t", "with", "claude:haiku", 1, 70, True, True)])):
                d.mkdir()
                (d / "env.json").write_text(json.dumps({"mode": "compare", "models": models, "reps": 1,
                                                        "tasks": [task]}))
                (d / "runs.jsonl").write_text("\n".join(json.dumps(r) for r in runs) + "\n")
            md = report.write_report(out, sources=[a, b])
            data = json.loads((out / "summary.json").read_text())
            self.assertEqual(data["env"]["models"], ["m1", "claude:haiku"])
            self.assertAlmostEqual(data["summary"]["overall"]["claude:haiku"]["delta_pct"], -0.3)
            self.assertIn("Merged from", md)


class TaskSelectionTests(unittest.TestCase):
    def _slugs(self, tasks=(), tier="small"):
        import argparse
        cfg = bench.Config(argparse.Namespace(tasks=list(tasks), tier=tier))
        return [t.slug for t in bench.load_tasks(cfg)]

    def test_tiers(self):
        small, large, every = self._slugs(), self._slugs(tier="large"), self._slugs(tier="all")
        self.assertTrue(small and large)
        self.assertTrue(all(not s.startswith("L") for s in small))
        self.assertTrue(all(s.startswith("L") for s in large))
        self.assertEqual(sorted(every), sorted(small + large))

    def test_named_tasks_override_tier(self):
        self.assertEqual(self._slugs(["01", "L1"]), ["01-single-file-boilerplate", "L1-crud-resource"])
        with self.assertRaises(SystemExit):
            self._slugs(["nope"])


class BreakEvenTests(unittest.TestCase):
    def test_fit(self):
        # with = 100k + 0.5 * without  ->  break-even at 200k
        pts = [(x, 100_000 + 0.5 * x) for x in (50_000, 100_000, 400_000)]
        be = report.fit_break_even(pts)
        self.assertAlmostEqual(be["overhead"], 100_000, places=3)
        self.assertAlmostEqual(be["ratio"], 0.5, places=6)
        self.assertAlmostEqual(be["break_even"], 200_000, places=3)
        self.assertEqual(be["verdict"], "above")

    def test_never_and_too_few(self):
        self.assertEqual(report.fit_break_even([(1, 10), (2, 12), (3, 14)])["verdict"], "never")
        self.assertIsNone(report.fit_break_even([(1, 2), (2, 3)]))


class PhaseTests(unittest.TestCase):
    def test_classify(self):
        import phases
        c = phases.classify_tool
        self.assertEqual(c("Skill", {"skill": "code-delegate:delegate"}), "skill")
        self.assertEqual(c("Bash", {"command": "bridge.sh --models"}), "discover")
        self.assertEqual(c("Bash", {"command": "bridge.sh feat-x"}), "dispatch")
        self.assertEqual(c("Bash", {"command": "cat > .local_task_x.md <<'EOF'"}), "spec")
        self.assertEqual(c("Write", {"file_path": "/r/.local_task_x.md"}), "spec")
        self.assertEqual(c("Edit", {"file_path": "/r/app/x.py"}), "code")
        self.assertEqual(c("Bash", {"command": "git merge feat/x && python3 -m unittest"}), "integrate")
        self.assertEqual(c("Bash", {"command": "python3 -m unittest discover"}), "test")
        self.assertEqual(c("Bash", {"command": "cd .git/worktrees_agents/x && git status"}), "review")
        self.assertEqual(c("Bash", {"command": "cat app/x.py"}), "explore")

    def test_breakdown_dedupes_message_ids(self):
        import phases
        lines = [
            {"type": "assistant", "message": {"id": "m1", "usage": {"input_tokens": 10, "cache_read_input_tokens": 90,
             "output_tokens": 5}, "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}},
            {"type": "assistant", "message": {"id": "m1", "usage": {"input_tokens": 10, "cache_read_input_tokens": 90,
             "output_tokens": 7}, "content": [{"type": "tool_use", "name": "Skill", "input": {}}]}},
            {"type": "user", "message": {}},
            {"type": "assistant", "message": {"id": "m2", "usage": {"input_tokens": 1, "output_tokens": 1},
             "content": [{"type": "text", "text": "done"}]}},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "t.jsonl"
            f.write_text("\n".join(json.dumps(l) for l in lines))
            b = phases.phase_breakdown(f)
        self.assertEqual(b["skill"], {"calls": 1, "context": 100, "output": 7, "total": 107})
        self.assertEqual(b["summary"]["total"], 2)


class TargetTests(unittest.TestCase):
    def test_parse_target(self):
        self.assertEqual(bench.parse_target("auto"), (None, None))
        self.assertEqual(bench.parse_target("claude:haiku"), ("claude", "haiku"))
        self.assertEqual(bench.parse_target("codex:gpt-x"), ("codex", "gpt-x"))
        self.assertEqual(bench.parse_target("ollama/qwen3.6:27b"), ("opencode", "ollama/qwen3.6:27b"))
        self.assertEqual(bench.parse_target("lmstudio/qwen/qwen3.6-27b"), ("opencode", "lmstudio/qwen/qwen3.6-27b"))


if __name__ == "__main__":
    unittest.main()
