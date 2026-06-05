#!/bin/bash
# ~/.claude/skills/opencode-delegate/bridge.sh
# Parallel worktree execution bridge with model selection

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

# --- Model selection: CLI --model has highest priority ---
MODEL=""
if [ "${1:-}" = "--model" ]; then
    MODEL="${2:-}"
    shift 2
fi

# Handle --list-models
if [ "${1:-}" = "--list-models" ]; then
    shift
    echo "Available Opencode models:"
    opencode models 2>/dev/null | tail -n +2
    exit 0
fi

# Handle --status
if [ "${1:-}" = "--status" ]; then
    handle_status
    exit 0
fi

# Handle --cleanup
if [ "${1:-}" = "--cleanup" ]; then
    [ -n "${2:-}" ] || die "--cleanup requires a slug argument"
    handle_cleanup "$2"
    exit 0
fi

# Handle --logs
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

# Continue with main flow only if not already handled
if [ "${1:-}" = "--status" ] || [ "${1:-}" = "--cleanup" ]; then
    handle_${1} "1"
    exit 0 && return 0
fi

# After --model is set, parse task/feedback files
SLUG="${1:-}"
[ -n "$SLUG" ] || die "Usage: bridge.sh <slug> | --status | --cleanup <slug> | --logs [slug] | --model <provider/model>"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    die "Not inside a Git repository"
fi

OPENCODE_AVAILABLE=true
if ! command -v opencode >/dev/null 2>&1; then
    OPENCODE_AVAILABLE=false
fi

if [ "$OPENCODE_AVAILABLE" = false ]; then
    json_output "no_opencode" "" "${SLUG:-}" "" "" "" "opencode CLI not found -- prompt for manual execution"
    exit 10
fi

TASK_FILE=".local_task_${SLUG}.md"
FEEDBACK_FILE=".local_feedback_${SLUG}.md"
WORKTREE_PATH="${AGENTS_DIR}/${SLUG}"

# Parse Model: from task/feedback file
HEADER_MODEL="$(parse_header "$TASK_FILE" "Model")"
[ -f "$FEEDBACK_FILE" ] && HEADER_MODEL="$(parse_header "$FEEDBACK_FILE" "Model")"

# Priority: CLI --model > task header > global default
if [ -z "$MODEL" ]; then
    MODEL="$HEADER_MODEL"
fi
if [ -z "$MODEL" ] && [ -n "$GLOBAL_MODEL" ]; then
    MODEL="$GLOBAL_MODEL"
fi
if [ -z "$MODEL" ]; then
    die "No model specified (no --model CLI flag, no Model: in task file, no global default)"
fi

# Validate model format
if ! echo "$MODEL" | grep -qE '^opencode/|^\w+/'; then
    die "Invalid model format: '$MODEL'. Must be 'provider/model' (e.g., 'lmstudio/qwen/qwen3.5-9b')"
fi

MODE=""
INSTRUCTION_FILE=""
if [ -f "$FEEDBACK_FILE" ]; then
    MODE="feedback"
    INSTRUCTION_FILE="$FEEDBACK_FILE"
    echo "Processing feedback for $SLUG..."
elif [ -f "$TASK_FILE" ]; then
    MODE="task"
    INSTRUCTION_FILE="$TASK_FILE"
    echo "Processing new task for $SLUG (model=$MODEL)..."
else
    die "Neither $TASK_FILE nor $FEEDBACK_FILE found"
fi

BRANCH="$(parse_header "$INSTRUCTION_FILE" "Branch")"

[ -n "$BRANCH" ] || die "No Branch: header found"

if [ "$MODE" = "task" ]; then
    if [ -d "$WORKTREE_PATH" ]; then
        echo "Worktree exists for $SLUG, reusing..."
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
    [ -d "$WORKTREE_PATH" ] || die "No worktree for $SLUG -- cannot apply feedback"
    cp "$INSTRUCTION_FILE" "${WORKTREE_PATH}/.local_feedback.md"
fi

TASK_CONTENT="$(cat "$INSTRUCTION_FILE")"
LOG_FILE="${WORKTREE_PATH}/opencode.log"

echo "Invoking OpenCode for $SLUG with model $MODEL..."
echo "[$(date '+%H:%M:%S')] Starting OpenCode ($SLUG, model=$MODEL)" > "$LOG_FILE"

COMMAND="opencode run --dangerously-skip-permissions"
[ -n "$MODEL" ] && COMMAND="$COMMAND --model $MODEL"

if [ "$MODE" = "feedback" ]; then
    ("$COMMAND" "Apply fixes:"$'\n\n'"$TASK_CONTENT") 2>&1 | tee -a "$LOG_FILE" || OPENCODE_EXIT=${PIPESTATUS[0]}
else
    ("$COMMAND" "Implement spec:"$'\n\n'"$TASK_CONTENT") 2>&1 | tee -a "$LOG_FILE" || OPENCODE_EXIT=${PIPESTATUS[0]}
fi

echo "[$(date '+%H:%M:%S')] OpenCode done (exit=$OPENCODE_EXIT)" >> "$LOG_FILE"

if [ $OPENCODE_EXIT -ne 0 ]; then
    json_output "error" "$BRANCH" "$SLUG" "$WORKTREE_PATH" "" "" "OpenCode error: exit $OPENCODE_EXIT"
    exit $OPENCODE_EXIT
fi

rm -f "${WORKTREE_PATH}/.local_task.md" "${WORKTREE_PATH}/.local_feedback.md"

TEST_PASSED=true
if [ -n "$(parse_header "$INSTRUCTION_FILE" "Test")" ]; then
    if ! run_test_gate "$WORKTREE_PATH" "$(parse_header "$INSTRUCTION_FILE" "Test")"; then
        TEST_PASSED=false
    fi
fi

[ "$TEST_PASSED" = true ] && json_output "pass" "$BRANCH" "$SLUG" "$WORKTREE_PATH" 0 "" || { json_output "fail" "$BRANCH" "$SLUG" "$WORKTREE_PATH" 0 "$(parse_header "$INSTRUCTION_FILE" "Test")"; exit 1; }

# Update global default model if it's the first task being run
if [ "$MODE" = "task" ] && [ "$MODEL" != "$GLOBAL_MODEL" ] && [ -z "$GLOBAL_MODEL" ]; then
    mkdir -p ".opencode/config"
    echo "{\"default_model\": \"$MODEL\"}" > ".opencode/config/opencode.json"
    echo "Updated global default model to $MODEL"
fi

exit 0