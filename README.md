# Code Delegate — Multi-Backend Code Delegation Plugin

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

**Claude Code CLI (already installed if you're reading this):**
The `claude` CLI is the Claude backend — no extra setup needed.

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

## Usage

### Slash commands

| Command | Description |
|---------|-------------|
| `/code-delegate` | Main command — distribution analysis + task execution |
| `/code-delegate:status` | Show active agent worktrees and progress |
| `/code-delegate:backends` | List installed backends and availability |
| `/code-delegate:cleanup <slug>` | Remove a worktree after merging |

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
- **Auto-selection** — bridge picks the best available backend based on task files, cross-file needs, and cost tier
- **Model escalation** — when a task fails, the bridge suggests the next model up (haiku → sonnet → opus) or a cross-backend fallback
- **Tiered security** — security-sensitive tasks (auth, crypto, secrets) are blocked from local models but can be delegated to approved combos like `claude/opus`
- **Parallel execution** — dispatch multiple tasks simultaneously, each in its own Git worktree
- **Test gates** — optional test commands that must pass before a task is considered done
- **Watcher** — kills stalled or doom-looping agents (timeout, stall detection, failure loop counting)

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
│   ├── delegate/SKILL.md        # Main skill: distribution + execution
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
├── bridge.sh                    # Backend-agnostic dispatcher
├── CLAUDE.md                    # Claude Code instructions
├── AGENTS.md                    # Codex/OpenCode instructions + tool mappings
└── tests/                       # Workflow validation scenarios
```

## License

MIT
