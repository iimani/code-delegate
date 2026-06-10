# Delegate Plugin Refactor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the single-backend `opencode-delegate` skill into a multi-backend `delegate` plugin with pluggable backends (opencode, claude, codex), proper plugin structure (`commands/`, `backends/`), and a thin dispatcher bridge.

**Architecture:** The bridge becomes a backend-agnostic dispatcher: it handles worktree setup, watcher, test gate, and cleanup, then calls `backends/<name>/run.sh` for execution. Each backend is self-contained with its own `run.sh` and `config.yaml`. The main command (`delegate`) handles distribution analysis and routing. Secondary commands (`delegate:status`, `delegate:backends`, `delegate:cleanup`) handle operations.

**Tech Stack:** Bash (bridge + backend runners), YAML (backend config), Markdown (skill/command files)

---

## File Structure

```
delegate/                          # project root (was opencode-delegate/)
├── commands/
│   └── delegate.md                # main command: distribution analysis + execution
├── skills/
│   ├── status.md                  # delegate:status — active worktrees + agent health
│   ├── backends.md                # delegate:backends — list backends + availability
│   └── cleanup.md                 # delegate:cleanup — remove worktree by slug
├── backends/
│   ├── opencode/
│   │   ├── run.sh                 # extracted from current bridge.sh — opencode-specific
│   │   └── config.yaml            # capabilities, models, availability check
│   ├── claude/
│   │   ├── run.sh                 # invokes `claude` CLI with spec
│   │   └── config.yaml
│   └── codex/
│       ├── run.sh                 # invokes `codex` CLI with spec
│       └── config.yaml
├── bridge.sh                      # thin dispatcher: worktree + watcher + backend routing
├── CLAUDE.md                      # project-level instructions (updated references)
├── README.md                      # updated
├── tests/
│   ├── bridge/
│   │   ├── test_dispatcher.sh     # unit tests for bridge dispatcher logic
│   │   └── test_backend_select.sh # unit tests for backend auto-selection
│   └── workflow/
│       ├── run.sh                 # updated scenario runner
│       ├── results/.gitignore
│       └── scenarios/             # existing + new scenarios
│           ├── 01-post-brainstorm-intercept.txt
│           ├── 02-multi-file-distribution.txt
│           ├── 03-security-sensitive-routing.txt
│           ├── 04-trivial-task-bypass.txt
│           ├── 05-no-prose-spec.txt
│           ├── 06-larger-model-routing.txt
│           ├── 07-abort-per-task-not-global.txt
│           ├── 08-backend-header-routing.txt      # NEW
│           ├── 09-backend-auto-selection.txt       # NEW
│           └── 10-backend-unavailable-fallback.txt # NEW
└── LICENSE
```

---

### Task 1: Extract backend-agnostic dispatcher from bridge.sh

This task splits the current monolithic `bridge.sh` into a thin dispatcher (bridge.sh) and a backend-specific runner (backends/opencode/run.sh). No new backends yet — just the separation.

**Files:**
- Modify: `bridge.sh` (gut the opencode-specific parts, add backend routing)
- Create: `backends/opencode/run.sh` (the extracted opencode execution logic)
- Create: `backends/opencode/config.yaml` (capabilities metadata)

- [ ] **Step 1: Write the backend config schema**

Create `backends/opencode/config.yaml`:

```yaml
name: opencode
description: Local AI coding agent via OpenCode CLI (LM Studio, Ollama, etc.)
check_command: command -v opencode
default_model: ""
models:
  - pattern: "*"
    description: "Any model configured in OpenCode (use provider/model format)"
capabilities:
  - single-file
  - boilerplate
  - test-generation
  - crud
tags:
  security_ok: false
  cross_file: false
  type_reasoning: false
cost_tier: free
```

- [ ] **Step 2: Extract the opencode runner**

Create `backends/opencode/run.sh`. This receives exactly 4 arguments from the dispatcher:
1. `$1` — worktree path
2. `$2` — spec file path (already copied into worktree)
3. `$3` — model string (from `Model:` header, may be empty)
4. `$4` — mode ("task" or "feedback")

It must:
- Build the opencode command with preamble
- `exec` the opencode process (the dispatcher handles backgrounding and watcher)
- Exit with opencode's exit code

The preamble and command construction come from the current `bridge.sh` lines 279-306.

