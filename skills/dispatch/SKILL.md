---
name: dispatch
description: This skill should be used when the user asks to dispatch tasks, run the bridge, execute task files, or launch agents. Trigger phrases include "dispatch the tasks", "run the tasks", "execute the task files", "launch the agents", "start the bridge". Executes .local_task_*.md files via bridge.sh with parallel dispatch, monitoring, feedback loops, and fallback handling.
argument-hint: "[slug...] — optional specific slugs to dispatch (default: all task files)"
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

Execute `.local_task_*.md` files via `bridge.sh`. No planning, no distribution analysis — task files must already have `Branch:` and `Backend:` headers set by prior plan/distribute steps.

## Discovery & Validation

If slug arguments were passed, dispatch only those specific tasks. Otherwise find all `.local_task_*.md` files in the project root.

For each task file:
- **`Branch:` header is required.** Skip the task and report an error if missing — the file is not ready to dispatch. Continue dispatching remaining tasks.
- **Warn if `Backend:` is missing.** Bridge will auto-select, but tell the user so they can correct it.
- **Skip tasks with no `Backend:` header that are marked IMPLEMENT DIRECTLY.** Do not dispatch them — handle them yourself or tell the user.

## Execution

### Single task
Run `bridge.sh <slug>` and wait for it to complete. Parse the last stdout line as the JSON status object.

### Multiple tasks
Run each as a background call:
```
bridge.sh feat-logger     # run_in_background: true
bridge.sh feat-auth       # run_in_background: true
bridge.sh fix-parse-error # run_in_background: true
```
Each call creates its own worktree and runs independently. You will be notified as each completes.

### JSON status format
The bridge prints this as the final stdout line:
```json
{
  "status": "pass | fail | error | aborted | no_backend",
  "branch": "feat/logger",
  "slug": "feat-logger",
  "worktree": ".git/worktrees_agents/feat-logger",
  "test_exit_code": 0,
  "test_command": "npm test -- --filter logger",
  "message": "",
  "suggestion": { "action": "escalate_model", "backend": "claude", "model": "opus", "reason": "..." }
}
```

## Result Handling

**`pass`** — Review changes with `git diff main..<branch>`. Report summary to user.

**`pass` but no diff** — Silent failure. Tell the user the delegate completed without making any code changes. Ask: "Should I implement this myself, or retry with a different model?" Do NOT implement without explicit approval.

**`fail`** — Present the failure. Read the `suggestion` field and present it alongside the failure context. NEVER act on suggestions automatically — always ask first.

**`error`** — Report the error message to the user.

**`aborted`** — Tell the user what happened (include `message` and the suggestion). Present options:
- If suggestion is `escalate_model` or `switch_backend`: "The agent was aborted ([reason]). Bridge suggests retrying with [backend/model]. Retry, or should I take over?"
- If suggestion is `implement_directly` or user declines: read the original task spec and the partial diff, then implement yourself.

**`no_backend` (exit 10)** — Tell the user which backend is unavailable and why — the `message` field distinguishes "CLI not found" from "CLI found but no models are currently available" (e.g. opencode installed but LM Studio/Ollama is down or empty). Present the suggestion: "The [backend] backend isn't available right now ([reason]). Bridge suggests [suggestion]. Switch, or should I implement directly?" Do NOT silently fall back — always ask first.

## How to Present Suggestions

Read the `suggestion` field and present it with the failure context:

- `escalate_model`: "Task failed with [model]. Bridge suggests retrying with [suggested model] (same backend). Retry with [model], or should I implement this myself?"
- `switch_backend`: "The [backend] backend is unavailable/failed. Bridge suggests trying [alt backend] with [model] ([cost_tier] tier). Switch, or should I implement this myself?"
- `implement_directly`: "No alternative backends are available. Should I implement this myself?"

If the user approves a model/backend switch: update the task file's `Backend:` and `Model:` headers, then re-run `bridge.sh <slug>`.

You can also call `bridge.sh --suggest '<json>'` to get a fallback suggestion without running a task. Pass `reason`, `backend`, `model`, and `task_file` fields.

## Monitoring

While background tasks run, use these to check progress:
```
bridge.sh --status            # list all active agent worktrees
bridge.sh --logs              # tail all agents
bridge.sh --logs <slug>       # full log for one agent
```
Each agent writes a live log to `.git/worktrees_agents/<slug>/agent.log`. Report progress when the user asks or when waiting.

## Feedback Loop

If issues found during review: write `.local_feedback_<slug>.md` with the same `Branch:` header as the original task file. Include specific fix instructions. Re-run `bridge.sh <slug>` — bridge routes feedback to the existing worktree.

## Cleanup

After the user approves and merges a branch:
```
bridge.sh --cleanup <slug>
```
Do not auto-cleanup — user controls merge.

## Fallback Rules

- **Never implement changes yourself without explicit user approval.** Always ask first.
- **Never act on bridge suggestions automatically.** Always present to the user first.
- **Re-evaluate remaining tasks independently when one fails.** An abort on one task does NOT mean all remaining tasks should be implemented directly. Apply distribution criteria to each remaining task — but factor in the suggestion's reasoning. If a local model doom-looped, bridge may suggest a larger model for similar tasks.
- After completing a direct implementation, run the test gate manually to verify, then clean up: `bridge.sh --cleanup <slug>`.

## Notes

- `bridge.sh` is invoked as a bare command — the plugin framework adds `bin/` to PATH. Manual installs outside the plugin framework must add `<plugin-root>/bin` to PATH explicitly.
- Worktrees live in `.git/worktrees_agents/` — inside `.git/`, invisible to the project.
- Dependencies (node_modules, venv, vendor, etc.) are auto-symlinked into worktrees.
