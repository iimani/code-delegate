#!/bin/bash
# ~/.claude/skills/opencode-delegate/bridge.sh
# Parallel worktree execution bridge for the opencode-delegate skill
#
# Usage:
#   bridge.sh <slug>              Run task or feedback for the given branch slug
#   bridge.sh --status            List active agent worktrees
#   bridge.sh --cleanup <slug>    Remove a worktree after branch is approved
#   bridge.sh --logs [slug]       Tail logs for one or all running agents

set -euo pipefail

AGENTS_DIR=".git/worktrees_agents"
DEP_DIRS=("node_modules" "venv" ".venv" "vendor" "target" ".build")

DEFAULT_WALL_TIMEOUT=3600   # 60 minutes
DEFAULT_MAX_FAILS=8         # abort after this many detected failure pattern matches
DEFAULT_FAIL_PATTERN="build commands failed|compilation error|FAILED|npm ERR!"
STALL_SECONDS=180           # kill if log has no new bytes for this many seconds

json_output() {
    local status="$1" branch="${2:-}" slug="${3:-}" worktree="${4:-}" test_exit="${5:-}" test_cmd="${6:-}" msg="${7:-}"
    printf '{"status":"%s","branch":"%s","slug":"%s","worktree":"%s","test_exit_code":%s,"test_command":"%s","message":"%s"}\n' \
        "$status" "$branch" "$slug" "$worktree" "${test_exit:-null}" "$test_cmd" "$msg"
}

die() {
    json_output "error" "" "${SLUG:-}" "" "" "" "$1"
    exit 1
}

parse_header() {
    local file="$1" key="$2"
    grep -m1 "^${key}:" "$file" 2>/dev/null | sed "s/^${key}:[[:space:]]*//" || true
}

link_dependencies() {
    local worktree_path="$1"
    local main_root
    main_root="$(git rev-parse --show-toplevel)"
    for dep in "${DEP_DIRS[@]}"; do
        if [ -e "${main_root}/${dep}" ] && [ ! -e "${worktree_path}/${dep}" ]; then
            ln -s "${main_root}/${dep}" "${worktree_path}/${dep}"
            echo "  Linked ${dep}"
        fi
    done
}