```bash
#!/bin/bash
set -euo pipefail

WORKTREE_PATH="$1"
SPEC_FILE="$2"
MODEL="$3"
MODE="$4"

PREAMBLE='<agent-role>
You are a direct code implementation agent dispatched by Claude Code. Your ONLY job is to implement the spec below.

Rules:
- Do NOT invoke any skills or load any skill frameworks
- Do NOT fetch external URLs
- Do NOT write plans, specs, or analysis documents
- Do NOT ask clarifying questions — the spec is authoritative

Workflow: read files → make changes → build/test → fix errors → repeat until the test gate passes or the spec is fully implemented.
</agent-role>'

TASK_CONTENT="$(cat "$SPEC_FILE")"

if [ "$MODE" = "feedback" ]; then
    PROMPT_TEXT="${PREAMBLE}"$'\n\n'"Apply the following fixes directly in this workspace:"$'\n\n'"${TASK_CONTENT}"
else
    PROMPT_TEXT="${PREAMBLE}"$'\n\n'"Implement the following spec directly in this workspace:"$'\n\n'"${TASK_CONTENT}"
fi

CMD=(opencode run --dangerously-skip-permissions --pure)
if [ -n "$MODEL" ]; then
    CMD+=(--model "$MODEL")
fi

cd "$WORKTREE_PATH"
exec "${CMD[@]}" "$PROMPT_TEXT"
```

- [ ] **Step 3: Refactor bridge.sh into a dispatcher**

Replace the opencode-specific execution in `bridge.sh` with a generic backend routing mechanism:

1. Add a `parse_header` call for `Backend:` (default: `opencode`)
2. Add a `resolve_backend()` function that:
   - Reads `Backend:` header from the task file
   - Falls back to `opencode` if empty
   - Validates that `backends/<name>/run.sh` exists
   - Returns the backend name
3. Replace the opencode invocation block (lines 274-306) with:

```bash
BACKEND="$(resolve_backend "$INSTRUCTION_FILE")"
BACKEND_DIR="$(dirname "$0")/backends/${BACKEND}"
BACKEND_RUNNER="${BACKEND_DIR}/run.sh"

[ -f "$BACKEND_RUNNER" ] || die "Backend runner not found: $BACKEND_RUNNER"
[ -x "$BACKEND_RUNNER" ] || chmod +x "$BACKEND_RUNNER"

# Spec file is already copied into worktree as .local_task.md or .local_feedback.md
SPEC_IN_WORKTREE="${WORKTREE_PATH}/.local_${MODE}.md"

OPENCODE_EXIT=0
(
    exec "$BACKEND_RUNNER" "$WORKTREE_PATH" "$SPEC_IN_WORKTREE" "$MODEL" "$MODE"
) >> "$LOG_FILE" 2>&1 &
OC_PID=$!
```

4. Replace the `no_opencode` check (lines 193-196) with a generic backend availability check:

```bash
check_backend_available() {
    local backend="$1"
    local config="${BACKEND_DIR}/config.yaml"
    if [ -f "$config" ]; then
        local check_cmd
        check_cmd="$(grep '^check_command:' "$config" | sed 's/^check_command:[[:space:]]*//')"
        if [ -n "$check_cmd" ] && ! eval "$check_cmd" >/dev/null 2>&1; then
            json_output "no_backend" "" "$SLUG" "" "" "" "${backend} CLI not found"
            exit 10
        fi
    fi
}
```

5. Keep ALL of: worktree creation, dependency linking, watcher, test gate, cleanup, status, logs. These are backend-agnostic.

- [ ] **Step 4: Run existing tests to verify no regression**

Run: `cd /Users/ismail/Documents/workspace/opencode-delegate && bash tests/workflow/run.sh`

Expected: All 7 existing scenarios pass. The bridge changes are structural — the opencode backend should behave identically.

- [ ] **Step 5: Commit**

```bash
git add bridge.sh backends/opencode/run.sh backends/opencode/config.yaml
git commit -m "refactor: extract opencode backend from bridge dispatcher"
```

---

### Task 2: Create the Claude backend

**Files:**
- Create: `backends/claude/run.sh`
- Create: `backends/claude/config.yaml`

- [ ] **Step 1: Write the Claude backend config**

Create `backends/claude/config.yaml`:

