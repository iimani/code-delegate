# Default Delegation Behavior — OVERRIDES ALL EXECUTION SKILLS

**This rule takes priority over execution skills** (executing-plans,
subagent-driven-development, and any other skill that writes code).

When you reach the implementation phase — whether driven by brainstorming, a direct
request, or any other trigger — follow this flow instead of writing code yourself:

1. **Classify each sub-task** using the Distribution Analysis criteria in the
   `delegate` skill. Produce a distribution summary (DELEGATE / IMPLEMENT
   DIRECTLY / ROUTE TO LARGER MODEL) and present it to the user for approval.
2. **Skip writing-plans / prose spec generation.** The `.local_task_<slug>.md` files
   you are about to write ARE the plan. Writing a prose spec first and then converting
   it to a task file wastes tokens — the spec is never passed to the delegate.
3. **After user approval:** write task files for delegated tasks, implement direct tasks
   yourself, and invoke the bridge.

## Invoking the skill

- **Claude Code:** `Skill tool → skill: "code-delegate:delegate"` (or `/delegate`)
- **Codex CLI:** invoke the `delegate` skill (or `/delegate`)
- **OpenCode CLI:** invoke the `delegate` skill (or `/delegate`)

The skill handles everything: distribution criteria, spec format, worktree isolation,
bridge invocation, test gates, and feedback loops. If a backend is not installed (bridge
exits with code 10), ask the user whether to try a different backend or proceed yourself.

## Tool mapping (Codex CLI)

Skills reference Claude Code tool names. Use these Codex equivalents:

| Skill references | Codex equivalent |
|-----------------|------------------|
| `Bash` (run commands) | native shell tools |
| `Read`, `Write`, `Edit` (files) | native file tools |
| `Task` tool (dispatch subagent) | `spawn_agent` / `wait_agent` / `close_agent` |
| `TodoWrite` (task tracking) | `update_plan` |
| `Skill` tool (invoke a skill) | skills load natively |

## Tool mapping (OpenCode CLI)

OpenCode has Claude Code compatibility — most tool names work as-is. Key differences:

| Skill references | OpenCode equivalent |
|-----------------|---------------------|
| `Bash` (run commands) | native shell tools |
| `Read`, `Write`, `Edit` (files) | native file tools |
| `Skill` tool (invoke a skill) | skills load natively |

## When NOT to delegate (do it yourself without asking)

- One-line fixes, config edits, or single-field changes
- Exploratory reads, git operations, or reviews
- The user explicitly says "do it yourself" or "don't delegate"

## SECURITY RULE — tiered delegation for security-sensitive tasks

- **Never delegate to local models** (opencode): auth logic, token/signature validation (JWT, OAuth, HMAC), cryptography, secret handling, or input validation at trust boundaries. Local models are not auditable.
- **May delegate to security-approved backend+model combos** (currently: `claude/opus`). Run `bridge.sh --security-check <backend> <model>` to verify before delegating. If not approved, suggest escalation or implement directly.
