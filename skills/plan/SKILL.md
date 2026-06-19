---
name: plan
description: Plan coding tasks by writing .local_task_*.md specification files from requirements. Use when the user wants to plan work for later delegation, or when breaking a complex feature into delegatable sub-tasks. Does NOT assign backends or models — use /code-delegate:distribute for that.
trigger: /code-delegate:plan
allowed-tools:
  - Bash
  - Read
  - Write
---

# Plan

Writes `.local_task_<slug>.md` specification files from requirements. No backend or model assignment — that is the distribute step's job.

## Slug Convention

Branch name with `/` replaced by `-`:
- `feat/logger` → slug `feat-logger` → file `.local_task_feat-logger.md`
- `fix/parse-error` → slug `fix-parse-error` → file `.local_task_fix-parse-error.md`

## Input Analysis

Accept requirements from: natural language, issue references, plan documents, or conversation context.

Steps:
- Break complex requirements into bounded sub-tasks
- Each sub-task must touch ≤2–3 files
- For each sub-task, determine: branch name, files to touch, test command (if applicable)
- If the user passes a branch slug or branch name as an argument, plan only that single sub-task
- If no argument, plan based on conversation context and requirements discussed

## Task File Writing

For each sub-task, write `.local_task_<slug>.md` in the project root.

**Required headers:**
- `Branch:` — the Git branch name to create
- `Files:` — comma-separated list of files the agent should touch

**Optional headers:**
- `Test:` — shell command to run as a test gate after implementation

**Leave `Backend:` and `Model:` EMPTY.** The distribute step assigns these.

**Body structure:**

```
## Objective
One sentence describing what this achieves.

## File Operations

### CREATE <path>
- Bullet describing what to build
- One bullet per requirement

### MODIFY <path>
- What to change and where
- Lines 14-28 are the target zone

## Constraints
- No changes outside listed files
- Must pass type checking
```

**Body guidelines:**
- Bullet points only, no prose paragraphs
- `CREATE` / `MODIFY` / `DELETE` verbs per file section
- Include line range hints for modifications
- Keep constraints explicit — scope creep is a common failure mode
- **NEVER write code blocks or function bodies.** Describe WHAT to build, not HOW. Say "add a `fetchUser(id:)` method that calls the `/users/:id` endpoint" — don't write the function.
- Keep constraints explicit — local models are prone to scope creep

See `/code-delegate:delegate` for the full task file format and header reference.

## Output

After writing all task files, print a summary table:

```
Planned tasks:
  .local_task_feat-foo.md  — feat/foo — brief description
  .local_task_feat-bar.md  — feat/bar — brief description
```

Then tell the user:

> Run `/code-delegate:distribute` to assign backends and models, or `/delegate` to plan + distribute + dispatch in one step.
