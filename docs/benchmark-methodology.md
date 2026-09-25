# Benchmark methodology

This document is for anyone running the code-delegate benchmark or judging its results. It covers
what is measured, under which conditions, how runs are scored and aggregated, and where the numbers
can mislead. The harness is in [`tests/benchmark/`](../tests/benchmark/). How delegation itself
works is covered in [how-delegation-works.md](how-delegation-works.md).

## The question

> For the same coding task, how many **Claude tokens** does a Claude Code session spend **with**
> code-delegate (delegating to an opencode model) compared with **without** it, and did both runs
> produce correct code?

The **headline metric** is the difference in Claude tokens, counted only over runs whose code
passed hidden tests. Everything else (pass rates, wall time, delegate-side tokens, routing
behaviour, retries, USD) is recorded to make the picture complete, but no ranking is based on it.

The harness is **portable**. Nothing in the repository names a host, provider or model. The
models under test are whatever `opencode models` lists on the machine running it: a home Ollama
box, LM Studio, or a company's self-hosted platform configured as an opencode provider.

## Two modes

| Mode | Command | Answers |
|---|---|---|
| **compare** (primary) | `bench.sh compare` | Claude tokens with vs. without delegation, per task and per delegate model |
| **scorecard** (secondary) | `bench.sh scorecard` | How good each delegate model is on each task class on its own, through the real bridge, with no Claude orchestrator |

## Compare mode: conditions

For every task and repetition the harness runs:

- **without**: one Claude Code session that implements the task itself.
- **with**: one Claude Code session per **delegate target**, with code-delegate loaded.

### Delegate targets

`BENCH_MODELS` / `--models` takes a comma-separated list of targets:

| Target | Example | What the *with* run does |
|---|---|---|
| opencode model | `ollama/qwen3.6:27b`, `ollama/*`, `all` | delegates pinned to that opencode model |
| Claude model | `claude:haiku`, `claude:sonnet` | delegates pinned to the claude backend with that model |
| `auto` | `auto` | **nothing pinned**: the orchestrator classifies each task and picks backend and model itself, exactly as in production. This scores the complete delegation flow |

Pinned targets measure what a given delegate is worth. `auto` measures what a user actually gets,
including the orchestrator's routing decisions. The routing table shows where `auto` sent each
task.

Each run is a fresh `claude --print --output-format json --dangerously-skip-permissions` process in
a fresh scratch git repository seeded from `tests/benchmark/fixture/`. Runs execute **one at a
time**, so local model servers aren't shared between runs and wall times stay comparable.

### What is held constant

| Factor | How |
|---|---|
| Codebase | Identical fixture copy and seed commit for every run |
| Task text | Same `prompt.md`, prefixed by the same [`preamble.md`](../tests/benchmark/preamble.md) in both conditions |
| Orchestrator model | CLI default, or `BENCH_ORCHESTRATOR_MODEL`. Recorded per run, including every model the session actually used (`modelUsage`) |
| Personal context | Excluded in both conditions (see Isolation) |
| Correctness check | Same hidden tests, added after the run |
| Tool permissions | Unattended in both (`--dangerously-skip-permissions`) |
| MCP servers | None (`--strict-mcp-config`) |

### What differs

Only the *with* condition gets:

- the code-delegate plugin (`--plugin-dir <this checkout>`) with `bin/` on `PATH`;
- the delegation directive [`directive.md`](../tests/benchmark/directive.md), appended to the
  system prompt. It is the snippet the README tells users to add to their `CLAUDE.md`, plus one
  paragraph for non-interactive use (see below). `BENCH_DIRECTIVE_FILE` swaps it for your own;
- for pinned targets, `CODE_DELEGATE_BACKEND=<backend>` and `<BACKEND>_DELEGATE_MODEL=<model>`
  (backend pinning); nothing for `auto`;
- `CLAUDE_DELEGATE_SETTING_SOURCES=project`, so a delegate that runs on the claude backend gets
  the same isolation from personal settings as the orchestrator;
- `CODE_DELEGATE_USAGE_LOG=<file>` (delegate token accounting).

### Non-interactive approval

In normal use the orchestrator shows a distribution summary and waits for the user. A benchmark
run has no user, so the directive tells the orchestrator to treat its own summary as approved and
to merge a delegated branch after reviewing it. The preamble, which both conditions get, says
nobody will answer questions and that the finished code must be committed on the checked-out
branch. This is the one deliberate departure from interactive use. It removes the human approval
turn, which in real use adds one extra orchestrator turn.

