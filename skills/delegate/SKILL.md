---
name: delegate
description: This skill should be used when the user asks to implement a feature, write boilerplate, generate tests, or execute any multi-file coding plan. Trigger phrases include "implement this", "build this", "write the code for", "generate tests for", "execute the plan". Routes tasks to local or cloud AI agents in isolated Git worktrees instead of writing code inline.
allowed-tools:
  - Bash
  - Read
  - Write
---

# Code Delegate

Bundled flow: plan → distribute → dispatch in one step. For individual steps, use `/code-delegate:plan`, `/code-delegate:distribute`, or `/code-delegate:dispatch`.

Acts as a high-level Architect and Code Reviewer, offloading token-heavy coding tasks to local or cloud AI agents. Each task runs in an isolated Git worktree, enabling parallel dispatch of multiple subagents. Available backends: opencode (local, free), claude (Anthropic API), codex (OpenAI).

## When to Use

Use this skill when the user asks to implement a complex plan, write heavy boilerplate, or generate exhaustive test suites — delegate instead of writing the code directly.

## Bundled Flow

Run all three steps in sequence:

1. **Plan** — Break requirements into sub-tasks, write `.local_task_*.md` files. See `/code-delegate:plan` for detailed planning guidance.
2. **Distribute** — Classify each task, run `bridge.sh --models`, present distribution summary, wait for user approval, write `Backend`/`Model` headers. See `/code-delegate:distribute` for classification criteria.
3. **Dispatch** — Run `bridge.sh <slug>` for each task (parallel for multiple). See `/code-delegate:dispatch` for execution protocol, fallback handling, and monitoring.

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
- `StallTimeout:` (optional) — seconds of log silence before the agent is killed (default: 600 = 10 min). Increase for large remote models (e.g. `StallTimeout: 1200` for a 70B model that takes time to produce its first token)
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

The full classification criteria (DELEGATE, DELEGATE security-approved, DELEGATE larger model, IMPLEMENT DIRECTLY), the security rule for auth/crypto/secrets tasks, and the distribution summary format live in **`/code-delegate:distribute`** — this skill defers to that one rather than keeping a second copy, so a policy change (e.g. a newly approved security combo) only needs updating in one place.

Run `bridge.sh --models` before showing the summary so the user sees real available models, not placeholders. The task file you are about to write IS the plan — do not write a separate prose spec first, it won't be passed to the delegate and only wastes tokens.

Only after user approval: write task files for delegated tasks, implement direct tasks yourself, and invoke the bridge.

## Execution Protocol

Run `bridge.sh <slug>` for each task — parallel via `run_in_background: true` when dispatching multiple. The bridge's final stdout line is a JSON status object (`pass | fail | error | aborted | no_backend`).

The full execution protocol — parsing the JSON status, monitoring background agents, the feedback loop, cleanup, and how to handle each outcome (including a `"pass"` with no diff, an `aborted` agent, or a `no_backend` exit) — lives in **`/code-delegate:dispatch`**, kept canonical there rather than duplicated here. The core rules that apply regardless of which skill you're in:

- **Never act on a bridge fallback `suggestion` automatically** — always present it to the user first.
- **Never silently take over implementation from the delegate** — even on failure, aborts, or a no-op "pass", ask before implementing yourself.
- **An abort on one task doesn't mean the rest should be implemented directly** — re-apply the distribution criteria to each remaining task independently.

## Notes
- Do not write massive blocks of code directly if this skill is available.
- The Claude Code plugin framework adds the plugin's `bin/` directory to PATH using its absolute install path — invoke `bridge.sh` as a bare command and the framework resolves it correctly. Manual installs outside the plugin framework must add `<plugin-root>/bin` to PATH explicitly.
- Worktrees are stored in `.git/worktrees_agents/` — inside `.git/`, so invisible to the project.
- Dependencies (node_modules, venv, vendor, etc.) are auto-symlinked into worktrees.

## Sub-Skills

For granular control, use the individual steps:
- `/code-delegate:plan` — write task files from requirements (no backend/model assignment)
- `/code-delegate:distribute` — analyze tasks and assign backends/models
- `/code-delegate:dispatch [slug...]` — execute task files via bridge.sh
