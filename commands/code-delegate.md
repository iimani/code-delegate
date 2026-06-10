---
description: Delegate code implementation to local or cloud AI agents using isolated Git worktrees for parallel execution.
argument-hint: Optional task description or plan reference
---

# Code Delegate

This command allows Claude Code to act as a high-level Architect and Code Reviewer, offloading token-heavy coding tasks to local or cloud AI agents. Each task runs in an isolated Git worktree, enabling parallel dispatch of multiple subagents. Available backends: opencode (local, free), claude (Anthropic API), codex (OpenAI).

## When to Use

When the user asks you to implement a complex plan, write heavy boilerplate, or generate exhaustive test suites, use this skill instead of writing the code yourself.

## Slug Convention

Every task is identified by a **branch slug** — the `Branch:` header with `/` replaced by `-`.
- `feat/logger` → slug `feat-logger`
- `fix/parse-error` → slug `fix-parse-error`

The slug is used for file naming, worktree directory naming, and feedback routing.

## Task File Format

Write `.local_task_<slug>.md` in the project root:

```markdown
---
Branch: feat/logger
Backend: opencode
Test: npm test -- --filter logger
Files: src/logger.ts, src/logger.test.ts
---

## Objective
One sentence describing what this achieves.

## File Operations

### CREATE src/logger.ts
- Bullet points describing the implementation
- One bullet per requirement

### MODIFY src/index.ts
- What to change and where
- Lines 14-28 are the target zone

## Constraints
- No changes outside listed files
- Must pass type checking
```

**Headers:**
- `Branch:` (required) — the Git branch name to create
- `Backend:` (optional) — which backend to use: `opencode`, `claude`, `codex`, or `auto` (default: `auto` — picks based on task complexity and backend availability)
- `Model:` (optional) — provider/model to use (e.g., `lmstudio/qwen/qwen3.5-9b`)
- `Test:` (optional) — shell command to run as a test gate after implementation
- `Files:` (optional) — comma-separated list of files the agent should touch
- `Timeout:` (optional) — wall-clock kill limit in seconds (default: 3600 = 60 min)
- `MaxFails:` (optional) — abort after this many failure-pattern matches in the log (default: 8; set to 0 to disable)
- `FailPattern:` (optional) — ERE pattern counted as one failure hit (default: `build commands failed|compilation error|FAILED|npm ERR!`)

**Model selection guidance:**
Small local models (≤9B via opencode) handle single-file, well-scoped tasks reliably. For complex type systems, cross-file refactors, or multi-step build feedback loops, set `Backend: claude` with an appropriate model. The `auto` backend selection reads each backend's config.yaml capabilities to route tasks.

**Body guidelines:**
- Use `CREATE` / `MODIFY` / `DELETE` verbs per file section
- Include line range hints for modifications (helps smaller models focus)
- Keep constraints explicit — local models are prone to scope creep
- Bullet points only, no prose paragraphs
- **NEVER write code blocks or function bodies in the spec.** Describe WHAT to build, not HOW. The delegate writes the code — that's the whole point. If you're pasting Swift/TypeScript/Python into the task file, you're doing the delegate's job and wasting tokens twice. Say "add a `calendar(start:end:)` method that fetches from the `/calendar` endpoint with ISO8601 date query params" — don't write the function.

## Distribution Analysis

Before writing any task files or running the bridge, classify each sub-task and present a distribution summary to the user. Wait for approval before proceeding.

### Delegate when:
- Single-file or tightly bounded (≤2–3 files, no cross-cutting concerns)
- Boilerplate-heavy: CRUD handlers, test suites, serialization, config parsing
- No complex type reasoning required (no TypeScript generics, no Swift concurrency, no Rust lifetimes)
- Failure is recoverable and low-risk (adding a feature, not modifying critical shared state)
- Task complexity is within the configured model's known ceiling

### Security-sensitive tasks (auth, crypto, secrets, trust boundaries):
- **NEVER delegate to local models** (opencode) — local models are not auditable and must not touch security-critical code
- **MAY delegate to security-approved backend+model combos** — run `bridge.sh --security-check <backend> <model>` to verify. Currently only `claude/opus` is approved.
- If the user's current backend+model is not security-approved, show a suggestion: "This task is security-sensitive. [current model] is not approved — suggest delegating with `Backend: claude` / `Model: opus`, or I can implement it directly."
- If no security-approved backend+model is available, implement directly