```yaml
name: claude
description: Claude Code CLI subagent (Anthropic API)
check_command: command -v claude
default_model: sonnet
models:
  - name: opus
    description: "Claude Opus — highest capability, cross-file reasoning, type systems"
  - name: sonnet
    description: "Claude Sonnet — fast, good for bounded tasks"
  - name: haiku
    description: "Claude Haiku — fastest, good for boilerplate and simple tasks"
capabilities:
  - single-file
  - cross-file
  - type-reasoning
  - boilerplate
  - test-generation
  - crud
tags:
  security_ok: false
  cross_file: true
  type_reasoning: true
cost_tier: paid
```

Note: `security_ok` stays false — the SKILL.md hard rule says security code is never delegated regardless of backend.

- [ ] **Step 2: Write the Claude backend runner**

Create `backends/claude/run.sh`:

```bash
#!/bin/bash
set -euo pipefail

WORKTREE_PATH="$1"
SPEC_FILE="$2"
MODEL="$3"
MODE="$4"

TASK_CONTENT="$(cat "$SPEC_FILE")"

if [ "$MODE" = "feedback" ]; then
    PROMPT_TEXT="Apply the following fixes directly in this workspace:"$'\n\n'"${TASK_CONTENT}"
else
    PROMPT_TEXT="Implement the following spec directly in this workspace:"$'\n\n'"${TASK_CONTENT}"
fi

CMD=(claude --dangerously-skip-permissions --print --verbose)
if [ -n "$MODEL" ]; then
    CMD+=(--model "$MODEL")
fi

cd "$WORKTREE_PATH"
exec "${CMD[@]}" "$PROMPT_TEXT"
```

Key differences from opencode runner:
- Uses `claude` CLI, not `opencode`
- Uses `--print` and `--verbose` flags (claude CLI convention)
- Uses `--dangerously-skip-permissions` for autonomous operation
- Model names are bare (`sonnet`, `opus`) not provider-prefixed
- No custom preamble needed — Claude Code already knows how to implement specs

- [ ] **Step 3: Make runner executable and test availability check**

```bash
chmod +x backends/claude/run.sh
# Verify the config parses correctly:
grep 'check_command' backends/claude/config.yaml
# Verify claude CLI is available:
command -v claude && echo "OK" || echo "NOT FOUND"
```

- [ ] **Step 4: Commit**

```bash
git add backends/claude/run.sh backends/claude/config.yaml
git commit -m "feat: add Claude backend for delegate plugin"
```

---

### Task 3: Create the Codex backend

**Files:**
- Create: `backends/codex/run.sh`
- Create: `backends/codex/config.yaml`

- [ ] **Step 1: Write the Codex backend config**

Create `backends/codex/config.yaml`:

```yaml
name: codex
description: OpenAI Codex CLI agent
check_command: command -v codex
default_model: ""
models:
  - pattern: "*"
    description: "Any model supported by Codex CLI"
capabilities:
  - single-file
  - boilerplate
  - test-generation
  - crud
tags:
  security_ok: false
  cross_file: false
  type_reasoning: false
cost_tier: paid
```

- [ ] **Step 2: Write the Codex backend runner**

Create `backends/codex/run.sh`:

```bash
#!/bin/bash
set -euo pipefail

WORKTREE_PATH="$1"
SPEC_FILE="$2"
MODEL="$3"
MODE="$4"

TASK_CONTENT="$(cat "$SPEC_FILE")"

if [ "$MODE" = "feedback" ]; then
    PROMPT_TEXT="Apply the following fixes directly in this workspace:"$'\n\n'"${TASK_CONTENT}"
else
    PROMPT_TEXT="Implement the following spec directly in this workspace:"$'\n\n'"${TASK_CONTENT}"
fi

CMD=(codex --quiet --full-auto)
if [ -n "$MODEL" ]; then
    CMD+=(--model "$MODEL")
fi

cd "$WORKTREE_PATH"
exec "${CMD[@]}" "$PROMPT_TEXT"
```

- [ ] **Step 3: Commit**

```bash
git add backends/codex/run.sh backends/codex/config.yaml
git commit -m "feat: add Codex backend for delegate plugin"
```

---

### Task 4: Rename project and restructure as a plugin