### Isolation from the operator's setup

A personal `~/.claude` (global `CLAUDE.md`, plugins, hooks, MCP servers) would contaminate the
baseline and make results differ between machines. The author's machine had a global `CLAUDE.md`
that says "always delegate", and it added about 12k tokens of context to every turn. Two isolation modes exist;
`doctor` picks one and the report records which:

1. **cli-login** (default): uses the normal CLI login (`claude` → `/login`) with
   `--setting-sources project`, which loads no user-level settings, `CLAUDE.md` or plugins. This
   was verified with claude 2.1.266: the probe context fell from 37,980 to 25,725 tokens and the
   model no longer saw the global directive.
2. **isolated-config**: an empty `CLAUDE_CONFIG_DIR` per run. It needs a credential in the
   environment (`ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`, or
   Bedrock/Vertex variables). Use this on CI or locked-down machines.

Before every run set, `doctor` runs two one-turn **probes**:

- a **leak probe** in the *without* configuration, which asks whether any delegation instructions
  are visible and must be answered NO;
- a **plugin probe** in the *with* configuration, which asks whether `code-delegate:delegate` is
  available and must be answered YES.

If the leak probe fails in cli-login mode, `doctor` falls back to isolated-config or refuses to run.

`doctor` also pings each model and asks it to create a file with a tool call. In `compare`, models
that fail the tool probe are **excluded** (each would cost a full Claude session per task only to
produce `no_tool_use`) and listed in the report; `--include-no-tools` keeps them. `scorecard`
keeps them, because it spends no Claude tokens.

### Backend pinning

Left to itself, the orchestrator could send a task somewhere other than the target under test,
either by writing an explicit `Backend:` header or because auto-routing prefers claude for tasks
touching more than 3 files. The run would then silently measure a different setup. For pinned
targets the harness therefore sets `CODE_DELEGATE_BACKEND` and the backend's model variable, which
apply whenever a task file leaves `Backend:` empty or `auto` (and `Model:` empty).

An explicit `Backend:` header written by the orchestrator still wins. Such a run is flagged
`routed_elsewhere`, and its Claude-side delegate tokens are **still counted** (see below).
The `auto` target turns pinning off to measure unconstrained production routing.

## What "Claude tokens" includes

```
claude_total_tokens = orchestrator tokens + tokens of every delegate that ran on the claude backend
tokens              = input + output + cache writes + cache reads
```

- **Orchestrator** tokens come from the `--output-format json` result. They are summed over
  `modelUsage`, which covers every model the session used, including subagents and background
  calls. The top-level `usage` block is only a fallback.
- **Delegate** tokens come from `CODE_DELEGATE_USAGE_LOG`. When it is set, each backend runner
  streams its CLI's JSON events through `lib/usage_wrap.py`, which appends one record per delegate
  run:
  - claude runs `--output-format stream-json`, and its final `result` event is summed the same
    way as the orchestrator's;
  - opencode runs `--format json`, and the `part.tokens` of every `step_finish` event are summed.
    These opencode tokens are reported separately and **never** counted as Claude tokens.

  Without the variable the runners behave exactly as in production.
- **Cache reads** are included in the total, because they fill the context window and are billed.
  Their price is much lower, though, so the report also shows them in their own column next to a
  **non-cached** column (input + output + cache writes). A delegation that mostly shifts cache
  reads is visible there.

### Claude delegates: mixed prices

When the delegate is itself a Claude model, the total mixes tokens of different prices: a Haiku
token costs a fraction of an Opus orchestrator token. The headline therefore splits the *with*
total into **orchestrator** and **Claude delegate** tokens and adds list-price USD next to it. For
Claude targets, judge on that split and on USD; for opencode targets the delegate side is zero and
the total is the whole story.

### Why tokens, not dollars

USD from the CLI is list price. Enterprise agreements and Bedrock, Vertex or gateway pricing
differ, and some setups report no cost at all. Tokens are what the orchestrator actually consumes
and are comparable across accounts. USD appears only in an appendix.

## Correctness: hidden tests

Saving tokens by producing broken code is not a saving, so every run is scored by tests the model
**never saw**. After the session ends:

1. each task's `hidden/test_hidden_*.py` is copied into `tests/`, and the whole `hidden/` folder
   into `tests/_hidden/` for assets such as mutants;
2. the **full suite** (`python3 -m unittest discover -s tests -t .`) runs, which covers the
   fixture's visible tests, any tests the model wrote, and the hidden tests;
3. the run **passes** only if the suite exits 0.

The code scored is the **working tree of the checked-out branch**, committed or not. Work left
only on a delegate branch or worktree counts as not done, because the preamble requires it to be
on the current branch.

Hidden tests check only behaviour the prompt specifies. Each prompt states the exact names,
signatures, edge cases and errors that are tested, so a correct solution cannot fail on an
unstated detail.

**Mutation scoring (task 05).** When the task is *writing tests*, the hidden check runs the
model's test file against the real module, where it must pass, and against five deliberately
broken copies, of which it must fail on at least four. It also checks that `app/text.py` was not
modified.

**Task self-validation.** `bench.sh selftest` (run in CI) checks that each task's hidden tests
**fail** on the untouched fixture and **pass** on its reference `solution/`. A task that fails
either check is broken.

## Task set

Tasks come in two tiers, selected with `--tier small|large|all` (default `small`) or by naming
tasks. Both fixtures are stdlib-only Python (3.9+), so nothing beyond `python3` needs to be
installed.

### Small tier

`fixture/` is a tiny project (a few modules, under 100 lines). Tasks finish in a handful of
orchestrator turns, so this tier mostly measures delegation's **fixed overhead**.

| # | Task | Class | Expected route | Hidden tests check |
|---|---|---|---|---|
| 01 | JSON logger (new file) | boilerplate | delegate | one JSON line per call, keys, UTC ISO timestamp, level validation |
| 02 | Generic TTL cache + its tests | type-reasoning | delegate (larger model) | `Generic[V]`, injected clock, TTL boundary, overwrite, delete, `len`/`in`, falsy values, the model's own test file |
| 03 | DI container across all modules | architectural | **implement directly** (control) | one shared logger, no `print` outside `ConsoleLogger`, exact messages, `Protocol` |
| 04 | Off-by-one bug fix | bugfix | delegate | exhaustive chunk coverage, edge cases, errors kept |
| 05 | Test suite for `slugify` | test-generation | delegate | mutation score ≥ 4/5, implementation untouched |
| 06 | Rename across 3 files | refactor | delegate | new name works, old name gone everywhere, behaviour unchanged |

### Large tier

`fixture-large/` is a layered order/inventory service (`shop`: util → models → sqlite3
repositories → services → framework-free API handlers → reports → CLI; about 1,300 lines plus 370
lines of visible tests). Services use a `(value, error)` tuple convention. Each task takes roughly
10× the work of a small one: reading many files, writing hundreds of lines, or a debugging loop.
This tier measures where delegation starts to **save** tokens.

| # | Task | Class | Expected route | Hidden tests check |
|---|---|---|---|---|
| L1 | Suppliers resource across all layers (model, table, repository, service, API, CLI, tests) | boilerplate | delegate | service rules, API statuses and JSON, CLI output, no clash with customers |
| L2 | Test suites for `money`, `dates`, `pricing` | test-generation | delegate | mutation score ≥ 14/17 across the three modules, modules untouched |
| L3 | Migrate `(value, error)` tuples to exceptions everywhere (~15 files) | refactor | delegate (larger model) | exception hierarchy, tuple API removed, no tuple unpacking of service results left, API/CLI behaviour unchanged, rollback kept |
| L4 | CSV/JSON export for every report via CLI and API | feature | delegate | exact CSV/JSON output, formats, endpoint statuses, CLI flag |
| L5 | Bug report with only a symptom ("sales report misses the last day") | bugfix | **implement directly** | root cause fixed in the repository layer, boundaries at 00:00:00 and 23:59:59 |
| L6 | Three independent features in one request (search, email normalization, cancellation) | multi-feature | delegate (split) | each feature, including stock release on cancel |

L5 is the large-tier control: the work is investigation, and the fix is one line.

Task 03 is a **control**. code-delegate's rules say not to delegate it, so the *with* condition
should look like the baseline plus a little classification overhead. A large saving there, or
frequent delegation, points to a routing problem rather than a win.

## Break-even estimate