handle_status() {
    if [ ! -d "$AGENTS_DIR" ]; then
        echo "No active agent worktrees."
        exit 0
    fi
    echo "Active agent worktrees:"
    for dir in "$AGENTS_DIR"/*/; do
        [ -d "$dir" ] || continue
        local slug branch last_log
        slug="$(basename "$dir")"
        branch="$(git -C "$dir" branch --show-current 2>/dev/null || echo "unknown")"
        last_log=""
        if [ -f "${dir}opencode.log" ]; then
            last_log=" | $(tail -1 "${dir}opencode.log")"
        fi
        echo "  $slug -> $branch$last_log"
    done
    exit 0
}

handle_cleanup() {
    local slug="$1"
    local worktree_path="${AGENTS_DIR}/${slug}"
    if [ ! -d "$worktree_path" ]; then
        echo "No worktree found for slug: $slug"
        exit 1
    fi
    git worktree remove "$worktree_path" --force
    echo "Removed worktree for $slug"
    exit 0
}

run_test_gate() {
    local worktree_path="$1" test_cmd="$2"
    if [ -z "$test_cmd" ]; then
        return 0
    fi
    echo "Running test gate: $test_cmd"
    local test_exit=0
    (cd "$worktree_path" && eval "$test_cmd") || test_exit=$?
    TEST_EXIT_CODE=$test_exit
    return $test_exit
}

# Monitors an opencode process for stalls, failure loops, and wall-clock timeout.
# Kills $pid and writes a reason to $abort_file if any limit is triggered.
start_watcher() {
    local pid="$1" log="$2" wall_timeout="$3" max_fails="$4" fail_pattern="$5" abort_file="$6"
    (
        elapsed=0
        last_size=0
        stall_elapsed=0
        while kill -0 "$pid" 2>/dev/null; do
            sleep 30
            elapsed=$((elapsed + 30))

            # Wall-clock timeout
            if [ "$elapsed" -ge "$wall_timeout" ]; then
                echo "[BRIDGE] $(date '+%H:%M:%S') Timeout: wall-clock limit ${wall_timeout}s reached" >> "$log"
                echo "timeout after ${wall_timeout}s" > "$abort_file"
                kill "$pid" 2>/dev/null || true
                break
            fi

            # Stall detection — no log growth
            cur_size=$(wc -c < "$log" 2>/dev/null | tr -d ' ' || echo 0)
            if [ "$cur_size" -eq "$last_size" ]; then
                stall_elapsed=$((stall_elapsed + 30))
                if [ "$stall_elapsed" -ge "$STALL_SECONDS" ]; then
                    echo "[BRIDGE] $(date '+%H:%M:%S') Stall: no log activity for ${STALL_SECONDS}s" >> "$log"
                    echo "stall: no activity for ${STALL_SECONDS}s" > "$abort_file"
                    kill "$pid" 2>/dev/null || true
                    break
                fi
            else
                stall_elapsed=0
                last_size=$cur_size
            fi

            # Failure loop detection
            if [ -n "$fail_pattern" ] && [ "$max_fails" -gt 0 ]; then
                fail_count=$(grep -cE "$fail_pattern" "$log" 2>/dev/null || echo 0)
                if [ "$fail_count" -ge "$max_fails" ]; then
                    echo "[BRIDGE] $(date '+%H:%M:%S') Loop: $fail_count failures detected (limit $max_fails)" >> "$log"
                    echo "loop: $fail_count failures matching '${fail_pattern}'" > "$abort_file"
                    kill "$pid" 2>/dev/null || true
                    break
                fi
            fi
        done
    ) &
    echo $!
}

# --- Main ---

if [ "${1:-}" = "--status" ]; then
    handle_status
fi

if [ "${1:-}" = "--cleanup" ]; then
    [ -n "${2:-}" ] || die "--cleanup requires a slug argument"
    handle_cleanup "$2"
fi

if [ "${1:-}" = "--logs" ]; then
    slug="${2:-}"
    if [ -n "$slug" ]; then
        log="${AGENTS_DIR}/${slug}/opencode.log"
        if [ -f "$log" ]; then
            cat "$log"
        else
            echo "No log found for slug: $slug"
        fi
    else
        for log in "$AGENTS_DIR"/*/opencode.log; do
            [ -f "$log" ] || continue
            slug="$(basename "$(dirname "$log")")"
            echo "=== $slug ==="
            tail -20 "$log"
            echo ""
        done
    fi
    exit 0
fi

if [ "${1:-}" = "--list-models" ]; then
    echo "Available Opencode models:"
    opencode models 2>/dev/null || echo "(failed to list models)"
    exit 0
fi

SLUG="${1:-}"
[ -n "$SLUG" ] || die "Usage: bridge.sh <slug> | --status | --cleanup <slug> | --logs [slug]"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    die "Not inside a Git repository"
fi

if ! command -v opencode >/dev/null 2>&1; then
    json_output "no_opencode" "" "$SLUG" "" "" "" "opencode CLI not found -- Claude should prompt user to proceed directly"
    exit 10
fi

TASK_FILE=".local_task_${SLUG}.md"
FEEDBACK_FILE=".local_feedback_${SLUG}.md"
WORKTREE_PATH="${AGENTS_DIR}/${SLUG}"
TEST_EXIT_CODE=""

MODE=""
INSTRUCTION_FILE=""
if [ -f "$FEEDBACK_FILE" ]; then
    MODE="feedback"
    INSTRUCTION_FILE="$FEEDBACK_FILE"
    echo "Processing feedback for $SLUG..."
elif [ -f "$TASK_FILE" ]; then
    MODE="task"
    INSTRUCTION_FILE="$TASK_FILE"
    echo "Processing new task for $SLUG..."
else
    die "Neither $TASK_FILE nor $FEEDBACK_FILE found"
fi

BRANCH="$(parse_header "$INSTRUCTION_FILE" "Branch")"
MODEL="$(parse_header "$INSTRUCTION_FILE" "Model")"
TEST_CMD="$(parse_header "$INSTRUCTION_FILE" "Test")"
FILES="$(parse_header "$INSTRUCTION_FILE" "Files")"
WALL_TIMEOUT="$(parse_header "$INSTRUCTION_FILE" "Timeout")"
MAX_FAILS="$(parse_header "$INSTRUCTION_FILE" "MaxFails")"
FAIL_PATTERN="$(parse_header "$INSTRUCTION_FILE" "FailPattern")"

WALL_TIMEOUT="${WALL_TIMEOUT:-$DEFAULT_WALL_TIMEOUT}"
MAX_FAILS="${MAX_FAILS:-$DEFAULT_MAX_FAILS}"
FAIL_PATTERN="${FAIL_PATTERN:-$DEFAULT_FAIL_PATTERN}"

[ -n "$BRANCH" ] || die "No Branch: header found in $INSTRUCTION_FILE"

if [ -n "$MODEL" ] && ! echo "$MODEL" | grep -qE '/'; then
    die "Invalid model format: '$MODEL'. Must be 'provider/model' (e.g., 'lmstudio/qwen/qwen3.5-9b')"
fi

if [ "$MODE" = "task" ]; then
    if [ -d "$WORKTREE_PATH" ]; then
        echo "Worktree already exists for $SLUG, reusing..."
    else
        mkdir -p "$AGENTS_DIR"
        echo "Creating worktree at $WORKTREE_PATH on branch $BRANCH..."
        if git show-ref --verify --quiet "refs/heads/${BRANCH}" 2>/dev/null; then
            git worktree add "$WORKTREE_PATH" "$BRANCH"
        else
            git worktree add "$WORKTREE_PATH" -b "$BRANCH"
        fi
        echo "Linking dependencies..."
        link_dependencies "$WORKTREE_PATH"
    fi

    cp "$INSTRUCTION_FILE" "${WORKTREE_PATH}/.local_task.md"

elif [ "$MODE" = "feedback" ]; then
    [ -d "$WORKTREE_PATH" ] || die "No worktree found for slug $SLUG -- cannot apply feedback"
    cp "$INSTRUCTION_FILE" "${WORKTREE_PATH}/.local_feedback.md"

    if [ -z "$TEST_CMD" ]; then
        ORIGINAL_TASK=".local_task_${SLUG}.md"
        if [ -f "$ORIGINAL_TASK" ]; then
            TEST_CMD="$(parse_header "$ORIGINAL_TASK" "Test")"
        fi
    fi
fi

TASK_CONTENT="$(cat "$INSTRUCTION_FILE")"
LOG_FILE="${WORKTREE_PATH}/opencode.log"
ABORT_FILE="${WORKTREE_PATH}/.bridge_abort"

rm -f "$ABORT_FILE"

echo "Invoking OpenCode in $WORKTREE_PATH..."
echo "[$(date '+%H:%M:%S')] Starting OpenCode for $SLUG ($MODE mode) | timeout=${WALL_TIMEOUT}s max_fails=${MAX_FAILS}" > "$LOG_FILE"
echo "  Follow progress: ~/.claude/skills/opencode-delegate/bridge.sh --logs $SLUG"

CMD=(opencode run --dangerously-skip-permissions)
if [ -n "$MODEL" ]; then
    CMD+=(--model "$MODEL")
fi

PREAMBLE="$(cat <<'PREAMBLE_EOF'
<agent-role>
You are a direct code implementation agent dispatched by Claude Code. Your ONLY job is to implement the spec below.

Rules:
- Do NOT invoke any skills or load any skill frameworks (no using-superpowers, no TDD workflow, no brainstorming)
- Do NOT fetch external URLs
- Do NOT write plans, specs, or analysis documents
- Do NOT ask clarifying questions — the spec is authoritative

Workflow: read files → make changes → build/test → fix errors → repeat until the test gate passes or the spec is fully implemented.
</agent-role>
PREAMBLE_EOF
)"

