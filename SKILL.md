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
- `Model:` (optional) — provider/model to use (e.g., `lmstudio/qwen/qwen3.5-9b`)
- `Test:` (optional) — shell command to run as a test gate after implementation
- `Files:` (optional) — comma-separated list of files the agent should touch
- `Timeout:` (optional) — wall-clock kill limit in seconds (default: 3600 = 60 min)
- `MaxFails:` (optional) — abort after this many failure-pattern matches in the log (default: 8; set to 0 to disable)
- `FailPattern:` (optional) — ERE pattern counted as one failure hit (default: `build commands failed|compilation error|FAILED|npm ERR!`)

**Model selection guidance:**
Small models (≤9B) handle single-file, well-scoped tasks reliably. For tasks involving complex type systems (Swift concurrency, TypeScript generics), cross-file refactors, or multi-step build feedback loops, set `Model:` to a larger local model or route to Claude via API. If the task requires reasoning about compiler error chains, a 9B model is likely to doom-loop — lower `MaxFails:` to 5 so failures surface faster.

**Body guidelines:**
- Use `CREATE` / `MODIFY` / `DELETE` verbs per file section
- Include line range hints for modifications (helps smaller models focus)
- Keep constraints explicit — local models are prone to scope creep
- Bullet points only, no prose paragraphs
- **NEVER write code blocks or function bodies in the spec.** Describe WHAT to build, not HOW. The delegate writes the code — that's the whole point. If you're pasting Swift/TypeScript/Python into the task file, you're doing the delegate's job and wasting tokens twice. Say "add a `calendar(start:end:)` method that fetches from the `/calendar` endpoint with ISO8601 date query params" — don't write the function.

## Execution Protocol

### Single task
1. **Plan**: Formulate your architectural plan and display it to the user.
2. **Write Spec**: Save instructions to `.local_task_<slug>.md` in the project root.
3. **Execute**: Run `~/.claude/skills/opencode-delegate/bridge.sh <slug>`
4. **Parse Output**: The last stdout line is a JSON status object.
5. **Review**: If `"status": "pass"`, review the changes with `git diff main..<branch>`.
6. **Fix Loop**: If issues found, write `.local_feedback_<slug>.md` and run the bridge again with the same slug.

### Parallel dispatch
Write multiple task files, then invoke the bridge in parallel using `run_in_background: true`:
```
# Launch all tasks in background
~/.claude/skills/opencode-delegate/bridge.sh feat-logger    # run_in_background: true
~/.claude/skills/opencode-delegate/bridge.sh feat-auth      # run_in_background: true
~/.claude/skills/opencode-delegate/bridge.sh fix-parse-error # run_in_background: true
```
Each call creates its own worktree and runs independently. You will be notified as each completes.

### Monitoring progress
While agents are running in the background, check progress with:
```
~/.claude/skills/opencode-delegate/bridge.sh --logs              # tail all agents
~/.claude/skills/opencode-delegate/bridge.sh --logs <slug>       # full log for one agent
```
Each agent writes a live log to `.git/worktrees_agents/<slug>/opencode.log`. Use `--logs` to give the user progress updates when they ask or when waiting for background tasks to finish.

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
- `aborted` — watcher killed the agent due to timeout, stall, or failure loop; `message` contains the reason

## OpenCode Not Available (Exit Code 10)

If the bridge exits with code 10 and `"status": "no_opencode"`, it means the `opencode` CLI is not installed on this machine. When this happens:

1. **Tell the user** that OpenCode is not available and the task cannot be delegated locally.
2. **Ask the user**: "OpenCode isn't installed on this machine. Should I implement this myself instead?"
3. If the user agrees, **read the task file you already wrote** (`.local_task_<slug>.md`) and implement it directly using your own tools. The spec format is designed to be readable by you as well.
4. Clean up the task file after implementation.

Do NOT silently fall back — always ask first. The user may prefer to install OpenCode or defer the task.

## OpenCode Produced No Changes (Status "pass" But No Diff)

If the bridge reports `"status": "pass"` but `git diff` in the worktree shows no changes, OpenCode ran but failed to implement anything. This is a silent failure. When this happens:

1. **Tell the user** that OpenCode completed without making any code changes.
2. **Ask the user**: "OpenCode didn't produce any changes. Should I implement this myself, or would you like to retry the delegation?"
3. **Do NOT implement the changes yourself without asking.** Always wait for the user's explicit approval.
4. If the user says to proceed, read the task spec and implement it directly.

This rule applies to ALL fallback scenarios — never silently take over implementation from the delegate.

## Agent Aborted (Status "aborted")

If the bridge returns `"status": "aborted"`, the watcher killed the agent due to a timeout, stall, or failure loop. The worktree is preserved with whatever partial work the agent completed. When this happens:

1. **Tell the user** what happened, including the abort reason from `message` (e.g. "loop: 8 failures matching 'build commands failed'").
2. **Inspect the partial work**: run `git diff main..<branch>` in the worktree to see what the agent managed to produce before being killed.
3. **Take over directly** — do not ask, do not re-delegate. Read the original task spec (`.local_task_<slug>.md` still exists) and the partial diff, then implement the remaining work yourself using your own tools. The agent's partial changes may be usable as a starting point or may need to be reverted first — read the diff and decide.
4. After completing the implementation, run the test gate manually to verify, then clean up: `bridge.sh --cleanup <slug>`.

The rationale: if a local model doom-looped on a task, re-delegating will produce the same result. Take over and finish it.

## Notes
- Do not write massive blocks of code directly if this skill is available.
- Always use the exact path `~/.claude/skills/opencode-delegate/bridge.sh` to run the tool.
- Worktrees are stored in `.git/worktrees_agents/` — inside `.git/`, so invisible to the project.
- Dependencies (node_modules, venv, vendor, etc.) are auto-symlinked into worktrees.