The small tier alone shows overhead; the large tier shows the other end. Across all tasks in a
run, the report fits a straight line through the per-task medians for each target:

```
Claude tokens with ≈ overhead + ratio × Claude tokens without
```

- **overhead**: the fixed Claude cost of delegating a task at all (skill, planning, dispatch,
  review, merge);
- **ratio**: the share of the direct work that still lands on Claude;
- **break-even** = overhead / (1 − ratio): the task size, in baseline Claude tokens, above which
  delegating is expected to use fewer Claude tokens. Reported as "never" when ratio ≥ 1.

It is a coarse, extrapolated estimate: at least 3 tasks are needed, and it is only trustworthy
within the range of baseline sizes actually measured (shown next to it).

## Where the orchestrator's tokens go

Each orchestrator session's Claude Code transcript is copied to `raw/<run>/transcript.jsonl`.
Every API call in it is assigned one phase from the tools it used: explore, code, test, skill,
discover (`bridge.sh --models` etc.), spec (task files), dispatch (`bridge.sh <slug>`), review
(inspecting worktrees), integrate (merging delegate work), subagent, summary. Each call is
charged its full context plus output. The report shows the mean tokens per phase for each
condition, which shows which parts of the delegation flow cost the most. For runs recorded
before transcripts were captured, `report` reads them from `~/.claude/projects` if they are still
there.

## What each run records

One JSON line per run in `results/<run>/runs.jsonl`, with raw artifacts (orchestrator JSON,
stderr, bridge logs, usage log, diff, hidden-test output, prompt, command) in
`results/<run>/raw/<run-label>/`.

| Field | Meaning |
|---|---|
| `claude.orchestrator` | input, output, cache_create, cache_read, total, cost_usd, turns, duration_ms, models |
| `orchestrator_phases` | per phase: calls, context, output, total tokens (from the transcript) |
| `claude.delegate` | the same totals for delegates that ran on the claude backend |
| `claude_total_tokens` | headline number for this run |
| `delegate_tokens` | non-Claude delegate tokens: input, output, reasoning, cache, tool_calls |
| `delegated`, `delegations`, `routed_elsewhere` | whether and where work was delegated |
| `bridge_attempts` | number of backend starts (first try plus feedback rounds) |
| `hidden_tests` | ok, ran, failures, errors |
| `working_tree_dirty`, `branches` | git state left behind |
| `wall_ms` | session wall time, including delegates |
| `exit_reason` | see below |

### Exit reasons

| Reason | Meaning |
|---|---|
| `ok` | Hidden-test suite passed |
| `test_fail` | Session finished, suite failed |
| `timeout` | Killed at the task's timeout (the process group is killed, delegates included) |
| `claude_error` | Orchestrator returned an error or unparseable output |
| `no_tool_use` | The delegate ended without making a single tool call. Typical of models whose tool-call template doesn't match the endpoint: `ollama/qwen2.5-coder:14b` was observed printing a `write` call as plain text. It means "can't drive opencode", not "wrote wrong code". |
| `delegate_error` | A delegate process exited non-zero |
| `bridge_error` / `bridge_aborted` / `bridge_no_backend` | Scorecard only: the bridge's own verdict |

## Scoring and aggregation

- **Per cell** (task × condition × model), over reps: pass count, median Claude tokens with
  min–max, median of the non-cached / cache-read / output columns, median delegate tokens,
  delegation count, median bridge attempts, median wall time, and counts of each exit reason.
- **Δ** = (median *with* − median *without*) / median *without*. Negative means delegation saved
  Claude tokens.
- **Δ correct** uses the same formula, but each median is taken **only over runs that passed**.
  This is the number to quote. If one side has no passing run, it is `n/a`.
- **Headline per model**: the sums of per-task medians (without vs. with), for all runs and for
  correct runs only, with the number of tasks that contributed. Summing medians gives each task
  equal weight regardless of its size.
- **Routing table**: how often each model's *with* runs delegated, compared with the task's
  expected route.
- **Confidence**: medians over fewer than 3 reps are flagged as low confidence. LLM sessions vary
  a lot in turn count, so use 3–5 reps before drawing conclusions.

### Scorecard aggregation

