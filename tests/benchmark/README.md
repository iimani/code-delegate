# Benchmark: orchestrator cost impact of delegation

Measures whether delegating a task via code-delegate actually reduces the token/dollar
cost of the *orchestrating* Claude session, compared to implementing the same task
directly — the plugin's core value proposition.

## What it does

For each task prompt in `tasks/`, runs two conditions in isolated scratch git repos
seeded from `fixture/`:

- **baseline** — `claude --print` with no code-delegate CLAUDE.md/skill available;
  implements the task directly.
- **with-skill** — same prompt, but with the code-delegate `CLAUDE.md` directive and
  skill installed into an isolated `CLAUDE_CONFIG_DIR`; the orchestrator is expected to
  delegate via `bridge.sh` instead of implementing inline.

Both run with `--output-format json`, which reports `total_cost_usd` and a full token
breakdown (`input_tokens`, `output_tokens`, cache creation/read) per run. Results land in
`results/<timestamp>/` as raw JSON per condition plus `summary.json`/`summary.md`.

## Run it

```bash
./run.sh                              # all tasks in tasks/
./run.sh 01-single-file-boilerplate   # one task by filename stem
BENCHMARK_TIMEOUT=600 ./run.sh        # per-condition timeout in seconds (default 300)
```

Requires the `claude` CLI on `PATH`, authenticated, and **not running as root** — see
Limitations below. Add a new task by dropping a prompt file in `tasks/`.

## Isolation

Each condition gets its own scratch git repo (thrown away after) and its own
`CLAUDE_CONFIG_DIR` — this never touches your real `~/.claude` config, your shell
history, or the code-delegate repo itself. The with-skill condition adds the isolated
config's `skills/code-delegate/bin` to `PATH` so `bridge.sh` resolves as a bare command,
matching how the real plugin framework injects it.

## What this measures — and what it doesn't

The cost/token numbers are **orchestrator-side only**: the main `claude --print` session
in each condition. When the with-skill condition delegates, the actual implementation
work happens in a *separate* nested `claude` CLI process spawned by
`backends/claude/run.sh` inside the isolated worktree. That process's own cost isn't
captured here — `backends/claude/run.sh` runs with `--verbose` (human-readable
transcript), not `--output-format json`, so there's no structured usage to parse without
changing the plugin's actual production behavior, which this harness intentionally
doesn't do.

That means a **positive cost delta on a task that should DELEGATE is still the expected,
interesting result**: it shows the orchestrator spent less tokens on reading, writing,
and editing code itself — the whole point of pushing that work to a delegate — even
though total system cost moved rather than disappeared. Task `03-cross-file-architectural`
is included as a control: code-delegate's own distribution criteria say this should be
IMPLEMENT DIRECTLY, so the with-skill condition is expected to behave like the baseline
(possibly with a little classification overhead), not show savings.

**This harness cannot demonstrate opencode's actual cost savings.** opencode routes to a
local model (LM Studio/Ollama) — zero Anthropic tokens by definition — but that's not
something Anthropic's own usage/cost reporting has any visibility into, and this sandbox
that authored the harness has no local LLM server reachable at all (`opencode`/`codex`
CLIs aren't installed here). If you have opencode configured, this harness will route to
it automatically the same way real usage does (`Backend: auto`) — you'll just need to
look at your own local model server's cost (i.e., $0 vs. whatever the baseline spent),
not this harness's `total_cost_usd` field, to see the number that actually matters for a
homelab/self-hosted setup.

## Limitations found while building this

- **`--dangerously-skip-permissions` refuses to run as root.** Both this harness and
  `backends/claude/run.sh` use it (matching real plugin behavior — this harness is
  meant to measure production behavior, not a testing workaround). If you're running
  this in a root-based container (common for some CI runners and cloud dev
  environments), every condition will fail immediately with a clear
  `--dangerously-skip-permissions cannot be used with root/sudo privileges` message in
  `results/<timestamp>/*.json.log`, and `summary.md` will show `n/a` for that task
  rather than crashing. Run as a non-root user to get real numbers.
- **`--permission-mode acceptEdits --permission-prompts none` is not a safe substitute**,
  despite running fine as root: testing showed it silently denies `git commit` (the
  process still exits `0` and reports success) while auto-approving file edits. Since
  the delegate contract requires the backend to actually commit its changes, this would
  make a benchmark run measure a delegate that silently produces *uncommitted* work —
  worse than a clean failure. Don't "fix" the root issue by switching to this flag
  without also verifying every action a real task needs (installs, test runners, git)
  still goes through.

## Task set

- `01-single-file-boilerplate` — new file, no cross-cutting concerns → should DELEGATE
- `02-bounded-multi-file-types` — two new files, real type reasoning, still bounded →
  should DELEGATE (possibly to a larger model)
- `03-cross-file-architectural` — touches every existing file, changes how modules wire
  together → should IMPLEMENT DIRECTLY (control case, savings not expected)
