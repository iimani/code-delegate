# Parallel Worktree Bridge — Design Spec

## Problem

The current `bridge.sh` runs OpenCode synchronously in the main working directory. There is no worktree isolation, no parallel dispatch, no test gating, and no branch-aware feedback routing. The architecture described in the skill's README (parallel worktrees, concurrent subagents) is not implemented.

## Solution

Upgrade `bridge.sh` to a worktree-aware, parallelizable execution bridge. Each invocation creates an isolated Git worktree, runs OpenCode inside it, optionally runs a test gate, and reports structured status back to Claude.

## Invocation Model

One bridge call per task. Claude dispatches N tasks by making N parallel shell calls:

```
bridge.sh feat-logger
bridge.sh feat-auth
bridge.sh fix-parse-error
```

The argument is a **branch slug** — the routing key that ties together the task file, worktree directory, feedback file, and Git branch.

### Slug-to-Branch Mapping

The slug is derived from the `Branch:` header in the task file by replacing `/` with `-`. Examples:
- `feat/logger` → `feat-logger`
- `fix/parse-error` → `fix-parse-error`

The bridge reads the actual branch name from the `Branch:` header inside the task file and uses the slug only for filesystem paths and file naming.

## File Convention

### Task files
Claude writes `.local_task_<slug>.md` in the project root:

```markdown
---
Branch: feat/logger
Test: npm test -- --filter logger
Files: src/logger.ts, src/logger.test.ts
---

## Objective
One sentence describing what this achieves.

## File Operations

### CREATE src/logger.ts
- Export a Logger class with methods: info(msg), error(msg, err?)
- Use structured JSON output to stdout

### MODIFY src/index.ts
- Import Logger from ./logger
- Replace console.log calls with logger.info()
- Lines 14-28 are the target zone

## Constraints
- No changes outside listed files
- Must pass npm run typecheck
```

### Feedback files
Claude writes `.local_feedback_<slug>.md` in the project root. The bridge detects this, locates the existing worktree for that slug, and re-runs OpenCode inside it.

## Execution Flow

### New task (task file exists, no worktree yet)

1. Parse headers from `.local_task_<slug>.md`: `Branch`, `Test`, `Files`
2. Validate: if `Files` header present, check listed paths exist in the repo
3. Create worktree: `git worktree add .git/worktrees_agents/<slug> -b <branch>` (from current HEAD)
4. Dependency linking: detect and symlink project dependency directories into the worktree (`node_modules`, `venv`, `.venv`, `vendor`, `target`, `.build`)
5. Copy task file into worktree root as `.local_task.md`
6. Run `opencode run` inside worktree directory
7. If `Test` header present, run the test command inside the worktree
8. Output structured JSON status to stdout
9. Clean up task file from project root

### Feedback loop (feedback file exists, worktree exists)

1. Parse slug from filename, locate worktree at `.git/worktrees_agents/<slug>`
2. Copy feedback file into worktree root as `.local_feedback.md`
3. Run `opencode run` inside worktree with feedback instructions
4. If `Test` header in original task was present, re-run the test gate
5. Output structured JSON status
6. Clean up feedback file from project root

### Cleanup mode

`bridge.sh --cleanup <slug>` removes the worktree via `git worktree remove`.

### Status mode

`bridge.sh --status` lists all active agent worktrees and their branch names.

## Structured Output

The bridge prints a JSON object as its last stdout line:

```json
{
  "status": "pass" | "fail" | "error",
  "branch": "feat/logger",
  "slug": "feat-logger",
  "worktree": ".git/worktrees_agents/feat-logger",
  "test_exit_code": 0,
  "test_command": "npm test -- --filter logger"
}
```

Claude parses this to decide whether to approve, send feedback, or report failure.

## Dependency Linking

The bridge auto-detects and symlinks these directories from the main worktree into the agent worktree (if they exist):

- `node_modules` (Node.js)
- `venv`, `.venv` (Python)
- `vendor` (Go, PHP, Ruby)
- `target` (Rust, Java/Maven)
- `.build` (Swift)

This avoids a full dependency install per worktree while keeping execution hermetic. The symlinks point to absolute paths in the main worktree.

## SKILL.md Updates

The skill manifest is updated to document:
- New file naming convention (`.local_task_<slug>.md`)
- Parallel dispatch pattern (multiple bridge calls)
- Feedback routing (`.local_feedback_<slug>.md`)
- Cleanup command (`--cleanup`)
- Status command (`--status`)
- Structured JSON output format

## Error Handling

- Missing task/feedback file for given slug → exit 1 with JSON `{"status": "error", "message": "..."}`
- `git worktree add` fails (branch exists) → attempt `git worktree add` using existing branch
- OpenCode not found → exit 1 with descriptive error
- Test gate fails → report `{"status": "fail", "test_exit_code": N}` but do NOT remove worktree (Claude may send feedback)

## Scope Exclusions

- No daemon/watcher mode — bridge is invoked per task
- No automatic merging — Claude decides when to merge branches
- No LM Studio health checks — assumes the server is running
- No multi-model routing — single OpenCode config applies
