---
name: distribute
description: Analyze planned .local_task_*.md files and assign backends and models based on task complexity, security requirements, and available backends. Use after /code-delegate:plan or when you want to re-analyze task distribution with different available models.
trigger: /code-delegate:distribute
allowed-tools:
  - Bash
  - Read
  - Edit
---

# Distribute

Reads `.local_task_*.md` files, classifies each task, and writes `Backend:` and `Model:` headers after user approval. Run this between `/code-delegate:plan` and `/code-delegate:dispatch`.

## Discovery

Find task files and gather context before classifying:

1. List all `.local_task_*.md` files in the project root. If a slug argument was passed (e.g. `/distribute feat-logger`), only process that file.
2. For each file, read and extract:
   - `Branch:`, `Files:` headers
   - `## Objective` — one-sentence summary
   - File count (count entries in `Files:` header, or count `### CREATE/MODIFY/DELETE` sections in body)
   - Whether it touches security-sensitive code (auth, tokens, signatures, JWT, OAuth, HMAC, crypto, secrets, trust boundaries)
   - Whether `Backend:` and `Model:` headers already exist (re-distribution case)
3. Run `bridge.sh --backends` to get backend availability.
4. Run `bridge.sh --models` to get available models per backend.

## Classification Criteria

Classify each task as one of four outcomes:

### DELEGATE
All of the following must hold:
- Single-file or tightly bounded (≤2–3 files, no cross-cutting concerns)
- Boilerplate-heavy: CRUD handlers, test suites, serialization, config parsing
- No complex type reasoning (no TypeScript generics, no Swift concurrency, no Rust lifetimes)
- Failure is recoverable and low-risk (adding a feature, not modifying critical shared state)
- Task complexity within the configured model's known ceiling
- Not shorter to do directly than to specify precisely enough for a local model

### DELEGATE (security-approved)
When the task touches auth, tokens, signatures (JWT, OAuth, HMAC), cryptography, or secrets:
- **Never assign to local models** (opencode) — local models are not auditable
- Run `bridge.sh --security-check <backend> <model>` to verify approval. Currently only `claude/opus` is approved.
- If no approved backend+model is available, classify as IMPLEMENT DIRECTLY instead

### DELEGATE (larger model)
When the task is delegatable but exceeds a small local model's ceiling:
- Multiple files with bounded scope but non-trivial type reasoning
- Use `Backend: claude` / `Model: sonnet` or `opus`, or a larger local model via opencode

### IMPLEMENT DIRECTLY
Assign to Claude orchestrator when any of the following holds:
- Security-sensitive AND no approved backend+model is available or user declined escalation
- Requires cross-file reasoning where correctness depends on cross-file invariants
- Involves complex type systems requiring compiler error chain inference (TS generics, Swift concurrency, Rust lifetimes)
- Architectural change that ripples across the codebase
- High risk of silent breakage (shared interfaces, database schema migrations)
- The task is shorter to do directly than to specify precisely enough for a local model

## Model Selection Heuristic

Use available models from `bridge.sh --models` output. Default assignments:

| Scope | Backend | Model |
|---|---|---|
| Single-file, well-scoped | opencode | smallest available (≤9B) |
| Multi-file bounded | opencode | medium available (27B–33B) |
| Multi-file with type reasoning | claude | sonnet |
| Cross-file / security-sensitive | claude | opus |

The bridge resolves model aliases automatically — `Model: haiku` maps to the correct ID. If no `Model:` header is set, the backend's default is used. For opencode, run `bridge.sh --models opencode` to query models available at runtime.

## Distribution Summary

After classifying all tasks, present the summary and wait for approval:

```
Task distribution:

  DELEGATE
  ├─ feat/logger         [opencode / qwen-9b]   — new file, boilerplate logger
  └─ feat/config-parser  [opencode / qwen-9b]   — single file, struct parsing

  DELEGATE (security-approved)
  └─ feat/jwt-validation [claude / opus]        — auth logic (opus approved)

  IMPLEMENT DIRECTLY (Claude orchestrator)
  └─ refactor/shared-db                         — 6 files, schema migration, cross-file invariants

  DELEGATE (larger model)
  └─ feat/generics-util  [claude / opus]        — TypeScript conditional types

Available models:
  opencode:  qwen-9b, deepseek-33b
  claude:    haiku, sonnet (default), opus [security: opus]
  codex:     (unavailable)

Override model selections, or proceed with defaults?
```

The user can respond with overrides like "use opus for feat/generics-util" or "proceed with defaults". Apply any overrides before writing headers.

After approval:
- **Delegated tasks**: write `Backend:` and `Model:` headers into the task file using Edit
- **IMPLEMENT DIRECTLY tasks**: note them but do not write headers — the orchestrator handles these after dispatch

## Re-distribution

If task files already have `Backend:` and `Model:` headers:
- Show current assignments in the distribution summary, labeled `(current)`
- Explain why re-distribution was triggered if obvious (e.g. a backend went offline, user swapped local model)
- Only overwrite existing headers after explicit approval

## Writing Headers

After user approval, use Edit to insert or update `Backend:` and `Model:` in the frontmatter of each delegated task file. Headers go in the `---` block, after `Branch:`:

```
---
Branch: feat/logger
Backend: opencode
Model: qwen-9b
...
---
```

Do not touch the body of the task file.

## Output

After writing all headers, confirm:

> Distribution complete. Run `/code-delegate:dispatch` to execute, or `/delegate` for the full flow.

List any IMPLEMENT DIRECTLY tasks that need to be handled by the orchestrator after dispatch.