This task renames from `opencode-delegate` to `delegate`, moves `SKILL.md` into `commands/delegate.md`, and creates the secondary skill commands.

**Files:**
- Rename: `SKILL.md` → `commands/delegate.md` (with frontmatter changes)
- Create: `skills/status.md`
- Create: `skills/backends.md`
- Create: `skills/cleanup.md`
- Modify: `CLAUDE.md` (update all references)
- Modify: `README.md` (update name and structure docs)

- [ ] **Step 1: Create commands/delegate.md from SKILL.md**

Move `SKILL.md` content into `commands/delegate.md`. Update the frontmatter:

```yaml
---
description: Delegate code implementation to local or cloud AI agents using isolated Git worktrees for parallel execution.
argument-hint: Optional task description or plan reference
---
```

In the body, make these changes:
1. Replace all references to "OpenCode" as the sole backend with generic "delegate" language
2. Replace `~/.claude/skills/opencode-delegate/bridge.sh` with `~/.claude/plugins/data/delegate/bridge.sh` throughout (this is where installed plugins store runtime data — but actually the bridge ships with the plugin, so use a relative reference `$PLUGIN_DIR/bridge.sh` in the skill text, where `$PLUGIN_DIR` is resolved at invocation)
3. Add a `Backend:` header to the task file format documentation:
   - `Backend:` (optional) — which backend to use: `opencode`, `claude`, `codex`, or `auto` (default: `auto`)
4. Update the Distribution Analysis section to reference backend capabilities from config.yaml rather than hardcoded opencode assumptions:
   - "Delegate to OpenCode when" → "Delegate when" (backend-agnostic criteria)
   - "Implement directly (Claude) when" stays as-is (this is about Claude-the-orchestrator, not claude-the-backend)
   - Add: "When `Backend: auto`, the bridge reads `config.yaml` capabilities to pick the best available backend"
5. Update execution protocol paths from `~/.claude/skills/opencode-delegate/bridge.sh` to just `bridge.sh` (the skill knows its own install path)
6. Remove the "OpenCode Not Available" section — replace with a generic "Backend Not Available (Exit Code 10)" section that works for any backend

- [ ] **Step 2: Create skills/status.md**

```markdown
---
name: status
description: Show active delegate agent worktrees, their backends, branches, and last log line
---

# Delegate Status

Show the user what delegate agents are currently running or have completed.

Run: `bridge.sh --status`

This lists all worktrees under `.git/worktrees_agents/`, showing:
- Slug and branch name
- Which backend was used (read from `.bridge_backend` marker file in worktree)
- Last line of the agent log
- Whether the agent is still running (check if PID in `.bridge_pid` is alive)

Present the output in a clean table format to the user.
```

- [ ] **Step 3: Create skills/backends.md**

```markdown
---
name: backends
description: List installed delegate backends, their availability, models, and capabilities
---

# Delegate Backends

List all available delegation backends and their status.

For each directory in `backends/`:
1. Read `config.yaml`
2. Run the `check_command` to test availability
3. Report: name, description, available (yes/no), models, capabilities, cost tier

Present as a formatted table:

| Backend  | Available | Cost | Capabilities                     |
|----------|-----------|------|----------------------------------|
| opencode | yes       | free | single-file, boilerplate, crud   |
| claude   | yes       | paid | cross-file, type-reasoning, ...  |
| codex    | no        | paid | single-file, boilerplate         |

If a backend is unavailable, show what command is missing.
```

- [ ] **Step 4: Create skills/cleanup.md**

```markdown
---
name: cleanup
description: Remove a delegate agent worktree after its branch has been approved/merged
argument-hint: <slug> — the branch slug to clean up
---

# Delegate Cleanup

Remove an agent worktree after its branch has been reviewed and merged.

Usage: The user provides a slug (e.g., `feat-logger`).

Run: `bridge.sh --cleanup <slug>`

Before running cleanup:
1. Check if the branch has been merged into main: `git branch --merged main | grep <branch>`
2. If not merged, warn the user and ask for confirmation before removing
3. If merged, proceed with cleanup

After cleanup, confirm removal to the user.
```

- [ ] **Step 5: Update CLAUDE.md references**

Replace all occurrences of `opencode-delegate` with `delegate` in `CLAUDE.md`. Update the skill invocation instruction:

```markdown
Invoke via: `Skill tool → skill: "delegate"`
```

