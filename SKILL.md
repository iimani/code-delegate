---
global: true
description: Delegate code implementation, heavy boilerplate generation, or bug fixes to a local OpenCode/LM Studio instance, using isolated Git worktrees for parallel execution.
---

# OpenCode Delegation Skill

This global skill allows Claude Code to act as a high-level Architect and Code Reviewer, offloading token-heavy coding tasks to a local OpenCode instance running on top of LM Studio. Each task runs in an isolated Git worktree, enabling parallel dispatch of multiple subagents.

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
- `Test:` (optional) — shell command to run as a test gate after implementation
- `Files:` (optional) — comma-separated list of files the agent should touch

**Body guidelines:**
- Use `CREATE` / `MODIFY` / `DELETE` verbs per file section
- Include line range hints for modifications (helps smaller models focus)
- Keep constraints explicit — local models are prone to scope creep
- Bullet points only, no prose paragraphs

## Execution Protocol

### Single task
1. **Plan**: Formulate your architectural plan and display it to the user.
2. **Write Spec**: Save instructions to `.local_task_<slug>.md` in the project root.
3. **Execute**: Run `~/.claude/skills/opencode-delegate/bridge.sh <slug>`
4. **Parse Output**: The last stdout line is a JSON status object.
5. **Review**: If `"status": "pass"`, review the changes with `git diff main..<branch>`.
6. **Fix Loop**: If issues found, write `.local_feedback_<slug>.md` and run the bridge again with the same slug.

### Parallel dispatch
Write multiple task files, then invoke the bridge in parallel:
```
~/.claude/skills/opencode-delegate/bridge.sh feat-logger
~/.claude/skills/opencode-delegate/bridge.sh feat-auth
~/.claude/skills/opencode-delegate/bridge.sh fix-parse-error
```
Each call creates its own worktree and runs independently.

### Feedback loop
Write `.local_feedback_<slug>.md` with the same `Branch:` header and specific fix instructions. The bridge routes it to the existing worktree for that slug.

### Cleanup
After approving and merging a branch:
```
~/.claude/skills/opencode-delegate/bridge.sh --cleanup <slug>
```

### Status check
List all active agent worktrees:
```
~/.claude/skills/opencode-delegate/bridge.sh --status
```

## JSON Status Output

The bridge prints a JSON object as its final stdout line:
```json
{
  "status": "pass | fail | error",
  "branch": "feat/logger",
  "slug": "feat-logger",
  "worktree": ".git/worktrees_agents/feat-logger",
  "test_exit_code": 0,
  "test_command": "npm test -- --filter logger",
  "message": ""
}
```

- `pass` — OpenCode finished and tests passed (or no test gate)
- `fail` — OpenCode finished but test gate failed; worktree preserved for feedback
- `error` — bridge-level failure (missing files, git errors, opencode crash)

## Notes
- Do not write massive blocks of code directly if this skill is available.
- Always use the exact path `~/.claude/skills/opencode-delegate/bridge.sh` to run the tool.
- Worktrees are stored in `.git/worktrees_agents/` — inside `.git/`, so invisible to the project.
- Dependencies (node_modules, venv, vendor, etc.) are auto-symlinked into worktrees.
