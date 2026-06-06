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
# Default Delegation Behavior — OVERRIDES ALL EXECUTION SKILLS

**This rule takes priority over superpowers execution skills** (executing-plans,
subagent-driven-development, and any other skill that writes code).

When you reach the implementation phase — whether driven by brainstorming, a direct
request, or any other trigger — follow this flow instead of writing code yourself or
running executing-plans:

1. **Classify each sub-task** using the Distribution Analysis criteria in the
   `opencode-delegate` skill. Produce a distribution summary (DELEGATE / IMPLEMENT
   DIRECTLY / ROUTE TO LARGER MODEL) and present it to the user for approval.
2. **Skip writing-plans / prose spec generation.** The `.local_task_<slug>.md` files
   you are about to write ARE the plan. Writing a prose spec first and then converting
   it to a task file wastes tokens — the spec is never passed to the delegate.
3. **After user approval:** write task files for delegated tasks, implement direct tasks
   yourself, and invoke the bridge.

Invoke the skill via: `Skill tool → skill: "opencode-delegate"`

The skill handles everything: distribution criteria, spec format, worktree isolation,
bridge invocation, test gates, and feedback loops. If OpenCode is not installed (bridge
exits with code 10), ask the user whether to proceed yourself.

**When NOT to delegate** (do it yourself without asking):
- One-line fixes, config edits, or single-field changes
- Exploratory reads, git operations, or reviews
- The user explicitly says "do it yourself" or "don't delegate"
```

#### Why the override is needed

If you use the [superpowers](https://github.com/obra/superpowers) plugin, its skill chain
(brainstorming → writing-plans → executing-plans) has a hardcoded execution phase that
dispatches Claude subagents or writes code inline. Without the override, superpowers takes
over at the implementation step and never reaches the `opencode-delegate` skill. The
`CLAUDE.md` instruction intercepts this and replaces two steps at once: it skips
writing-plans (whose prose spec is never passed to OpenCode anyway) and replaces
executing-plans with the local delegate.

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