Update the "When NOT to delegate" section — no changes needed, it's backend-agnostic.

Update the bridge path references.

- [ ] **Step 6: Delete the old SKILL.md**

```bash
rm SKILL.md
```

- [ ] **Step 7: Commit**

```bash
git add commands/delegate.md skills/status.md skills/backends.md skills/cleanup.md CLAUDE.md
git rm SKILL.md
git commit -m "refactor: restructure as delegate plugin with commands and skills"
```

---

### Task 5: Add `Backend:` header routing + auto-selection to bridge

**Files:**
- Modify: `bridge.sh` (add auto-selection logic)

- [ ] **Step 1: Add the auto-select function to bridge.sh**

Add `auto_select_backend()` after the `resolve_backend()` function:

```bash
auto_select_backend() {
    local instruction_file="$1"
    local skill_dir
    skill_dir="$(dirname "$0")"

    # Read task capabilities needed (simple heuristic from Files: header)
    local files_header
    files_header="$(parse_header "$instruction_file" "Files")"
    local file_count=1
    if [ -n "$files_header" ]; then
        file_count=$(echo "$files_header" | tr ',' '\n' | wc -l | tr -d ' ')
    fi

    # Try each backend in preference order: opencode (free) → claude → codex
    for backend in opencode claude codex; do
        local config="${skill_dir}/backends/${backend}/config.yaml"
        [ -f "$config" ] || continue

        # Check availability
        local check_cmd
        check_cmd="$(grep '^check_command:' "$config" | sed 's/^check_command:[[:space:]]*//')"
        if [ -n "$check_cmd" ] && ! eval "$check_cmd" >/dev/null 2>&1; then
            continue
        fi

        # If multi-file task, skip backends without cross_file capability
        if [ "$file_count" -gt 3 ]; then
            if grep -q 'cross_file: false' "$config"; then
                continue
            fi
        fi

        echo "$backend"
        return 0
    done

    # Nothing available
    echo ""
    return 1
}
```

Update `resolve_backend()`:

```bash
resolve_backend() {
    local instruction_file="$1"
    local backend
    backend="$(parse_header "$instruction_file" "Backend")"

    if [ -z "$backend" ] || [ "$backend" = "auto" ]; then
        backend="$(auto_select_backend "$instruction_file")"
        if [ -z "$backend" ]; then
            die "No available backend found. Run 'bridge.sh --backends' to check."
            return 1
        fi
        echo "Auto-selected backend: $backend" >&2
    fi

    echo "$backend"
}
```

- [ ] **Step 2: Add a --backends flag to bridge.sh**

Add this block near the other flag handlers (after `--logs`):

```bash
if [ "${1:-}" = "--backends" ]; then
    skill_dir="$(dirname "$0")"
    echo "Installed backends:"
    for config in "$skill_dir"/backends/*/config.yaml; do
        [ -f "$config" ] || continue
        local dir name check_cmd available
        dir="$(dirname "$config")"
        name="$(basename "$dir")"
        check_cmd="$(grep '^check_command:' "$config" | sed 's/^check_command:[[:space:]]*//')"
        if [ -n "$check_cmd" ] && eval "$check_cmd" >/dev/null 2>&1; then
            available="YES"
        else
            available="NO"
        fi
        desc="$(grep '^description:' "$config" | sed 's/^description:[[:space:]]*//')"
        echo "  $name ($available) — $desc"
    done
    exit 0
fi
```

- [ ] **Step 3: Write a backend marker into worktrees**

After backend resolution in the main flow, write a marker so `--status` can report which backend was used:

```bash
echo "$BACKEND" > "${WORKTREE_PATH}/.bridge_backend"
```

And in `handle_status()`, read it:

```bash
backend=""
if [ -f "${dir}.bridge_backend" ]; then
    backend=" [$(cat "${dir}.bridge_backend")]"
fi
echo "  $slug -> $branch$backend$last_log"
```

- [ ] **Step 4: Commit**

```bash
git add bridge.sh
git commit -m "feat: add Backend: header routing and auto-selection to bridge"
```

---

### Task 6: Update workflow tests for multi-backend support

**Files:**
- Modify: `tests/workflow/run.sh` (update skill install path)
- Create: `tests/workflow/scenarios/08-backend-header-routing.txt`
- Create: `tests/workflow/scenarios/09-backend-auto-selection.txt`
- Create: `tests/workflow/scenarios/10-backend-unavailable-fallback.txt`

