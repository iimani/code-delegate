#!/bin/bash
# ~/.claude/skills/opencode-delegate/bridge.sh
# Parallel worktree execution bridge for the opencode-delegate skill
#
# Usage:
#   bridge.sh <slug>              Run task or feedback for the given branch slug
#   bridge.sh --status            List active agent worktrees
#   bridge.sh --cleanup <slug>    Remove a worktree after branch is approved

set -euo pipefail

AGENTS_DIR=".git/worktrees_agents"
DEP_DIRS=("node_modules" "venv" ".venv" "vendor" "target" ".build")

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
    grep -m1 "^${key}:" "$file" 2>/dev/null | sed "s/^${key}:[[:space:]]*//"
}

link_dependencies() {
    local worktree_path="$1"
    local main_root
    main_root="$(git rev-parse --show-toplevel)"
    for dep in "${DEP_DIRS[@]}"; do
        if [ -e "${main_root}/${dep}" ] && [ ! -e "${worktree_path}/${dep}" ]; then
            l            ln -s "${main_root}/${dep}" "${worktree_path}/${dep}"
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

# --- Early parsing ---

# Handle --model <value> syntax before SLUG is set
MODEL=""
if [ "${1:-}" = "--model" ]; then
    MODEL="${2:-}"
    shift 2
elif [ "${1:-}" = "--list-models" ]; then
    shift
elif [ -n "${1:-}" ]; then
    SLUG="${1:-}"
fi

# Handle main flags that don't affect SLUG
if [ "${1:-}" = "--status" ]; then
    handle_status
    exit 0
fi

if [ "${1:-}" = "--cleanup" ]; then
    [ -n "${2:-}" ] || die "--cleanup requires a slug argument"
    handle_cleanup "$2"
    exit 0
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

SLUG="${1:-}"
[ -n "$SLUG" ] || die "Usage: bridge.sh <slug> | --status | --cleanup <slug> | --logs [slug]"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    die "Not inside a Git repository"
fi

OPENCODE_AVAILABLE=true
if ! command -v opencode >/dev/null 2>&1; then
    OPENCODE_AVAILABLE=false
fi

if [ "$OPENCODE_AVAILABLE" = false ]; then
    json_output "no_opencode" "" "${SLUG:-}" "" "" "" "opencode CLI not found -- Claude should prompt user to proceed directly"
    exit 10
fi

TASK_FILE=".local_task_${SLUG}.md"
FEEDBACK_FILE=".local_feedback_${SLUG}.md"
WORKTREE_PATH="${AGENTS_DIR}/${SLUG}"
TEST_EXIT_CODE=""

MODE=""
INSTRUCTION_FILE=""
# Default to default model, can be overridden by Model: header
if [ -n "$MODEL" ] && [ "${DEFAULT_MODEL:-}" = "" ]; then
    DEFAULT_MODEL="$MODEL"
fi
if [ -n "${MODEL:-}" ]; then
    MODEL="$MODEL"
fi
MODEL="$(parse_header "$INSTRUCTION_FILE" "Model")"
if [ -z "$MODEL" ] && [ -n "${DEFAULT_MODEL:-}" ]; then
    MODEL="$DEFAULT_MODEL"
fi
if [ -z "$MODEL" ]; then
    # Use global default if available
    GLOBAL_MODEL=""
    if [ -f "$HOME/.opencode/opencode.json" ]; then
        GLOBAL_MODEL="$(jq -r '.default_model // if .models then (keys | .[0]) else "" end' "$HOME/.opencode/opencode.json" 2>/dev/null || echo "")"
    fi
    if [ -n "$GLOBAL_MODEL" ]; then
        MODEL="$GLOBAL_MODEL"
    fi
    die "No model specified (no Model: header, no --model flag, no global default) -- please specify a model using --model, Model: in task file, or set in ~/.opencode/opencode.json"
fi

# Validate model format
if [ -n "$MODEL" ]; then
    if ! echo "$MODEL" | grep -qE '^opencode/|^\w+/'; then
        die "Invalid model format: '$MODEL'. Must be 'provider/model' (e.g., 'lmstudio/qwen/qwen3.5-9b')"
    fi
fi

if [ "$OPENCODE_AVAILABLE" = false ]; then
    json_output "no_opencode" "" "${SLUG:-}" "" "" "" "opencode CLI not found -- Claude should prompt user to proceed directly"
    exit 10
fi

[ -n "$BRANCH" ] || die "No Branch: header found in $INSTRUCTION_FILE"

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

echo "Invoking OpenCode for $SLUG with model $MODEL..."
echo "[$(date '+%H:%M:%S')] Starting OpenCode for $SLUG ($MODE mode, model=$MODEL)" > "$LOG_FILE"

COMMAND="opencode run --dangerously-skip-permissions"
if [ -n "$MODEL" ]; then
    COMMAND="$COMMAND --model $MODEL"
fi

if [ "$MODE" = "feedback" ]; then
    ("$COMMAND" "Apply the following fixes directly in this workspace:"$'\n\n'"$TASK_CONTENT") 2>&1 | tee -a "$LOG_FILE" || OPENCODE_EXIT=${PIPESTATUS[0]}
else
    ("$COMMAND" "Implement the following spec directly in this workspace:"$'\n\n'"$TASK_CONTENT") 2>&1 | tee -a "$LOG_FILE" || OPENCODE_EXIT=${PIPESTATUS[0]}
fi

echo "[$(date '+%H:%M:%S')] OpenCode finished (exit: $OPENCODE_EXIT)" >> "$LOG_FILE"

if [ $OPENCODE_EXIT -ne 0 ]; then
    json_output "error" "$BRANCH" "$SLUG" "$WORKTREE_PATH" "" "" "OpenCode exited with code $OPENCODE_EXIT"
    exit $OPENCODE_EXIT
fi

rm -f "${WORKTREE_PATH}/.local_task.md" "${WORKTREE_PATH}/.local_feedback.md"



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
