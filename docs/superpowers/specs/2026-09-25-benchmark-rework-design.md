# Benchmark rework — design

Date: 2026-09-25
Status: approved in brainstorming, pending spec review
Branch: `feature/benchmark-rework`

## Goal

Answer, with evidence anyone can reproduce on their own machine:

> For the same coding task, how many **Claude tokens** does a Claude Code session spend
> **with** code-delegate (delegating to an opencode model) versus **without** it — and did
> both runs produce correct code?

The headline metric is that token difference. Everything else (correctness, time, delegate
tokens, routing behavior, retries, USD) is recorded for a fuller score.

The harness must be **portable**: runnable unchanged from a home laptop against a LAN Ollama
box, or from a company PC against a sovereign AI platform exposed as an opencode provider.
Nothing in the repo may reference a specific host, provider, or model.

## Non-goals

- Measuring local/sovereign model $ cost (reported as tokens only).
- Supporting non-opencode delegate targets for the sovereign platform (it is an opencode
  provider; no new backend).
- Windows-native shells. Requires bash (macOS, Linux, WSL, Git Bash).

## Current state (what we replace)

`tests/benchmark/run.sh` (from #27) compares orchestrator `total_cost_usd` for a baseline vs.
with-skill `claude --print` run. Gaps:

1. Delegated work routed to the **claude backend** is invisible (nested process, not JSON) —
   the "with" side can under-report Claude tokens.
2. No correctness check — a cheap-but-broken run looks like a win.
3. Uses `timeout`, absent on stock macOS.
4. Explicitly cannot say anything about opencode.
5. USD-centric; misleading on Bedrock/Vertex/enterprise pricing.

## Design

### Layout (`tests/benchmark/`)

```
bench.sh                   # entry point: bench.sh <doctor|compare|scorecard> [opts]
bench.env.example          # documented config keys (committed)
bench.local.env            # per-machine overrides (gitignored)
lib/common.sh              # config loading, portable timeout, scratch repo seeding,
                           # hidden-test runner, result writing
lib/metrics.py             # parse claude JSON / usage log / bridge log → run record
lib/report.py              # results/*.jsonl → summary.json + summary.md
lib/fake-backend/          # deterministic backend for --dry-run (config.yaml + run.sh)
fixture/                   # shared TS project; tests via `node --test`
tasks/<NN-slug>/
  prompt.md                # exactly what the orchestrator/delegate is given
  task.yaml                # class, expected_route, timeout, files_hint
  hidden-tests/*.test.ts   # copied in only AFTER the run finishes
  solution/                # reference solution, used by --dry-run fake backend
results/<run-id>/          # gitignored
```

The old `run.sh` is removed; its logic becomes the `compare` mode.

### Configuration & portability

Precedence: CLI flag > environment variable > `bench.local.env` > built-in default.

| Key | Flag | Default |
|---|---|---|
| `BENCH_MODELS` | `--models a,b` | every model in `opencode models` that passes the doctor ping |
| `BENCH_REPS` | `--reps N` | 3 |
| `BENCH_TASKS` | positional args | all tasks |
| `BENCH_TIMEOUT` | `--timeout S` | per-task `task.yaml` value, else 900 |
| `BENCH_ORCHESTRATOR_MODEL` | `--orchestrator-model` | claude CLI default |
| `BENCH_ALLOW_CLAUDE_DELEGATE` | `--allow-claude-delegate` | off |

No host, provider or model name appears in committed files. Company use = set
`BENCH_MODELS=sovereign/<model>` (or rely on discovery) in `bench.local.env`.

**Portable timeout:** `lib/common.sh` provides `run_with_timeout` using `timeout`, then
`gtimeout`, then a bash background-process + `kill` fallback.

### `bench.sh doctor`

Preflight; exits non-zero with actionable messages. Checks:

- bash (scripts must stay compatible with macOS's bash 3.2: no associative arrays).
- `git`, `python3`, `node` ≥ 22.6 (for `--experimental-strip-types`; no npm install needed).
- `claude` on PATH and authenticated (a 1-turn `claude --print --output-format json` ping
  that reports usage; works with API key, Bedrock, Vertex).
- `opencode` on PATH; each requested model answers a minimal ping within 60s. Unreachable
  models are listed and excluded from the run (not a hard fail unless none remain).
- Not running as root (`--dangerously-skip-permissions` refuses root).

Doctor runs automatically at the start of `compare`/`scorecard`.

### Accounting: `CODE_DELEGATE_USAGE_LOG`

New opt-in env var honored by backend runners. When unset, runners behave exactly as today.
When set to a file path:

- `backends/claude/run.sh` adds `--output-format json`, and appends one JSONL record
  `{backend, model, input_tokens, output_tokens, cache_creation_input_tokens,
  cache_read_input_tokens, total_cost_usd, duration_ms}` to the file. Its human transcript
  still goes to the bridge log.
- `backends/opencode/run.sh` adds `--format json` and parses the JSONL event stream
  (format verified with opencode 1.17.7): sums `part.tokens.{input,output,reasoning,
  cache.read,cache.write}` over all `step_finish` events, and counts tool-call events.
  Appends the same record shape (Claude-specific fields null) plus `tool_calls: N`.
  `text` parts are still written to the log in readable form.
- `backends/codex/run.sh`: records `{backend, model}` with null tokens (out of scope).

`bridge.sh` passes the env var through unchanged; it needs no other change. The harness sets
it per run to a file in the run's results directory.

### Mode: `compare` (primary)

For each task × rep:

1. **without** — seed scratch repo, isolated empty `CLAUDE_CONFIG_DIR`,
   `claude --print --output-format json --dangerously-skip-permissions <prompt>`.
2. **with** — for each model under test: seed scratch repo, isolated `CLAUDE_CONFIG_DIR`
   with code-delegate's `CLAUDE.md` + plugin installed, `bin/` on PATH,
   `OPENCODE_DELEGATE_MODEL=<model>`, `CODE_DELEGATE_USAGE_LOG` set, same claude command.
   **Backend pinning:** unless `--allow-claude-delegate`, the harness sets
   `CODE_DELEGATE_BACKEND=opencode` — a new bridge env var that, when set, overrides
   `Backend: auto`/empty (but not an explicit `Backend:` header; an explicit non-opencode
   header is recorded as `routed_elsewhere`). This guarantees the model under test is the one
   exercised, while still counting any Claude-backend tokens if the orchestrator insists.
3. After each run: commit/merge state is read as-is (the orchestrator is responsible for
   merging delegate work, same as production), hidden tests are copied in and run with
   `node --test`, pass/fail recorded.

**Auth & context isolation.** Every run is a fresh `claude --print` process; it cannot
borrow the calling session's login, and it must not inherit the operator's personal context
(global `CLAUDE.md`, plugins, hooks, MCP servers) or the *without* condition is contaminated
and results aren't comparable across machines. Two isolation modes, chosen by doctor:

1. **`cli-login` (preferred):** the operator's normal CLI login (`claude` → `/login`), with
   `--setting-sources project --strict-mcp-config`. The *with* condition loads code-delegate via
   `--plugin-dir <repo>` plus its `CLAUDE.md` via `--append-system-prompt-file`; the *without*
   condition loads neither.
2. **`isolated-config` (fallback / CI / locked-down PCs):** empty temp `CLAUDE_CONFIG_DIR`;
   requires an env credential: `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token`),
   `ANTHROPIC_API_KEY`, or Bedrock/Vertex env vars. Verified 2026-09-25: an empty config dir
   with no env credential fails with `terminal_reason: api_error`.

Verified 2026-09-25 (claude 2.1.266, 1-turn probe from an empty git repo): default sources →
model reports seeing the global `CLAUDE.md` directive, 37,980 context tokens;
`--setting-sources project` → not seen, 25,725 tokens. So `cli-login` is the default.

Doctor runs a **leak probe** in the *without* configuration: it asks the model whether its
instructions mention code-delegate / delegation directives. If `cli-login` leaks the user's
global `CLAUDE.md`, doctor falls back to `isolated-config`, or aborts with instructions if no
env credential exists. The chosen mode is recorded in the report's environment block.
`BENCH_ISOLATION=cli-login|isolated-config` forces a mode.

### Mode: `scorecard` (secondary)

No orchestrator. For each task × model × rep: seed repo, write a `.local_task_*.md` from
`prompt.md` with `Backend: opencode`, `Model: <model>`, `Test:` = the fixture's
visible test command (`node --test`; hidden tests are not present), run `bridge.sh`, then run hidden
tests. Measures raw model quality through the real bridge (worktree, test gate, feedback
loop). Report adds a *suggested routing* per task class: the first model in `BENCH_MODELS`
order (users list cheapest first) with pass rate ≥ 2/3.

### Run record (one JSONL line per run)

```
run_id, mode, task, task_class, expected_route, rep, condition (without|with|scorecard),
model_under_test, orchestrator_model,
claude: {orchestrator: {input, output, cache_create, cache_read, cost_usd, turns, duration_ms},
         delegate:     {input, output, cache_create, cache_read, cost_usd}},
claude_total_tokens,            # input+output+cache_create+cache_read, orch + delegate
delegate_tokens: {input, output},   # opencode side
delegated: bool, delegations: [{backend, model}], routed_elsewhere: bool,
bridge_attempts, hidden_tests: {passed, failed, ok},
wall_ms, exit_reason (ok|timeout|bridge_error|claude_error|no_tool_use|skipped)
```

`delegated` is derived from the usage log (≥1 record) cross-checked with bridge log presence.

### Report (`summary.md`)

1. **Headline table** per task: median Claude total tokens without vs. with (per model),
   Δ and Δ%, pass rate both sides.
2. **Correct savings**: Δ counted only for rep pairs where the *with* run passed hidden tests;
   runs that saved tokens but failed are shown separately, never as savings.
3. Token breakdown (input/output/cache) — cache reads are shown separately because they are
   priced very differently.
4. Per-model: pass rate, median wall time, delegate tokens, delegation rate, bridge attempts.
5. Expected vs. actual route per task (did the orchestrator delegate the tasks it should,
   and implement the control task directly?).
6. Environment block: date, OS, CLI versions, orchestrator model, models under test, reps,
   git SHA of code-delegate. USD shown in an appendix only.

Medians over reps; min/max shown. N<3 is flagged as low confidence.

### Tasks (6)

All share `fixture/` (a small TS project: `src/` with a few modules using `console.log`,
a bugged `range()` util, an untested `slugify` module, visible tests for some modules).

| # | Slug | Class | Expected route |
|---|---|---|---|
| 01 | single-file-boilerplate (logger) | boilerplate | delegate |
| 02 | bounded-multi-file-types (generic TTL cache + tests) | type-reasoning | delegate (larger model) |
| 03 | cross-file-architectural (DI container) | architectural | implement directly (control) |
| 04 | bugfix-off-by-one (`range()`) | bugfix | delegate |
| 05 | write-tests (`slugify`) | test-generation | delegate |
| 06 | rename-refactor across 2 files | refactor | delegate |

Task 05 scoring is mutation-based: hidden check runs the model's tests against the real
module (must pass) and against a bundled buggy variant (must fail).

TTL test in task 02 must not rely on real sleeps > 50ms (inject a clock or use short TTLs).

### Error handling

- Unreachable model → `skipped`, excluded from aggregates, listed in report.
- Delegate finished with zero tool calls → `no_tool_use`. Observed 2026-09-25:
  `ollama/qwen2.5-coder:14b` emitted its `write` tool call as plain text and opencode ended
  with `reason: stop` — nothing written. Reported per model as "cannot drive opencode tools"
  so it isn't confused with wrong code. Doctor's model ping also asks for one trivial tool
  call and warns on models that fail it.
- Timeout / non-zero exit → recorded with `exit_reason`, counted as fail; run continues.
- Unparseable claude JSON → `claude_error`, raw output kept in `results/<run-id>/raw/`.
- Ctrl-C → partial results still aggregated (trap writes summary).
- Scratch dirs under `mktemp -d`, removed on exit unless `--keep`.

### Harness self-test

`bench.sh compare --dry-run` / `scorecard --dry-run`: uses `lib/fake-backend` (copies
`solution/` into the worktree and commits) and a stub orchestrator (a script standing in for
`claude` that emits fixed JSON and calls `bridge.sh`). Verifies the full pipeline — seeding,
bridge, usage log, hidden tests, report — with no LLM. Added to CI, plus shellcheck on new
scripts.

## Documentation deliverables

1. **`docs/benchmark-methodology.md`** — for people evaluating results:
   research question; conditions and what is held constant (fixture, prompt, hidden tests,
   orchestrator model, isolated config); what "Claude tokens" includes and why tokens not USD;
   backend pinning and its effect; hidden tests and why the model never sees them; mutation
   scoring; reps, medians, confidence caveats; "correct savings" rule; known threats to
   validity (non-determinism, caching effects, orchestrator prompt sensitivity, fixture size
   vs. real codebases, local model quantization); how to reproduce and how to add tasks;
   how to run against a sovereign platform.
2. **`docs/how-delegation-works.md`** — for users/integrators: end-to-end flow from a Claude
   Code request → distribute (classification into DELEGATE / IMPLEMENT DIRECTLY / LARGER
   MODEL) → task file format → `bridge.sh` (backend/model resolution precedence, security
   check, worktree isolation, liveness/stall watcher, test gate, feedback loop, JSON output)
   → backend runner → merge back. Includes a sequence diagram (mermaid), the security tiering
   rule, and where to plug in a new provider (opencode provider config vs. new backend,
   linking to `docs/authoring-backends.md`).
3. `tests/benchmark/README.md` — short quickstart pointing to the methodology doc.
4. README.md: short "Benchmarks" section linking both docs.

## Changes outside `tests/benchmark/`

- `backends/claude/run.sh`, `backends/opencode/run.sh`, `backends/codex/run.sh`:
  `CODE_DELEGATE_USAGE_LOG` support (opt-in, no default behavior change).
- `bin/bridge.sh`: `CODE_DELEGATE_BACKEND` env override for auto/empty backend.
- `.gitignore`: `tests/benchmark/bench.local.env`.
- `.github/workflows/ci.yml`: shellcheck new scripts; dry-run job.
- `CHANGELOG.md` entry.

## Security note

Both new env vars are harness-facing and don't weaken the security tiering: the
`--security-check` path is unchanged, and `CODE_DELEGATE_BACKEND` does not override an
explicit `Backend:` header, so a security-routed task keeps its approved backend.

## Implementation deviations (2026-09-25)

Decided during implementation. `docs/benchmark-methodology.md` is authoritative where it
differs from the text above.

- **Fixture and tasks are stdlib Python (3.9+), not TypeScript.** Node was not installed on the
  reference machine, and python3 is already a hard requirement, so no extra runtime is needed
  (user decision). Tests run with `python3 -m unittest discover -s tests -t .`.
- **The harness is Python** (`lib/bench.py`, `lib/report.py`) behind a thin `bench.sh`, instead
  of `lib/common.sh` + `metrics.py`. This gives portable timeouts with process-group kill and
  native JSON handling.
- **Models are not auto-discovered by default.** `BENCH_MODELS` or `--models` is required
  (`--models all` for everything listed). A run's cost scales with the model count, and
  `opencode models` also lists cloud models.
- **Exit reasons** are `ok`, `test_fail`, `timeout`, `claude_error`, `no_tool_use` and
  `delegate_error`, plus `bridge_error`, `bridge_aborted` and `bridge_no_backend` in the
  scorecard.
- **Delegation directive**: the README snippet plus a non-interactive approval paragraph, in
  `tests/benchmark/directive.md`, appended via `--append-system-prompt-file`.
- **Wrapper location**: `lib/usage_wrap.py` at the repo root. Runners take the wrapped path only
  when `CODE_DELEGATE_USAGE_LOG` is set and otherwise `exec` the CLI exactly as before.

## Addendum: delegate targets and large tier (2026-09-25)

- **Delegate targets**: `claude:<model>` and `auto` (nothing pinned, which scores the full
  production flow) alongside opencode models. `compare --skip-baseline` plus a multi-directory
  `report --out` reuse a baseline.
- **Large tier**: `fixture-large/` (layered `shop` service) and tasks L1–L6. They are selected
  with `--tier`; each task picks its fixture via `task.yaml` `fixture:`.
- **Analysis**: break-even line fit per target, and a per-phase orchestrator token breakdown
  from Claude Code transcripts (copied to `raw/`, backfilled from `~/.claude/projects` for older
  runs).
- **Motivation**: the first Ollama run (small tier) showed +124–127% Claude tokens with
  delegation. Every management step costs roughly one full-context API call (~30k tokens), which
  outweighs the tiny tasks' direct work. The large tier is there to find the break-even point.
