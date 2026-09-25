"""Turn results/<run>/runs.jsonl (+ env.json) into summary.json and summary.md.

Aggregation rules are described in docs/benchmark-methodology.md ("Scoring").
Standard library only.
"""
from __future__ import annotations

import json
import re
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


def merge_runs(sources: List[Path]):
    """Combine several result dirs of the same mode (e.g. a baseline run and a
    --skip-baseline run with more delegate targets) into one data set."""
    runs: List[dict] = []
    env: dict = {}
    for src in sources:
        r, e = _load(src)
        runs += r
        if not env:
            env = json.loads(json.dumps(e))
            env["models"] = list(e.get("models", []))
            env["merged_from"] = []
        else:
            if e.get("mode") != env.get("mode"):
                raise SystemExit("cannot merge %s (mode %s) with mode %s" % (src, e.get("mode"), env.get("mode")))
            env["models"] += [m for m in e.get("models", []) if m not in env["models"]]
            env["reps"] = max(env.get("reps") or 0, e.get("reps") or 0)
            for key in ("model_notes", "excluded_models"):
                env.setdefault(key, {}).update(e.get(key) or {})
            known = {t["slug"] for t in env.get("tasks", [])}
            env.setdefault("tasks", []).extend(t for t in e.get("tasks", []) if t["slug"] not in known)
            for key in ("orchestrator_model", "isolation", "code_delegate_sha"):
                if e.get(key) != env.get(key):
                    env.setdefault("merge_warnings", []).append(
                        "%s differs: %s vs %s (%s)" % (key, env.get(key), e.get(key), src.name))
        env["merged_from"].append(src.name)
    return runs, env


def _raw_label(r: dict) -> str:
    model = r.get("model_under_test")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", model).strip("_") if model else ""
    return r.get("raw_label") or "%s.%s%s.r%d" % (r["task"], r["condition"], "." + safe if safe else "", r["rep"])


def backfill_phases(run_dirs: List[Path], runs: List[dict]) -> None:
    """Older runs (or runs whose transcript wasn't captured) get phases from the
    transcript Claude Code still keeps under ~/.claude/projects, if available."""
    try:
        import phases
    except ImportError:
        return
    home = Path.home() / ".claude"
    for r in runs:
        if r.get("mode") != "compare" or r.get("orchestrator_phases"):
            continue
        for d in run_dirs:
            raw = d / "raw" / _raw_label(r)
            if (raw / "transcript.jsonl").exists():
                r["orchestrator_phases"] = phases.phase_breakdown(raw / "transcript.jsonl")
                break
            if (raw / "orchestrator.json").exists():
                try:
                    sid = json.loads((raw / "orchestrator.json").read_text()).get("session_id")
                except ValueError:
                    sid = None
                t = phases.find_transcript(sid or "", [home])
                if t:
                    r["orchestrator_phases"] = phases.phase_breakdown(t)
                    break


def phase_table(runs: List[dict]) -> Dict[str, object]:
    """Mean orchestrator tokens per run for each phase, over runs with a phase breakdown."""
    breakdowns = [r["orchestrator_phases"] for r in runs if r.get("orchestrator_phases")]
    if not breakdowns:
        return {}
    totals: Dict[str, float] = {}
    for breakdown in breakdowns:
        for phase, v in breakdown.items():
            totals[phase] = totals.get(phase, 0) + v["total"]
    return {"runs": len(breakdowns), "mean_tokens": {k: v / len(breakdowns) for k, v in totals.items()}}