### Implement directly (Claude orchestrator) when:
- Security-sensitive task AND no approved backend+model is available or the user declines escalation
- Requires multi-file reasoning where correctness depends on cross-file invariants
- Involves complex type systems where compiler error chains require inference (TS generics, Swift concurrency, Rust lifetimes)
- Architectural change that ripples across the codebase
- High risk of silent breakage (shared interfaces, database schema migrations)
- The task is shorter to do directly than to specify precisely enough for a local model

### Route to a more capable model when:
- Task scope exceeds the local model's ceiling but is still delegatable — set `Backend: claude` with `Model: opus`, or use a larger local model via opencode
- Security-sensitive task with a non-approved model — escalate to an approved model (e.g. `claude/opus`)

### Model selection

Before showing the distribution summary, run `bridge.sh --models` to get available models per backend. Present models alongside the distribution so the user can override defaults.

The bridge resolves model aliases automatically — if the user writes `Model: haiku`, the bridge maps it to the correct ID for the selected backend. If no `Model:` header is set, the backend's default model is used.

For the opencode backend, models are dynamic (whatever's running locally). Run `bridge.sh --models opencode` to query available models at runtime.

### Distribution summary (show this to the user before any execution)

```
Task distribution:

  DELEGATE
  ├─ feat/logger         [opencode]       — new file, boilerplate JSON logger
  └─ feat/config-parser  [opencode]       — single file, straightforward struct parsing

  DELEGATE (security-approved model)
  └─ feat/jwt-validation [claude / opus]  — auth logic, security-sensitive (opus approved)

  IMPLEMENT DIRECTLY (Claude orchestrator)
  └─ refactor/shared-db  — touches 6 files, cross-file invariants, schema migration

  DELEGATE (larger model)
  └─ feat/generics-util  [claude / opus]  — TypeScript conditional types, needs strong type reasoning

Available models:
  opencode:  (dynamic) qwen-9b, deepseek-33b
  claude:    haiku, sonnet (default), opus [security: opus]
  codex:     (unavailable)

Override model selections, or proceed with defaults?
```

The user can respond with overrides like "use opus for feat/generics-util" or "proceed with defaults". Write the chosen model into each task file's `Model:` header.

Only after user approval: write task files for delegated tasks, implement direct tasks yourself, and invoke the bridge.

## Execution Protocol

### Single task
1. **Distribute**: Classify the task using the criteria above, display the distribution summary, and wait for user approval. The task file you are about to write IS the plan — do not write a separate prose spec first, it won't be passed to the delegate and only wastes tokens.
2. **Write Spec**: Save instructions to `.local_task_<slug>.md` in the project root.
3. **Execute**: Run `bridge.sh <slug>`
4. **Parse Output**: The last stdout line is a JSON status object.
5. **Review**: If `"status": "pass"`, review the changes with `git diff main..<branch>`.
6. **Fix Loop**: If issues found, write `.local_feedback_<slug>.md` and run the bridge again with the same slug.

### Parallel dispatch
Write multiple task files, then invoke the bridge in parallel using `run_in_background: true`:
```
# Launch all tasks in background
bridge.sh feat-logger    # run_in_background: true
bridge.sh feat-auth      # run_in_background: true
bridge.sh fix-parse-error # run_in_background: true
```
Each call creates its own worktree and runs independently. You will be notified as each completes.

### Monitoring progress
While agents are running in the background, check progress with:
```
bridge.sh --logs              # tail all agents
bridge.sh --logs <slug>       # full log for one agent
```
Each agent writes a live log to `.git/worktrees_agents/<slug>/agent.log`. Use `--logs` to give the user progress updates when they ask or when waiting for background tasks to finish.

### Feedback loop
Write `.local_feedback_<slug>.md` with the same `Branch:` header and specific fix instructions. The bridge routes it to the existing worktree for that slug.

### Cleanup
After approving and merging a branch:
```
bridge.sh --cleanup <slug>
```

### Status check
List all active agent worktrees:
```
bridge.sh --status
```

## JSON Status Output

The bridge prints a JSON object as its final stdout line:
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

- `pass` — the agent finished and tests passed (or no test gate)
- `fail` — the agent finished but test gate failed; worktree preserved for feedback. Includes a `suggestion` field.
- `error` — bridge-level failure (missing files, git errors, agent crash)
- `aborted` — watcher killed the agent due to timeout, stall, or failure loop. Includes a `suggestion` field.
- `no_backend` — selected backend CLI not installed. Includes a `suggestion` field.

## Fallback Suggestions

When a task fails, aborts, or the backend is unavailable, the bridge includes a `suggestion` field in the JSON output. The suggestion is one of:

- `{"action": "escalate_model", "backend": "claude", "model": "opus", ...}` — retry with a more capable model in the same backend
- `{"action": "switch_backend", "backend": "claude", "model": "sonnet", "cost_tier": "paid", ...}` — try a different backend entirely
- `{"action": "implement_directly", ...}` — no alternatives available, implement yourself

**How to present suggestions to the user:**

1. Read the `suggestion` field from the JSON output.
2. Present the suggestion alongside the failure context:
   - For `escalate_model`: "Task failed with [model]. The bridge suggests retrying with [suggested model] (same backend). Retry with [model], or should I implement this myself?"
   - For `switch_backend`: "The [backend] backend is unavailable/failed. The bridge suggests trying [alt backend] with [model] ([cost_tier] tier). Switch, or should I implement this myself?"
   - For `implement_directly`: "No alternative backends are available. Should I implement this myself?"
3. **Never act on suggestions automatically.** Always present to the user first.
4. If the user approves a model/backend switch, update the task file's `Backend:` and `Model:` headers and re-run the bridge.

You can also call `bridge.sh --suggest '<json>'` directly to get a fallback suggestion without running a task. The JSON argument takes `reason` (no_backend, aborted, fail), `backend`, `model`, and `task_file` fields.

## Backend Not Available (Exit Code 10)

If the bridge exits with code 10 and `"status": "no_backend"`, the selected backend's CLI is not installed. The `suggestion` field will recommend an alternative backend if one is available. When this happens:

1. **Tell the user** which backend is unavailable.
2. **Present the suggestion**: "The [backend] CLI isn't installed. The bridge suggests [suggestion]. Should I [switch/implement directly]?"
3. If the user agrees to switch, update the task file headers and re-run.
4. If the user agrees to implement directly, **read the task file** (`.local_task_<slug>.md`) and implement using your own tools.
5. Clean up the task file after implementation.

Do NOT silently fall back — always present the suggestion and ask first.

## The Delegate Produced No Changes (Status "pass" But No Diff)

If the bridge reports `"status": "pass"` but `git diff` in the worktree shows no changes, the delegate ran but failed to implement anything. This is a silent failure. When this happens:

1. **Tell the user** that the delegate completed without making any code changes.
2. **Ask the user**: "The delegate didn't produce any changes. Should I implement this myself, or would you like to retry with a different model?"
3. **Do NOT implement the changes yourself without asking.** Always wait for the user's explicit approval.
4. If the user says to proceed, read the task spec and implement it directly.

This rule applies to ALL fallback scenarios — never silently take over implementation from the delegate.

## Agent Aborted (Status "aborted")

If the bridge returns `"status": "aborted"`, the watcher killed the agent due to a timeout, stall, or failure loop. The `suggestion` field recommends the next step. When this happens:

1. **Tell the user** what happened, including the abort reason from `message` and the suggestion.
2. **If the suggestion is `escalate_model` or `switch_backend`**: present it to the user — "The agent was aborted ([reason]). The bridge suggests retrying with [backend/model]. Retry, or should I take over?"
3. **If the user declines the suggestion or suggestion is `implement_directly`**: take over the task directly. Read the original task spec and the partial diff (`git diff main..<branch>`), then implement using your own tools.
4. After completing the implementation, run the test gate manually to verify, then clean up: `bridge.sh --cleanup <slug>`.
5. **Re-evaluate remaining tasks independently.** An abort on one task does NOT mean all remaining tasks should be implemented directly. For each remaining task, apply the Distribution Analysis criteria again — but now factor in the suggestion's reasoning. If a local model doom-looped, the bridge may suggest a larger model for similar remaining tasks.

## Notes
- Do not write massive blocks of code directly if this skill is available.
- Bridge path is resolved relative to the skill's install directory.
- Worktrees are stored in `.git/worktrees_agents/` — inside `.git/`, so invisible to the project.
- Dependencies (node_modules, venv, vendor, etc.) are auto-symlinked into worktrees.
