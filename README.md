# Claude Code + OpenCode Local Delegation Skill

A global skill for Claude Code that delegates token-heavy implementation tasks to a local LLM running via OpenCode + LM Studio. Each task runs in an isolated Git worktree, enabling parallel dispatch of multiple local subagents.

## How It Works

```
Claude Code (cloud)          bridge.sh              OpenCode (local)
─────────────────          ──────────────          ─────────────────
Write .local_task_<slug>.md
         │
         ├──→ Parse Branch/Test/Files headers
         │    git worktree add .git/worktrees_agents/<slug>
         │    Symlink dependencies
         │                    │
         │                    ├──→ opencode run (inside worktree)
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

### 1. Install the skill (any machine)

```bash
git clone https://github.com/iimani/opencode-delegate.git ~/.claude/skills/opencode-delegate
```

That's it — Claude Code auto-discovers global skills from `~/.claude/skills/`.

### 2. Install OpenCode + LM Studio (optional, per machine)

The skill works best with a local inference engine, but gracefully prompts the user to let Claude proceed directly if OpenCode isn't installed.

**LM Studio:**
1. Download from [lmstudio.ai](https://lmstudio.ai)
2. Load a coding model (e.g., Qwen 2.5 Coder, DeepSeek Coder)
3. Start the local server (defaults to `http://localhost:1234`)

**OpenCode:**
```bash
curl -fsSL https://opencode.ai/install | bash
```

Configure it to use LM Studio in `~/.config/opencode/opencode.json`:
```json
{
  "provider": {
    "lmstudio": {
      "name": "LM Studio (Local)",
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "http://127.0.0.1:1234/v1",
        "apiKey": "lm-studio"
      },
      "models": {
        "your-model-id": { "name": "your-model-id" }
      }
    }
  },
  "model": "lmstudio/your-model-id"
}
```

### 3. Make it the default workflow

Add this to your global `~/.claude/CLAUDE.md` so Claude always uses delegation:

```markdown
# Global Cloud-to-Local Orchestration Rules

You are the **Lead Architect (Claude Code)**. Your partner is the **Developer Agent (OpenCode via LM Studio)**.
To maximize efficiency, you must never write massive blocks of repetitive code, boilerplate, or heavy unit tests yourself. Instead, offload them using the `opencode-delegate` skill.
```

## Usage

### Single task delegation
Tell Claude to implement something — it will write a spec, invoke the bridge, and review the result:

> "Implement a structured logger module with JSON output and context support."

### Parallel dispatch
For multi-file features, Claude writes multiple task specs and invokes the bridge in parallel:

> "Implement the auth middleware, the rate limiter, and the request logger as separate modules."

### Manual invocation
You can also invoke the skill explicitly:

> "Use the opencode-delegate skill to implement this."

### Check active agents
```bash
~/.claude/skills/opencode-delegate/bridge.sh --status
```

### Clean up after merging
```bash
~/.claude/skills/opencode-delegate/bridge.sh --cleanup <slug>
```

## When OpenCode Isn't Installed

If `opencode` is not in PATH, the bridge exits with code 10. Claude will ask you:

> "OpenCode isn't installed on this machine. Should I implement this myself instead?"

If you say yes, Claude reads the task spec it already wrote and implements it directly. The spec format is designed to be readable by both OpenCode and Claude.

## Task File Format

```markdown
---
Branch: feat/logger
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

## Roadmap

See [TODO.md](TODO.md) for planned features, including delegation to Claude API models as an alternative backend.