def fit_break_even(points: List[tuple]) -> Optional[dict]:
    """Least-squares fit with ≈ overhead + ratio × without over per-task medians.

    break_even is the baseline size (Claude tokens without delegation) above which
    delegating is expected to use fewer Claude tokens: overhead / (1 − ratio).
    """
    if len(points) < 3:
        return None
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    ratio = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    overhead = my - ratio * mx
    if ratio >= 1:
        verdict, break_even = "never" if overhead >= 0 else "always", None
    elif overhead <= 0:
        verdict, break_even = "always", 0.0
    else:
        verdict, break_even = "above", overhead / (1 - ratio)
    return {"points": len(points), "overhead": overhead, "ratio": ratio, "break_even": break_even,
            "verdict": verdict, "max_baseline_seen": max(xs)}


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
        "orchestrator_tokens_median": _median(o.get("total") for o in orch),
        "delegate_claude_tokens_median": _median(
            ((r.get("claude") or {}).get("delegate") or {}).get("total") for r in scored),
        "delegate_tokens_median": _median(
            ((r.get("delegate_tokens") or {}).get("input") or 0)
            + ((r.get("delegate_tokens") or {}).get("output") or 0) for r in scored),
        "wall_s_median": _median((r.get("wall_ms") or 0) / 1000 for r in scored),
        "turns_median": _median(o.get("turns") for o in orch),
        "cost_usd_median": _median(o.get("cost_usd") for o in orch),
        "delegate_cost_usd_median": _median(
            ((r.get("claude") or {}).get("delegate") or {}).get("cost_usd") for r in scored),
        "delegated": sum(1 for r in scored if r.get("delegated")),
        "bridge_attempts_median": _median(r.get("bridge_attempts") for r in scored),
        "routed_elsewhere": sum(1 for r in scored if r.get("routed_elsewhere")),
        "routes": _count("%s/%s" % (d.get("backend"), d.get("model") or "default")
                         for r in scored for d in (r.get("delegations") or [])),
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
        orch_with = deleg_with = 0.0
        usd_base = usd_with = 0.0
        usd_counted = 0
        for t in tasks:
            w, wo = t["with"].get(m) or {}, t["without"]
            if w.get("claude_tokens_median") is not None and wo.get("claude_tokens_median") is not None:
                base += wo["claude_tokens_median"]
                sum_with += w["claude_tokens_median"]
                orch_with += w.get("orchestrator_tokens_median") or 0
                deleg_with += w.get("delegate_claude_tokens_median") or 0
                counted += 1
                if w.get("cost_usd_median") is not None and wo.get("cost_usd_median") is not None:
                    usd_base += wo["cost_usd_median"]
                    usd_with += w["cost_usd_median"] + (w.get("delegate_cost_usd_median") or 0)
                    usd_counted += 1
            if (w.get("claude_tokens_median_passing") is not None
                    and wo.get("claude_tokens_median_passing") is not None):
                base_ok += wo["claude_tokens_median_passing"]
                with_ok += w["claude_tokens_median_passing"]
                counted_ok += 1
        overall[m] = {
            "tasks_counted": counted, "without_tokens": base, "with_tokens": sum_with,
            "with_orchestrator_tokens": orch_with, "with_delegate_claude_tokens": deleg_with,
            "usd_without": usd_base if usd_counted else None, "usd_with": usd_with if usd_counted else None,
            "delta_pct": (sum_with - base) / base if base else None,
            "tasks_counted_correct": counted_ok, "without_tokens_correct": base_ok,
            "with_tokens_correct": with_ok,
            "correct_delta_pct": (with_ok - base_ok) / base_ok if base_ok else None,
            "pass_rate": _ratio(sum(t["with"][m]["passed"] for t in tasks if m in t["with"]),
                                sum(t["with"][m]["n"] for t in tasks if m in t["with"])),
        }
    base_pass = _ratio(sum(t["without"]["passed"] for t in tasks), sum(t["without"]["n"] for t in tasks))
    for m in models:
        points = [(t["without"]["claude_tokens_median"], t["with"][m]["claude_tokens_median"]) for t in tasks
                  if m in t["with"] and t["without"]["claude_tokens_median"] is not None
                  and t["with"][m]["claude_tokens_median"] is not None]
        overall[m]["break_even"] = fit_break_even(points)
    phase_rows = {"without": phase_table([r for r in runs if r["condition"] == "without"])}
    for m in models:
        phase_rows[m] = phase_table([r for r in runs if r["condition"] == "with" and r.get("model_under_test") == m])
    return {"tasks": tasks, "overall": overall, "without_pass_rate": base_pass, "phases": phase_rows}


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
                    r.get("delegate_io_tokens") if r.get("delegate_io_tokens") is not None else
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
    if env.get("merged_from"):
        lines.append("| Merged from | %s |" % ", ".join("`%s`" % m for m in env["merged_from"]))
    for w in env.get("merge_warnings") or []:
        lines.append("| **Merge warning** | %s |" % w)
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
            "| Delegate target | Tasks | Claude tokens without | with | of which orchestrator / Claude delegate "
            "| Δ | Δ (correct runs only) | Hidden-test pass (with) | USD list without → with |",
            "|---|---|---|---|---|---|---|---|---|"]
    for m in models:
        o = data["overall"].get(m) or {}
        usd = "n/a" if o.get("usd_without") is None else "%s → %s" % (
            _fmt_usd(o["usd_without"]), _fmt_usd(o["usd_with"]))
        out.append("| `%s` | %d | %s | %s | %s / %s | %s | %s (%d tasks) | %s | %s |" % (
            m, o.get("tasks_counted", 0), _fmt_int(o.get("without_tokens")), _fmt_int(o.get("with_tokens")),
            _fmt_int(o.get("with_orchestrator_tokens")), _fmt_int(o.get("with_delegate_claude_tokens")),
            _fmt_pct(o.get("delta_pct")), _fmt_pct(o.get("correct_delta_pct")),
            o.get("tasks_counted_correct", 0),
            "n/a" if o.get("pass_rate") is None else "{:.0%}".format(o["pass_rate"]), usd))
    out += ["", "Targets: `auto` = nothing pinned, the orchestrator routes each task itself (production "
            "behaviour); `claude:<model>` = delegates pinned to that Claude model; anything else = that "
            "opencode model. Claude-delegate tokens are cheaper per token than the orchestrator's when "
            "the delegate is a smaller model, so compare the orchestrator/delegate split and the USD "
            "column, not only the total."]
    out += ["", "## Break-even", "",
            "Per target, a straight-line fit over the per-task medians: *with* ≈ overhead + ratio × *without*. "
            "Break-even is the task size (Claude tokens without delegation) above which delegating is expected "
            "to use fewer Claude tokens. Treat it as an estimate: it extrapolates beyond the largest task measured.", "",
            "| Delegate target | Tasks | Fixed overhead | Ratio | Break-even (baseline tokens) | Largest baseline measured |",
            "|---|---|---|---|---|---|"]
    for m in models:
        be = (data["overall"].get(m) or {}).get("break_even")
        if not be:
            out.append("| `%s` | <3 | n/a | n/a | n/a | n/a |" % m)
            continue
        verdict = {"never": "never (ratio ≥ 1)", "always": "always saves"}.get(be["verdict"], _fmt_int(be["break_even"]))
        out.append("| `%s` | %d | %s | %.2f | %s | %s |" % (m, be["points"], _fmt_int(be["overhead"]), be["ratio"],
                                                           verdict, _fmt_int(be["max_baseline_seen"])))
    phase_rows = data.get("phases") or {}
    if any(phase_rows.values()):
        import phases as _phases
        present = [p for p in _phases.PHASES if any(p in (row or {}).get("mean_tokens", {}) for row in phase_rows.values())]
        out += ["", "## Where the orchestrator's tokens go", "",
                "Mean Claude tokens per run, by phase, from the session transcripts (each API call is charged its "
                "full context plus output). Phases: explore = reading the repo; code = editing it directly; "
                "skill = loading code-delegate; discover = listing backends/models; spec = writing task files; "
                "dispatch = running bridge.sh; review = inspecting delegate output; integrate = merging it; "
                "summary = final answer.", "",
                "| Condition | Runs | " + " | ".join(present) + " |", "|---|---|" + "---|" * len(present)]
        for label, row in phase_rows.items():
            if not row:
                continue
            cells = [_fmt_int(row["mean_tokens"].get(p)) if p in row["mean_tokens"] else "—" for p in present]
            out.append("| %s | %d | %s |" % ("without" if label == "without" else "with `%s`" % label,
                                             row["runs"], " | ".join(cells)))
    out.append("")
    wp = data.get("without_pass_rate")
    out += ["", "Without delegation, hidden-test pass rate: %s. Totals are sums of per-task medians." % (
        "n/a" if wp is None else "{:.0%}".format(wp)), ""]

    out += ["## Per task", ""]
    for t in data["tasks"]:
        wo = t["without"]
        out += ["### %s  (`%s`, expected route: %s)" % (t["task"], t["class"], t["expected_route"]), "",
                "| Condition | Pass | Claude tokens median (min–max) | Δ | Δ correct | Orchestrator | "
                "Claude delegate | Non-cached | Cache read | Output | Non-Claude delegate tokens | Delegated | "
                "Bridge attempts | Wall s | Exit reasons |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
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
            if w.get("routes"):
                txt += " → " + ", ".join("%s×%d" % (k, v) for k, v in sorted(w["routes"].items()))
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
    return "| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
        label, _fmt_rate(s["passed"], s["n"]), rng,
        _fmt_pct(deltas.get("delta_pct")) if deltas else "—",
        _fmt_pct(deltas.get("correct_delta_pct")) if deltas else "—",
        _fmt_int(s["orchestrator_tokens_median"]),
        _fmt_int(s["delegate_claude_tokens_median"]) if deltas else "—",
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
    out += ["", "## Median wall time (s) / delegate input+output tokens", "",
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


def write_report(run_dir: Path, sources: Optional[List[Path]] = None) -> str:
    if sources:
        runs, env = merge_runs(sources)
        run_dir.mkdir(parents=True, exist_ok=True)
        with (run_dir / "runs.jsonl").open("w") as f:
            for r in runs:
                f.write(json.dumps(r) + "\n")
        (run_dir / "env.json").write_text(json.dumps(env, indent=1))
    else:
        runs, env = _load(run_dir)
    mode = env.get("mode") or (runs[0].get("mode") if runs else "compare")
    if mode != "scorecard":
        backfill_phases(list(sources or []) + [run_dir], runs)
    if mode == "scorecard":
        data = build_scorecard(runs, env)
        md = scorecard_markdown(data, env)
    else:
        data = build_compare(runs, env)
        md = compare_markdown(data, env)
    (run_dir / "summary.json").write_text(json.dumps({"env": env, "summary": data}, indent=1))
    (run_dir / "summary.md").write_text(md)
    return md
