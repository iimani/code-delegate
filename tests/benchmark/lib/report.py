"""Turn results/<run>/runs.jsonl (+ env.json) into summary.json and summary.md.

Aggregation rules are described in docs/benchmark-methodology.md ("Scoring").
Standard library only.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Dict, Iterable, List, Optional

LOW_CONFIDENCE_REPS = 3
SUGGEST_PASS_RATE = 2 / 3


def _median(values: Iterable[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if isinstance(v, (int, float))]
    return statistics.median(vals) if vals else None


def _fmt_int(v: Optional[float]) -> str:
    return "n/a" if v is None else "{:,.0f}".format(v)


def _fmt_pct(v: Optional[float]) -> str:
    return "n/a" if v is None else "{:+.0f}%".format(v * 100)


def _fmt_rate(passed: int, n: int) -> str:
    return "%d/%d" % (passed, n) if n else "n/a"


def _load(run_dir: Path):
    runs = []
    runs_file = run_dir / "runs.jsonl"
    if runs_file.exists():
        for line in runs_file.read_text().splitlines():
            if line.strip():
                runs.append(json.loads(line))
    env_file = run_dir / "env.json"
    env = json.loads(env_file.read_text()) if env_file.exists() else {}
    return runs, env


def _passed(r) -> bool:
    return bool((r.get("hidden_tests") or {}).get("ok"))


def cell_stats(runs: List[dict]) -> Dict[str, object]:
    scored = [r for r in runs if r.get("exit_reason") != "skipped"]
    passing = [r for r in scored if _passed(r)]
    orch = [((r.get("claude") or {}).get("orchestrator") or {}) for r in scored]
    reasons: Dict[str, int] = {}
    for r in scored:
        reasons[r.get("exit_reason", "?")] = reasons.get(r.get("exit_reason", "?"), 0) + 1
    tokens = [r.get("claude_total_tokens") for r in scored]
    return {
        "n": len(scored),
        "passed": len(passing),
        "claude_tokens_median": _median(tokens),
        "claude_tokens_min": min((t for t in tokens if t is not None), default=None),
        "claude_tokens_max": max((t for t in tokens if t is not None), default=None),
        "claude_tokens_median_passing": _median(r.get("claude_total_tokens") for r in passing),
        "claude_noncached_median": _median(
            (o.get("input") or 0) + (o.get("output") or 0) + (o.get("cache_create") or 0) for o in orch),
        "cache_read_median": _median(o.get("cache_read") for o in orch),
        "output_median": _median(o.get("output") for o in orch),
        "delegate_claude_tokens_median": _median(
            ((r.get("claude") or {}).get("delegate") or {}).get("total") for r in scored),
        "delegate_tokens_median": _median(
            ((r.get("delegate_tokens") or {}).get("input") or 0)
            + ((r.get("delegate_tokens") or {}).get("output") or 0) for r in scored),
        "wall_s_median": _median((r.get("wall_ms") or 0) / 1000 for r in scored),
        "turns_median": _median(o.get("turns") for o in orch),
        "cost_usd_median": _median(o.get("cost_usd") for o in orch),
        "delegated": sum(1 for r in scored if r.get("delegated")),
        "bridge_attempts_median": _median(r.get("bridge_attempts") for r in scored),
        "routed_elsewhere": sum(1 for r in scored if r.get("routed_elsewhere")),
        "exit_reasons": reasons,
    }


def _delta(with_v, without_v):
    if with_v is None or without_v is None or not without_v:
        return None, None
    return with_v - without_v, (with_v - without_v) / without_v


def build_compare(runs: List[dict], env: dict) -> dict:
    tasks = []
    order = [t["slug"] for t in env.get("tasks", [])] or sorted({r["task"] for r in runs})
    models = env.get("models") or sorted({r["model_under_test"] for r in runs if r.get("model_under_test")})
    for slug in order:
        task_runs = [r for r in runs if r["task"] == slug]
        if not task_runs:
            continue
        meta = task_runs[0]
        without = cell_stats([r for r in task_runs if r["condition"] == "without"])
        per_model = {}
        for m in models:
            w = cell_stats([r for r in task_runs if r["condition"] == "with" and r.get("model_under_test") == m])
            d_all, p_all = _delta(w["claude_tokens_median"], without["claude_tokens_median"])
            d_ok, p_ok = _delta(w["claude_tokens_median_passing"], without["claude_tokens_median_passing"])
            w.update({"delta_tokens": d_all, "delta_pct": p_all,
                      "correct_delta_tokens": d_ok, "correct_delta_pct": p_ok})
            per_model[m] = w
        tasks.append({"task": slug, "class": meta.get("task_class"),
                      "expected_route": meta.get("expected_route"),
                      "without": without, "with": per_model})

    overall = {}
    for m in models:
        base = sum_with = 0.0
        base_ok = with_ok = 0.0
        counted = counted_ok = 0
        for t in tasks:
            w, wo = t["with"].get(m) or {}, t["without"]
            if w.get("claude_tokens_median") is not None and wo.get("claude_tokens_median") is not None:
                base += wo["claude_tokens_median"]
                sum_with += w["claude_tokens_median"]
                counted += 1
            if (w.get("claude_tokens_median_passing") is not None
                    and wo.get("claude_tokens_median_passing") is not None):
                base_ok += wo["claude_tokens_median_passing"]
                with_ok += w["claude_tokens_median_passing"]
                counted_ok += 1
        overall[m] = {
            "tasks_counted": counted, "without_tokens": base, "with_tokens": sum_with,
            "delta_pct": (sum_with - base) / base if base else None,
            "tasks_counted_correct": counted_ok, "without_tokens_correct": base_ok,
            "with_tokens_correct": with_ok,
            "correct_delta_pct": (with_ok - base_ok) / base_ok if base_ok else None,
            "pass_rate": _ratio(sum(t["with"][m]["passed"] for t in tasks if m in t["with"]),
                                sum(t["with"][m]["n"] for t in tasks if m in t["with"])),
        }
    base_pass = _ratio(sum(t["without"]["passed"] for t in tasks), sum(t["without"]["n"] for t in tasks))
    return {"tasks": tasks, "overall": overall, "without_pass_rate": base_pass}


def _ratio(a: int, b: int) -> Optional[float]:
    return a / b if b else None


def build_scorecard(runs: List[dict], env: dict) -> dict:
    models = env.get("models") or sorted({r["model_under_test"] for r in runs})
    classes = []
    for t in env.get("tasks", []):
        if t["class"] not in classes:
            classes.append(t["class"])
    for r in runs:
        if r.get("task_class") not in classes:
            classes.append(r.get("task_class"))
    matrix = {}
    for m in models:
        matrix[m] = {}
        for c in classes:
            cell = [r for r in runs if r["model_under_test"] == m and r.get("task_class") == c]
            passed = sum(1 for r in cell if _passed(r))
            matrix[m][c] = {
                "n": len(cell), "passed": passed,
                "wall_s_median": _median((r.get("wall_ms") or 0) / 1000 for r in cell),
                "delegate_tokens_median": _median(
                    ((r.get("delegate_tokens") or {}).get("input") or 0)
                    + ((r.get("delegate_tokens") or {}).get("output") or 0) for r in cell),
                "no_tool_use": sum(1 for r in cell if r.get("exit_reason") == "no_tool_use"),
                "exit_reasons": _count(r.get("exit_reason") for r in cell),
            }
    suggested = {}
    for c in classes:
        suggested[c] = None
        for m in models:  # models are listed cheapest-first by convention
            cell = matrix[m][c]
            if cell["n"] and cell["passed"] / cell["n"] >= SUGGEST_PASS_RATE:
                suggested[c] = m
                break
    return {"classes": classes, "matrix": matrix, "suggested_routing": suggested}


def _count(values) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


# --------------------------------------------------------------------------- markdown

def _env_md(env: dict) -> List[str]:
    v = env.get("versions") or {}
    lines = [
        "## Environment", "",
        "| | |", "|---|---|",
        "| Date | %s |" % env.get("date", "?"),
        "| OS | %s |" % env.get("os", "?"),
        "| code-delegate | `%s` |" % env.get("code_delegate_sha", "?"),
        "| claude / opencode | %s / %s |" % (v.get("claude") or "n/a", v.get("opencode") or "n/a"),
        "| Python / git | %s / %s |" % (v.get("python") or "?", v.get("git") or "?"),
        "| Orchestrator model | %s |" % env.get("orchestrator_model", "?"),
        "| Isolation | %s |" % env.get("isolation"),
        "| Backend pinned | %s |" % (env.get("backend_pinned") or "no (auto-routing)"),
        "| Delegation directive | `%s` |" % env.get("directive_file", "?"),
        "| Models under test | %s |" % ", ".join("`%s`" % m for m in env.get("models", [])),
        "| Reps per cell | %s |" % env.get("reps"),
    ]
    if env.get("dry_run"):
        lines.append("| **DRY RUN** | fake orchestrator and backend — numbers are synthetic |")
    excluded = env.get("excluded_models") or {}
    for m, note in (env.get("model_notes") or {}).items():
        label = "Excluded" if m in excluded else "Note"
        lines.append("| %s: `%s` | %s |" % (label, m, note))
    return lines + [""]


def compare_markdown(data: dict, env: dict) -> str:
    models = env.get("models", [])
    reps = env.get("reps") or 0
    out = ["# code-delegate benchmark — Claude tokens with vs. without delegation", ""]
    if reps and reps < LOW_CONFIDENCE_REPS:
        out += ["> **Low confidence:** %d rep(s) per cell. LLM runs vary a lot; use `--reps 3` or more "
                "before drawing conclusions." % reps, ""]
    out += ["Claude tokens = input + output + cache writes + cache reads, orchestrator plus any delegate "
            "that ran on Claude. **Correct** columns only use runs whose code passed the hidden tests. "
            "Negative Δ means delegation saved Claude tokens. See docs/benchmark-methodology.md.", ""]

    out += ["## Headline", "",
            "| Model under test | Tasks | Claude tokens without | with | Δ | Δ (correct runs only) | "
            "Hidden-test pass (with) |", "|---|---|---|---|---|---|---|"]
    for m in models:
        o = data["overall"].get(m) or {}
        out.append("| `%s` | %d | %s | %s | %s | %s (%d tasks) | %s |" % (
            m, o.get("tasks_counted", 0), _fmt_int(o.get("without_tokens")), _fmt_int(o.get("with_tokens")),
            _fmt_pct(o.get("delta_pct")), _fmt_pct(o.get("correct_delta_pct")),
            o.get("tasks_counted_correct", 0),
            "n/a" if o.get("pass_rate") is None else "{:.0%}".format(o["pass_rate"])))
    wp = data.get("without_pass_rate")
    out += ["", "Without delegation, hidden-test pass rate: %s. Totals are sums of per-task medians." % (
        "n/a" if wp is None else "{:.0%}".format(wp)), ""]

    out += ["## Per task", ""]
    for t in data["tasks"]:
        wo = t["without"]
        out += ["### %s  (`%s`, expected route: %s)" % (t["task"], t["class"], t["expected_route"]), "",
                "| Condition | Pass | Claude tokens median (min–max) | Δ | Δ correct | Non-cached | "
                "Cache read | Output | Delegate tokens | Delegated | Bridge attempts | Wall s | Exit reasons |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        out.append(_task_row("without", wo, None))
        for m in models:
            if m in t["with"]:
                out.append(_task_row("with `%s`" % m, t["with"][m], t["with"][m]))
        out.append("")

    out += ["## Routing", "", "Did the orchestrator delegate where code-delegate's rules say it should?", "",
            "| Task | Expected | " + " | ".join("`%s`" % m for m in models) + " |",
            "|---|---|" + "---|" * len(models)]
    for t in data["tasks"]:
        cells = []
        for m in models:
            w = t["with"].get(m) or {}
            txt = "%d/%d delegated" % (w.get("delegated", 0), w.get("n", 0))
            if w.get("routed_elsewhere"):
                txt += ", %d routed elsewhere" % w["routed_elsewhere"]
            cells.append(txt)
        out.append("| %s | %s | %s |" % (t["task"], t["expected_route"], " | ".join(cells)))
    out += ["", "## Appendix: orchestrator USD (list price as reported by the CLI)", "",
            "Informational only — enterprise, Bedrock and Vertex pricing differ. Rank on tokens.", "",
            "| Task | without | " + " | ".join("`%s`" % m for m in models) + " |",
            "|---|---|" + "---|" * len(models)]
    for t in data["tasks"]:
        cells = [_fmt_usd(t["with"].get(m, {}).get("cost_usd_median")) for m in models]
        out.append("| %s | %s | %s |" % (t["task"], _fmt_usd(t["without"].get("cost_usd_median")), " | ".join(cells)))
    return "\n".join(out + [""] + _env_md(env))


def _fmt_usd(v):
    return "n/a" if v is None else "$%.4f" % v


def _task_row(label: str, s: dict, deltas: Optional[dict]) -> str:
    rng = "%s (%s–%s)" % (_fmt_int(s["claude_tokens_median"]), _fmt_int(s["claude_tokens_min"]),
                          _fmt_int(s["claude_tokens_max"]))
    reasons = ", ".join("%s×%d" % (k, v) for k, v in sorted(s["exit_reasons"].items()))
    return "| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
        label, _fmt_rate(s["passed"], s["n"]), rng,
        _fmt_pct(deltas.get("delta_pct")) if deltas else "—",
        _fmt_pct(deltas.get("correct_delta_pct")) if deltas else "—",
        _fmt_int(s["claude_noncached_median"]), _fmt_int(s["cache_read_median"]),
        _fmt_int(s["output_median"]),
        _fmt_int(s["delegate_tokens_median"]) if deltas else "—",
        "%d/%d" % (s["delegated"], s["n"]) if deltas else "—",
        _fmt_int(s["bridge_attempts_median"]) if deltas else "—",
        "n/a" if s["wall_s_median"] is None else "%.0f" % s["wall_s_median"], reasons)


def scorecard_markdown(data: dict, env: dict) -> str:
    models = env.get("models", [])
    classes = data["classes"]
    out = ["# code-delegate benchmark — delegate scorecard", "",
           "Each task sent straight to `bridge.sh` (no Claude orchestrator) with the model pinned; "
           "scored by hidden tests. See docs/benchmark-methodology.md.", ""]
    reps = env.get("reps") or 0
    if reps and reps < LOW_CONFIDENCE_REPS:
        out += ["> **Low confidence:** %d rep(s) per cell." % reps, ""]
    out += ["## Hidden-test pass rate by task class", "",
            "| Model | " + " | ".join(classes) + " | no_tool_use |",
            "|---|" + "---|" * (len(classes) + 1)]
    for m in models:
        cells = [_fmt_rate(data["matrix"][m][c]["passed"], data["matrix"][m][c]["n"]) for c in classes]
        ntu = sum(data["matrix"][m][c]["no_tool_use"] for c in classes)
        out.append("| `%s` | %s | %d |" % (m, " | ".join(cells), ntu))
    out += ["", "## Median wall time (s) / delegate tokens", "",
            "| Model | " + " | ".join(classes) + " |", "|---|" + "---|" * len(classes)]
    for m in models:
        cells = []
        for c in classes:
            cell = data["matrix"][m][c]
            cells.append("%s / %s" % ("n/a" if cell["wall_s_median"] is None else "%.0f" % cell["wall_s_median"],
                                      _fmt_int(cell["delegate_tokens_median"])))
        out.append("| `%s` | %s |" % (m, " | ".join(cells)))
    out += ["", "## Suggested routing", "",
            "First model in `BENCH_MODELS` order (list cheapest first) with a pass rate of at least "
            "%.0f%% for the class." % (SUGGEST_PASS_RATE * 100), "",
            "| Class | Suggested model |", "|---|---|"]
    for c in classes:
        s = data["suggested_routing"].get(c)
        out.append("| %s | %s |" % (c, "`%s`" % s if s else "none qualified — keep on Claude"))
    return "\n".join(out + [""] + _env_md(env))


def write_report(run_dir: Path) -> str:
    runs, env = _load(run_dir)
    mode = env.get("mode") or (runs[0].get("mode") if runs else "compare")
    if mode == "scorecard":
        data = build_scorecard(runs, env)
        md = scorecard_markdown(data, env)
    else:
        data = build_compare(runs, env)
        md = compare_markdown(data, env)
    (run_dir / "summary.json").write_text(json.dumps({"env": env, "summary": data}, indent=1))
    (run_dir / "summary.md").write_text(md)
    return md
