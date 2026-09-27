# Code Delegate — Parallel AI Coding Agents for Claude Code

A cross-platform plugin that delegates token-heavy implementation tasks to local or cloud AI agents. Works with **Claude Code**, **Codex CLI**, and **OpenCode CLI**. Each task runs in an isolated Git worktree, enabling parallel dispatch of multiple subagents across different backends.

## Requirements

- `git` and `bash` (macOS, Linux, WSL or Git Bash)
- `python3` 3.9+ (standard library only), used by the bundled MCP server and the hooks
- At least one delegate backend: [OpenCode](https://opencode.ai) for local or self-hosted models, the `claude` CLI, or the Codex CLI

## Installation

### Claude Code (recommended)

```bash
claude plugin marketplace add iimani/code-delegate
claude plugin install code-delegate@code-delegate
```

This installs the skills (`/code-delegate:*`), puts `bridge.sh` on the PATH of your Claude Code sessions, and
starts the bundled MCP server that provides the `delegate` and `delegate_wait` tools. Nothing needs to be added
to your `CLAUDE.md`.

To update later:

```bash
claude plugin marketplace update code-delegate
claude plugin update code-delegate@code-delegate
```

### Claude Code from a local checkout (development)

```bash
git clone https://github.com/iimani/code-delegate.git
claude --plugin-dir ./code-delegate          # load it for one session
# or install it from the checkout, like the published plugin:
claude plugin marketplace add ./code-delegate && claude plugin install code-delegate@code-delegate
```

### Codex CLI and OpenCode CLI

These use the skills only; the `delegate` MCP tool is wired up for Claude Code.

```bash
git clone https://github.com/iimani/code-delegate.git
cd code-delegate
# Codex discovers skills in ~/.agents/skills, OpenCode in ~/.claude/skills: link each skill there
for dir in ~/.agents/skills ~/.claude/skills; do
  mkdir -p "$dir"
  for skill in skills/*/; do ln -sfn "$(pwd)/$skill" "$dir/$(basename "$skill")"; done
done
# The skills call bridge.sh: put it on your PATH (add this to your shell profile)
export PATH="$(pwd)/bin:$PATH"
```

`AGENTS.md` at the repo root provides the Codex/OpenCode tool mappings.

### Set up a delegate backend

**OpenCode (local or self-hosted models, no Claude tokens):**

```bash
curl -fsSL https://opencode.ai/install | bash
```

Configure a provider in `~/.config/opencode/opencode.json`: LM Studio, Ollama, or any OpenAI-compatible
endpoint, such as a company's self-hosted AI platform. `opencode models` should then list your models; the
model must support tool calling. See [how delegation works](docs/how-delegation-works.md#plugging-in-a-model-provider)
for an example provider block.

Then choose your defaults once, on your machine (these are never committed):

```bash
export CODE_DELEGATE_BACKEND=opencode                 # backend for tasks that don't name one
export OPENCODE_DELEGATE_MODEL="ollama/qwen3-coder:30b"  # model for that backend (any name from `opencode models`)
```

- `CODE_DELEGATE_BACKEND` applies whenever a task leaves `Backend:` empty or `auto`; an explicit `Backend:` always wins.
- `<BACKEND>_DELEGATE_MODEL` works for every backend (`CLAUDE_DELEGATE_MODEL`, `CODEX_DELEGATE_MODEL`).
  Precedence, highest first: `Model:` in the task → `<BACKEND>_DELEGATE_MODEL` → `default_model` in the
  backend's `config.yaml` → the CLI's own default. The opencode backend ships with no default model, so without
  either setting opencode uses the model configured in your `opencode.json`.

**Claude Code CLI:** the `claude` CLI is the Claude backend; no extra setup. If your Claude access goes through
Bedrock or Vertex, configure the `claude` CLI for that (e.g. `CLAUDE_CODE_USE_BEDROCK=1` plus AWS credentials).
Bedrock/Vertex model IDs (e.g. `anthropic.claude-sonnet-...`) don't match the `haiku`/`sonnet`/`opus` aliases in
`backends/claude/config.yaml`; edit that file's `models:` list or pass the full ID as `Model:`.

**Codex CLI:**

```bash
npm install -g @openai/codex
```

### Check the setup

In a Claude Code session, run `/code-delegate:backends` (or `bridge.sh --backends` in a terminal). It lists each
backend and whether it is usable right now; for opencode, that means a model is actually reachable.

### Upgrading from 1.x

- The bridge's stall watchdog now works: a delegate that produces no output for `StallTimeout` seconds
  (default 300) is stopped. Previously, stuck agents ran until the 60-minute `Timeout`. For slow models, set
  `StallTimeout:` in the task file.
- The plugin now starts an MCP server (`python3`) for the `delegate` tool.

## Backends

| Backend    | CLI       | Cost | Strengths                                    |
|------------|-----------|------|----------------------------------------------|
| **opencode** | `opencode` | Free | Single-file tasks, boilerplate, CRUD via local LLM |
| **claude**   | `claude`   | Paid | Cross-file reasoning, complex types, multi-file refactors |
| **codex**    | `codex`    | Paid | Single-file tasks, boilerplate               |

The bridge auto-selects the best available backend based on task complexity, or you can specify one explicitly via the `Backend:` header.

## How It Works

The `delegate` tool and the `/code-delegate:*` skills both drive `bin/bridge.sh`; the tool uses its one-step
`bridge.sh run` mode (parallel tasks, fix round, apply uncommitted). The full flow is described in
[how delegation works](docs/how-delegation-works.md).

```
Claude Code (orchestrator)      bridge.sh              Backend (opencode/claude/codex)
──────────────────────        ──────────────          ─────────────────────────────
Write .local_task_<slug>.md
         │
         ├──→ Parse headers (Branch/Backend/Model/Test/Files)
         │    Resolve backend (explicit or auto-select)
         │    Resolve model (alias → id, apply defaults)
         │    git worktree add .git/worktrees_agents/<slug>
         │    Symlink dependencies
         │                    │
         │                    ├──→ backends/<name>/run.sh (inside worktree)
         │                    │         │
         │                    │    ←────┘ commits to isolated branch
         │                    │
         │    Run test gate   │
         │         │
    ←────┘  JSON status (+suggestion on failure)
         │
Review git diff
         │
    (pass) merge  ──or──  (fail) apply suggestion → re-run
```

## Trust Model

`bridge.sh` runs task files, test commands, and each backend's `check_command`/`list_models_command` via `eval`. That's by design, not an oversight: task files are written locally by the orchestrating Claude/Codex/OpenCode session (not fetched from the network), and `Test:`/`check_command`/`list_models_command` are values you or a teammate put in your own repo's task files and `backends/*/config.yaml`. Treat those config files with the same care as any other script in the repo — anyone who can edit them can run arbitrary shell.

## Usage

### Just ask (the `delegate` tool)

With the plugin installed, Claude Code has a `delegate` tool. Ask for the work as usual; for large,
well-specified work Claude hands it off in a single call:

> "Add a suppliers resource across all layers, following the customers implementation."

The tool takes a list of tasks (`name`, `objective`, `requirements`, a one-line `test` command, optional
`files`, `backend`, `model`). It writes the task files, runs them in parallel in isolated git worktrees, gives each
one automatic fix round if its test fails, and applies passing work to your working tree **uncommitted**, so you
review and commit it as usual. It returns a short report with the applied diff. `delegate_wait` keeps waiting for
tasks that take longer than about 9 minutes.

When it's worth delegating: every step the orchestrator takes re-sends its whole context, so a hand-off only
pays off for work that would take it many steps (multi-file features, migrations, test suites, bulk
boilerplate). The tool's description tells Claude this, so small changes are done directly. See the
[benchmark results](docs/benchmark-methodology.md) for the measurements behind this.

### Slash commands (step by step, with approval)

| Command | Description |
|---------|-------------|
| `/code-delegate:delegate` | Plan, distribute and dispatch in one go, with a distribution summary you approve |
| `/code-delegate:plan` | Break requirements into `.local_task_*.md` specs (no backend/model assignment) |
| `/code-delegate:distribute` | Classify tasks and assign `Backend:`/`Model:` headers |
| `/code-delegate:dispatch [slug...]` | Execute task files via `bridge.sh`, with monitoring and feedback loops |
| `/code-delegate:status` | Show active agent worktrees and progress |
| `/code-delegate:backends` | List installed backends and availability |
| `/code-delegate:cleanup <slug>` | Remove a worktree after merging |

## Skills Reference

Each slash command above is backed by a skill under `skills/`. Skills also auto-trigger on natural-language phrasing (Claude Code matches the `description` in each `SKILL.md`), not just the explicit `/code-delegate:*` command.

| Skill | Triggers on | Allowed tools | What it does |
|-------|-------------|----------------|---------------|
| **delegate** | "implement this", "build this", "write the code for", "generate tests for", "execute the plan" | Bash, Read, Write | Bundled flow — runs plan → distribute → dispatch in sequence. The top-level entry point for offloading a coding task instead of writing it inline. |
| **plan** | "plan the implementation", "break this into tasks", "write task files for", "plan the work" | Bash, Read, Write, Grep, Glob | Breaks requirements into bounded sub-tasks (≤2–3 files each) and writes `.local_task_<slug>.md` spec files. Leaves `Backend:`/`Model:` headers empty — that's the distribute step's job. |
| **distribute** | "distribute", "assign models", "pick backends", "re-distribute", "change model for" | Bash, Read, Edit, Grep, Glob | Reads existing `.local_task_*.md` files and classifies each as DELEGATE, DELEGATE (security-approved), DELEGATE (larger model), or IMPLEMENT DIRECTLY. Runs `bridge.sh --backends`/`--models` for real availability, presents a distribution summary, and writes `Backend:`/`Model:` headers after user approval. |
| **dispatch** | "dispatch the tasks", "run the tasks", "execute the task files", "launch the agents", "start the bridge" | Bash, Read, Write, Glob | Runs `bridge.sh <slug>` for each ready task file (parallel for multiple), parses the JSON status result, handles pass/fail/error/aborted/no_backend outcomes, and manages the feedback loop (`.local_feedback_<slug>.md`) for re-runs. |
| **status** | "what's running", "check agent status", "show active agents", "is the delegate done yet", "what worktrees are open" | Bash | Runs `bridge.sh --status` and presents active/completed agent worktrees, backend used, and last log line. |
| **backends** | "what backends do I have", "list available models", "is opencode installed", "which backend should I use" | Bash | Runs `bridge.sh --backends` and presents installed backends, availability, cost tier, and capabilities. |
| **cleanup** | "clean up the worktree", "remove the agent branch", "delete the delegate worktree for" | Bash | Verifies a branch has been merged, then runs `bridge.sh --cleanup <slug>` to remove its worktree. Warns and asks for confirmation if the branch isn't merged yet. |

Sub-skill relationship: `delegate` is a superset that chains `plan` → `distribute` → `dispatch`. Use the individual skills directly for granular control (e.g. re-running just `distribute` after a backend goes offline) instead of the bundled flow.

### Examples

**Single task delegation:**
> "Implement a structured logger module with JSON output and context support."

**Parallel dispatch:**
> "Implement the auth middleware, the rate limiter, and the request logger as separate modules."

**Explicit backend + model:**
> "Use the claude backend with opus to implement this complex type system."

### Delegating by default (optional)

To make Claude reach for the step-by-step flow whenever it implements something, add to your `~/.claude/CLAUDE.md`:

```markdown
When you reach the implementation phase, invoke the `code-delegate:delegate` skill
instead of writing code yourself. Invoke via: Skill tool → skill: "code-delegate:delegate"
```

This delegates small tasks too, which costs more Claude tokens than doing them directly; most users don't need it.

## Features

- **`delegate` tool** — one-call hand-off from Claude Code: parallel tasks, automatic fix round, applied uncommitted with the diff returned
- **Multi-backend dispatch** — route tasks to local models (free) or cloud APIs (capable) based on complexity
- **Auto-selection** — bridge picks the best available backend based on task files, cross-file needs, and cost tier. For backends with `models: dynamic` (opencode), "available" also means a model is actually loaded right now, not just that the CLI is installed — a dispatch or `Model:` header against an unavailable/unknown model fails fast with a suggestion instead of failing deep inside the backend
- **Model escalation** — when a task fails, the bridge suggests the next model up (haiku → sonnet → opus) or a cross-backend fallback
- **Tiered security** — security-sensitive tasks (auth, crypto, secrets) are blocked from local models but can be delegated to approved combos like `claude/opus`
- **Parallel execution** — dispatch multiple tasks simultaneously, each in its own Git worktree
- **Test gates** — optional test commands that must pass before a task is considered done
- **Watcher** — stops stalled or doom-looping agents (wall-clock timeout, no-output stall timeout, failure-loop counting)

## Benchmarks

`tests/benchmark/` measures the Claude tokens a session spends on the same task with vs. without
delegation, and scores correctness with hidden tests. It runs against whatever models your
opencode install lists, including a company's self-hosted platform.

- [Benchmark methodology](docs/benchmark-methodology.md): conditions, metrics, scoring, caveats
- [How delegation works](docs/how-delegation-works.md): orchestrator, skills, bridge and backends end to end

```bash
cd tests/benchmark && ./bench.sh doctor && ./bench.sh compare --reps 1 01
```

## Bridge CLI

```bash
bridge.sh <slug>                          # Run task
bridge.sh run <slug>... [--max-wait S]    # Fast path: parallel, fix round, apply uncommitted, compact report
bridge.sh wait <slug>... [--max-wait S]   # Keep waiting for tasks started with run
bridge.sh --status                        # List active agents
bridge.sh --backends                      # List installed backends
bridge.sh --models [backend]              # List available models
bridge.sh --logs [slug]                   # Tail agent logs
bridge.sh --cleanup <slug>                # Remove worktree
bridge.sh --suggest '<json>'              # Get fallback suggestion
bridge.sh --security-check <backend> <model>  # Check security approval
```

## Task File Format

```markdown
---
Branch: feat/logger
Backend: auto
Model: sonnet
Test: npm test -- --filter logger
Files: src/logger.ts, src/logger.test.ts
---

## Objective
One sentence.

## File Operations

### CREATE src/logger.ts
- Bullet point requirements

### MODIFY src/index.ts
- What to change, line range hints

## Constraints
- Explicit boundaries
```

**Headers:** `Branch:` (required), `Backend:` (optional, default: auto), `Model:` (optional), `Test:` (optional; required by `bridge.sh run` and the `delegate` tool, one line), `Files:` (optional), `Timeout:` (seconds, default 3600), `StallTimeout:` (seconds without output, default 300), `MaxFails:` (default 8), `FailPattern:` (optional).

## Project Structure

```
code-delegate/
├── .claude-plugin/
│   ├── plugin.json              # Plugin manifest (also declares the MCP server)
│   ├── marketplace.json         # Marketplace index
│   └── hooks/                   # Optional hooks and their installer
├── skills/
│   ├── delegate/SKILL.md        # Bundled skill: plan + distribute + dispatch
│   ├── plan/SKILL.md            # code-delegate:plan
│   ├── distribute/SKILL.md      # code-delegate:distribute
│   ├── dispatch/SKILL.md        # code-delegate:dispatch
│   ├── status/SKILL.md          # code-delegate:status
│   ├── backends/SKILL.md        # code-delegate:backends
│   └── cleanup/SKILL.md         # code-delegate:cleanup
├── backends/
│   ├── opencode/                # Local LLM via OpenCode CLI
│   │   ├── run.sh
│   │   └── config.yaml
│   ├── claude/                  # Claude Code CLI
│   │   ├── run.sh
│   │   └── config.yaml
│   └── codex/                   # OpenAI Codex CLI
│       ├── run.sh
│       └── config.yaml
├── bin/
│   ├── bridge.sh                # Backend-agnostic dispatcher
│   └── bridge-run.sh            # Fast path: bridge.sh run / wait
├── mcp/
│   └── server.py                # delegate / delegate_wait MCP tools (stdlib only)
├── lib/
│   └── usage_wrap.py            # Opt-in token accounting for backend runners (benchmark)
├── docs/                        # How delegation works, benchmark methodology, backend authoring
├── CLAUDE.md                    # Claude Code instructions
├── AGENTS.md                    # Codex/OpenCode instructions + tool mappings
└── tests/
    ├── bridge/                  # Fast-path tests with a fake backend
    ├── mcp/                     # MCP tool tests
    ├── workflow/                # Behavioral validation scenarios (does it classify/route correctly?)
    └── benchmark/               # Claude tokens with vs. without delegation, scored by hidden tests
```

## License

MIT