if [ "$MODE" = "feedback" ]; then
    PROMPT_TEXT="${PREAMBLE}"$'\n\n'"Apply the following fixes directly in this workspace:"$'\n\n'"$TASK_CONTENT"
else
    PROMPT_TEXT="${PREAMBLE}"$'\n\n'"Implement the following spec directly in this workspace:"$'\n\n'"$TASK_CONTENT"
fi

# Use exec inside the subshell so the PID we track IS the opencode process,
# allowing the watcher to kill it directly.
OPENCODE_EXIT=0
(
    cd "$WORKTREE_PATH"
    exec "${CMD[@]}" "$PROMPT_TEXT"
) >> "$LOG_FILE" 2>&1 &
OC_PID=$!

WATCHER_PID=$(start_watcher "$OC_PID" "$LOG_FILE" "$WALL_TIMEOUT" "$MAX_FAILS" "$FAIL_PATTERN" "$ABORT_FILE")

wait "$OC_PID" 2>/dev/null || OPENCODE_EXIT=$?
kill "$WATCHER_PID" 2>/dev/null || true
wait "$WATCHER_PID" 2>/dev/null || true

echo "[$(date '+%H:%M:%S')] OpenCode finished (exit: $OPENCODE_EXIT)" >> "$LOG_FILE"

# Watcher writes the kill reason here before sending SIGTERM
ABORT_REASON=""
if [ -f "$ABORT_FILE" ]; then
    ABORT_REASON="$(cat "$ABORT_FILE")"
    rm -f "$ABORT_FILE"
fi

rm -f "${WORKTREE_PATH}/.local_task.md" "${WORKTREE_PATH}/.local_feedback.md"

if [ -n "$ABORT_REASON" ]; then
    json_output "aborted" "$BRANCH" "$SLUG" "$WORKTREE_PATH" "" "" "Agent aborted: $ABORT_REASON"
    exit 2
fi

if [ "$OPENCODE_EXIT" -ne 0 ]; then
    json_output "error" "$BRANCH" "$SLUG" "$WORKTREE_PATH" "" "" "OpenCode exited with code $OPENCODE_EXIT"
    exit $OPENCODE_EXIT
fi

TEST_PASSED=true
if [ -n "$TEST_CMD" ]; then
    if ! run_test_gate "$WORKTREE_PATH" "$TEST_CMD"; then
        TEST_PASSED=false
    fi
fi

rm -f "$TASK_FILE" "$FEEDBACK_FILE"

if [ "$TEST_PASSED" = true ]; then
    json_output "pass" "$BRANCH" "$SLUG" "$WORKTREE_PATH" "${TEST_EXIT_CODE:-0}" "$TEST_CMD" ""
else
    json_output "fail" "$BRANCH" "$SLUG" "$WORKTREE_PATH" "$TEST_EXIT_CODE" "$TEST_CMD" "Test gate failed"
    exit 1
fi