- [ ] **Step 1: Update test runner paths**

In `tests/workflow/run.sh`, change:
- `SKILL_DEST="$HOME/.claude/skills/opencode-delegate"` → `SKILL_DEST="$HOME/.claude/skills/delegate"`
- Update the CLAUDE.md installation logic to reference `delegate` instead of `opencode-delegate`

- [ ] **Step 2: Create scenario 08 — backend header routing**

Create `tests/workflow/scenarios/08-backend-header-routing.txt`:

```
DESCRIPTION: Task with explicit Backend: header should mention that backend in distribution
PROMPT: You are in a Node.js project. Implement a simple YAML config reader in src/config.ts. Use Backend: claude for this task.
EXPECT: claude
EXPECT: DELEGATE
FORBID: ```typescript
FORBID: import {
```

- [ ] **Step 3: Create scenario 09 — backend auto-selection**

Create `tests/workflow/scenarios/09-backend-auto-selection.txt`:

```
DESCRIPTION: Task without explicit backend should auto-select and show the chosen backend
PROMPT: You are in a Node.js project. Implement a JSON logger in src/logger.ts. This is a single-file boilerplate task.
EXPECT: DELEGATE
FORBID: ```typescript
FORBID: import {
```

- [ ] **Step 4: Create scenario 10 — backend unavailable fallback**

Create `tests/workflow/scenarios/10-backend-unavailable-fallback.txt`:

```
DESCRIPTION: Distribution analysis should note when a backend is unavailable
PROMPT: You are in a Node.js project. Implement a REST client in src/api.ts. Use Backend: codex for this. Note that codex CLI is not installed on this machine.
EXPECT: DELEGATE
FORBID: ```typescript
```

- [ ] **Step 5: Run all tests**

Run: `cd /Users/ismail/Documents/workspace/opencode-delegate && bash tests/workflow/run.sh`

Expected: All 10 scenarios pass.

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "test: add multi-backend workflow scenarios"
```

---

### Task 7: Update README and global CLAUDE.md references

**Files:**
- Modify: `README.md`
- Modify: `~/.claude/CLAUDE.md` (global — update references from `opencode-delegate` to `delegate`)

- [ ] **Step 1: Update README.md**

Rewrite the README to reflect the new plugin structure:
- Name: `delegate` (not `opencode-delegate`)
- Describe the multi-backend architecture
- List available backends with their capabilities
- Show the task file format with `Backend:` header
- Document commands: `delegate`, `delegate:status`, `delegate:backends`, `delegate:cleanup`
- Show the directory structure
- Update installation instructions

- [ ] **Step 2: Update global CLAUDE.md**

In `~/.claude/CLAUDE.md`, replace all `opencode-delegate` references with `delegate`:
- `invoke the \`opencode-delegate\` skill` → `invoke the \`delegate\` skill`
- `Invoke via: \`Skill tool → skill: "opencode-delegate"\`` → `Invoke via: \`Skill tool → skill: "delegate"\``
- Table entries: `opencode-delegate` → `delegate`

- [ ] **Step 3: Delete TODO.md (roadmap is now implemented)**

The TODO.md contains the multi-delegate roadmap which this refactor implements. Remove it.

```bash
git rm TODO.md
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README and references for delegate plugin rename"
```

The global `~/.claude/CLAUDE.md` change is not committed (it's outside the repo).

---

### Task 8: Reinstall skill under new name

This is a manual/operational step, not code. After all commits:

- [ ] **Step 1: Remove old skill symlink/copy**

```bash
rm -rf ~/.claude/skills/opencode-delegate
```

- [ ] **Step 2: Install under new name**

```bash
cp -r /Users/ismail/Documents/workspace/opencode-delegate ~/.claude/skills/delegate
```

Or create a symlink for development:

```bash
ln -s /Users/ismail/Documents/workspace/opencode-delegate ~/.claude/skills/delegate
```

- [ ] **Step 3: Verify skill is discovered**

Start a new Claude Code session and verify `delegate` appears in the skill list.

- [ ] **Step 4: Run a smoke test**

```
/delegate — ask it to implement a trivial task and verify it routes correctly
```