Pass rate per model × task class, with median wall time and delegate tokens.
**Suggested routing** per class is the first model in `BENCH_MODELS` order with a pass rate of at
least 2/3. List models cheapest first, so the suggestion is the cheapest one that is good enough.
The scorecard writes a task file with `Backend: opencode`, `Model: <model>` and the fixture's
visible test command as `Test:`, runs `bridge.sh` directly, and scores the delegate's worktree.
It also records whether the delegate committed its work.

## Threats to validity

- **Non-determinism.** The same prompt can take 5 turns or 25. Medians and reps help but don't
  remove it; compare runs made with the same orchestrator model and CLI version.
- **Prompt caching.** Consecutive runs can hit a warm cache, which lowers input and raises cache
  reads. The totals include both; the separate columns show how the mix changes.
- **Directive sensitivity.** Results depend on the delegation directive and skill wording. The
  directive file is recorded in the report, and changing it should be treated as a new experiment.
- **Fixture scale.** Even the large fixture is small next to a real product codebase. Reading
  costs grow with codebase size, so real break-even points may be lower than measured here.
- **Delegate model and serving.** Quantization, context length, server load and the endpoint's
  tool-calling support all change delegate quality. Record them alongside the results.
- **Non-interactive departure.** Auto-approval removes a human turn that real sessions have.
- **Wall time** includes the bridge's 10-second watcher polling interval and model load time.
- **Self-reported probes.** The leak and plugin probes rely on the model's own yes/no answer. They
  catch gross misconfiguration, not subtle leaks; the recorded context-token count is a second
  signal.

## Reusing a baseline

The *without* runs don't depend on the delegate target, so a later run with more targets can reuse
an earlier baseline:

```bash
./bench.sh compare --skip-baseline --models claude:haiku,claude:sonnet,auto
./bench.sh report results/<baseline-run> results/<new-run> --out results/combined
```

`report` merges the runs and warns in the environment block if the orchestrator model, isolation
mode or code-delegate version differ between them. Only merge runs made under the same conditions.

## Running it

```bash
cd tests/benchmark
cp bench.env.example bench.local.env     # set BENCH_MODELS etc. for this machine
./bench.sh doctor                         # tools, auth, isolation, model reachability
./bench.sh compare --reps 3               # headline experiment
./bench.sh scorecard --reps 3             # model quality matrix
./bench.sh report results/<run>           # re-render a summary
./bench.sh selftest                       # validate tasks (no LLM)
./bench.sh compare --dry-run --reps 1     # full pipeline with fakes (no LLM)
```

Requirements: bash, git, python3 ≥ 3.9, a logged-in `claude` CLI (or env credentials), `opencode`
with at least one model, and a non-root user. Cost: each compare cell is a full Claude Code session,
so `6 tasks × reps × (1 + models)` sessions. Start with `--reps 1` and one or two tasks.

### On a company machine against a self-hosted platform

1. Add the platform to opencode as a provider (see
   [how-delegation-works.md](how-delegation-works.md#plugging-in-a-model-provider)).
2. Check `opencode models` lists it and `./bench.sh doctor --models <provider>/<model>` passes.
   The tool probe matters: a model that can't make tool calls through the gateway will only
   produce `no_tool_use`.
3. Set `BENCH_MODELS` in `bench.local.env`, cheapest first, or use a pattern such as
   `sovereign/*` to test every model of a provider. Pin `BENCH_ORCHESTRATOR_MODEL` if you
   will compare against runs from another machine.
4. If policy prevents `claude /login`, use `BENCH_ISOLATION=isolated-config` with Bedrock, Vertex
   or API-key variables.

## Adding a task

Create `tests/benchmark/tasks/<NN-slug>/` (large tasks use an `L` prefix) with:

- `prompt.md`: exactly what the model is told. Specify every behaviour the hidden tests check.
- `task.yaml`: flat `key: value` with `title`, `class`, `expected_route`
  (`delegate` | `delegate-larger` | `direct`), `timeout` (seconds), and optionally `tier`
  (`small` default, or `large`) and `fixture` (`small` default, or `large`).
- `hidden/test_hidden_*.py`: `unittest` tests. Extra assets in `hidden/` are available at
  `tests/_hidden/` when the tests run.
- `solution/`: a reference solution overlaid on the fixture. It is used by `selftest` and by the
  dry-run fakes.

Then run `./bench.sh selftest`. Tasks can build on the shared fixture or add files it needs through
the prompt. Keep tasks stdlib-only so the benchmark stays portable.
