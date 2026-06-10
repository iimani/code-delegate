# Code Delegate — Multi-Backend Code Delegation Plugin

A Claude Code plugin that delegates token-heavy implementation tasks to local or cloud AI agents. Each task runs in an isolated Git worktree, enabling parallel dispatch of multiple subagents across different backends.

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
         ├──→ Parse headers (Branch/Backend/Test/Files)
         │    Resolve backend (explicit or auto-select)
         │    git worktree add .git/worktrees_agents/<slug>
         │    Symlink dependencies
         │                    │
         │                    ├──→ backends/<name>/run.sh (inside worktree)
         │                    │         │
         │                    │    ←────┘ commits to isolated branch
         │                    │
         │    Run test gate   │
         │         │
    ←────┘  JSON status       │
         │
Review git diff
         │
    (pass) merge  ──or──  (fail) write .local_feedback_<slug>.md → re-run
```

## Setup

### Install the plugin

```bash
git clone https://github.com/iimani/code-delegate.git ~/.claude/skills/code-delegate
```

Claude Code auto-discovers global skills from `~/.claude/skills/`.

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

### Make it the default workflow

Add to your `~/.claude/CLAUDE.md`:

```markdown
When you reach the implementation phase, invoke the `code-delegate` skill instead of
writing code yourself. Invoke via: `Skill tool → skill: "code-delegate"`
```

## Usage

### Single task delegation
> "Implement a structured logger module with JSON output and context support."

### Parallel dispatch
> "Implement the auth middleware, the rate limiter, and the request logger as separate modules."

### Explicit backend selection
> "Use the claude backend with opus to implement this complex type system."

### Commands

| Command | Description |
|---------|-------------|
| `/code-delegate` | Main command — distribution analysis + task execution |
| `/code-delegate:status` | Show active agent worktrees and progress |
| `/code-delegate:backends` | List installed backends and availability |
| `/code-delegate:cleanup <slug>` | Remove a worktree after merging |

### Bridge CLI

```bash
bridge.sh <slug>              # Run task
bridge.sh --status            # List active agents
bridge.sh --backends          # List installed backends
bridge.sh --logs [slug]       # Tail agent logs
bridge.sh --cleanup <slug>    # Remove worktree
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

**Headers:** `Branch:` (required), `Backend:` (optional, default: auto), `Model:` (optional), `Test:` (optional), `Files:` (optional), `Timeout:` (optional), `MaxFails:` (optional), `FailPattern:` (optional).

## Project Structure

```
code-delegate/
├── commands/
│   └── code-delegate.md     # Main command: distribution + execution
├── skills/
│   ├── status.md            # code-delegate:status
│   ├── backends.md          # code-delegate:backends
│   └── cleanup.md           # code-delegate:cleanup
├── backends/
│   ├── opencode/            # Local LLM via OpenCode CLI
│   │   ├── run.sh
│   │   └── config.yaml
│   ├── claude/              # Claude Code CLI
│   │   ├── run.sh
│   │   └── config.yaml
│   └── codex/               # OpenAI Codex CLI
│       ├── run.sh
│       └── config.yaml
├── bridge.sh                # Backend-agnostic dispatcher
├── CLAUDE.md                # Project-level instructions
└── tests/                   # Workflow validation scenarios
```
