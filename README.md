# Code Delegate — Parallel AI Coding Agents for Claude Code

A cross-platform plugin that delegates token-heavy implementation tasks to local or cloud AI agents. Works with **Claude Code**, **Codex CLI**, and **OpenCode CLI**. Each task runs in an isolated Git worktree, enabling parallel dispatch of multiple subagents across different backends.

## Installation

### From marketplace (recommended)

```bash
# Add the marketplace
claude plugin marketplace add iimani/code-delegate

# Install the plugin
claude plugin install code-delegate
```

### Manual install (development)

```bash
git clone https://github.com/iimani/code-delegate.git ~/.claude/skills/code-delegate
```

Claude Code auto-discovers plugins from `~/.claude/skills/`.

### Codex CLI

```bash
git clone https://github.com/iimani/code-delegate.git
# Symlink skills into Codex's discovery path
mkdir -p ~/.agents/skills
for skill in code-delegate/skills/*/; do
  ln -sf "$(pwd)/$skill" ~/.agents/skills/"$(basename "$skill")"
done
```

Codex auto-discovers skills from `~/.agents/skills/`. The `AGENTS.md` at the repo root provides Codex-specific tool mappings.

### OpenCode CLI

```bash
git clone https://github.com/iimani/code-delegate.git ~/.claude/skills/code-delegate
```

OpenCode has Claude Code compatibility and auto-discovers skills from `~/.claude/skills/`. It also reads the `AGENTS.md` file for project-level instructions.

### Install backends (at least one)

**OpenCode (local, free):**
```bash
curl -fsSL https://opencode.ai/install | bash
```
Configure with LM Studio, Ollama, or any OpenAI-compatible server.

The opencode backend ships with an empty `default_model` so a fresh install stays portable — when no `Model:` header is set, opencode falls back to whatever model is configured in your own `opencode.json`. To pin a personal default without editing the committed config, export a per-backend env var (machine-local, never committed):

```bash
export OPENCODE_DELEGATE_MODEL="ollama/qwen3.6:27b"
```

The `<BACKEND>_DELEGATE_MODEL` pattern works for every backend, not just opencode — `CLAUDE_DELEGATE_MODEL` and `CODEX_DELEGATE_MODEL` are resolved the same way. Precedence (highest first): `Model:` task header → `<BACKEND>_DELEGATE_MODEL` env var → config `default_model` → the CLI's own default.

**Claude Code CLI (already installed if you're reading this):**
The `claude` CLI is the Claude backend — no extra setup needed. If your Claude access goes through Bedrock or Vertex rather than the API console, configure the `claude` CLI itself for that (e.g. `CLAUDE_CODE_USE_BEDROCK=1` plus AWS credentials) — the bridge just shells out to whatever `claude` resolves to. Note that Bedrock/Vertex model IDs (e.g. `anthropic.claude-sonnet-...`) don't match the `haiku`/`sonnet`/`opus` aliases in `backends/claude/config.yaml`; edit that file's `models:` list to match your deployment's IDs, or pass the full ID via the task file's `Model:` header.

**Codex CLI:**
```bash
npm install -g @openai/codex
```

## Backends

| Backend    | CLI       | Cost | Strengths                                    |
|------------|-----------|------|----------------------------------------------|
| **opencode** | `opencode` | Free | Single-file tasks, boilerplate, CRUD via local LLM |
| **claude**   | `claude`   | Paid | Cross-file reasoning, complex types, multi-file refactors |
| **codex**    | `codex`    | Paid | Single-file tasks, boilerplate               |

The bridge auto-selects the best available backend based on task complexity, or you can specify one explicitly via the `Backend:` header.

## How It Works

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

### Slash commands

| Command | Description |
|---------|-------------|
| `/code-delegate` | Main command — bundled plan + distribute + dispatch in one step |
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

### Make it the default workflow

Add to your `~/.claude/CLAUDE.md`:

```markdown
When you reach the implementation phase, invoke the `code-delegate:delegate` skill
instead of writing code yourself. Invoke via: Skill tool → skill: "code-delegate:delegate"
```

## Features

- **Multi-backend dispatch** — route tasks to local models (free) or cloud APIs (capable) based on complexity
- **Auto-selection** — bridge picks the best available backend based on task files, cross-file needs, and cost tier. For backends with `models: dynamic` (opencode), "available" also means a model is actually loaded right now, not just that the CLI is installed — a dispatch or `Model:` header against an unavailable/unknown model fails fast with a suggestion instead of failing deep inside the backend
- **Model escalation** — when a task fails, the bridge suggests the next model up (haiku → sonnet → opus) or a cross-backend fallback
- **Tiered security** — security-sensitive tasks (auth, crypto, secrets) are blocked from local models but can be delegated to approved combos like `claude/opus`
- **Parallel execution** — dispatch multiple tasks simultaneously, each in its own Git worktree
- **Test gates** — optional test commands that must pass before a task is considered done
- **Watcher** — kills stalled or doom-looping agents (timeout, stall detection, failure loop counting)

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

**Headers:** `Branch:` (required), `Backend:` (optional, default: auto), `Model:` (optional), `Test:` (optional), `Files:` (optional), `Timeout:` (optional, default: 3600), `MaxFails:` (optional, default: 8), `FailPattern:` (optional).

## Project Structure

```
code-delegate/
├── .claude-plugin/
│   ├── plugin.json              # Plugin manifest
│   └── marketplace.json         # Marketplace index
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
│   └── bridge.sh                # Backend-agnostic dispatcher
├── CLAUDE.md                    # Claude Code instructions
├── AGENTS.md                    # Codex/OpenCode instructions + tool mappings
└── tests/
    ├── workflow/                # Behavioral validation scenarios (does it classify/route correctly?)
    └── benchmark/                # Claude tokens with vs. without delegation, scored by hidden tests
```

## License

MIT
