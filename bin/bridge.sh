#!/bin/bash
# code-delegate/bin/bridge.sh
# Backend-agnostic dispatcher for delegated worktree execution
#
# Usage:
#   bridge.sh <slug>              Run task or feedback for the given branch slug
#   bridge.sh --status            List active agent worktrees
#   bridge.sh --cleanup <slug>    Remove a worktree after branch is approved
#   bridge.sh --logs [slug]       Tail logs for one or all running agents
#   bridge.sh --backends          List installed backends and availability
#   bridge.sh --suggest <json>    Suggest fallback backend+model for a failed task
#   bridge.sh --security-check <backend> <model>  Check if backend+model is approved for security-sensitive tasks

set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

AGENTS_DIR=".git/worktrees_agents"
DEP_DIRS=("node_modules" "venv" ".venv" "vendor" "target" ".build")

DEFAULT_WALL_TIMEOUT=3600   # 60 minutes
DEFAULT_MAX_FAILS=8         # abort after this many detected failure pattern matches
DEFAULT_FAIL_PATTERN="build commands failed|compilation error|FAILED|npm ERR!"
DEFAULT_STALL_SECONDS=300   # kill if log has no new bytes for this many seconds (5 min default — override with StallTimeout: header for large remote models)

json_escape() {
    # Escapes backslashes, double quotes, and control chars so arbitrary
    # strings (test commands, failure messages) can't corrupt the JSON
    # status line every skill parses as the bridge's final stdout line.
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr '\n' ' '
}

json_output() {
    local status="$1" branch="${2:-}" slug="${3:-}" worktree="${4:-}" test_exit="${5:-}" test_cmd="${6:-}" msg="${7:-}" suggestion="${8:-}"
    status="$(json_escape "$status")"
    branch="$(json_escape "$branch")"
    slug="$(json_escape "$slug")"
    worktree="$(json_escape "$worktree")"
    test_cmd="$(json_escape "$test_cmd")"
    msg="$(json_escape "$msg")"
    if [ -n "$suggestion" ]; then
        printf '{"status":"%s","branch":"%s","slug":"%s","worktree":"%s","test_exit_code":%s,"test_command":"%s","message":"%s","suggestion":%s}\n' \
            "$status" "$branch" "$slug" "$worktree" "${test_exit:-null}" "$test_cmd" "$msg" "$suggestion"
    else
        printf '{"status":"%s","branch":"%s","slug":"%s","worktree":"%s","test_exit_code":%s,"test_command":"%s","message":"%s"}\n' \
            "$status" "$branch" "$slug" "$worktree" "${test_exit:-null}" "$test_cmd" "$msg"
    fi
}

die() {
    json_output "error" "" "${SLUG:-}" "" "" "" "$1"
    exit 1
}

parse_header() {
    local file="$1" key="$2"
    grep -m1 "^${key}:" "$file" 2>/dev/null | sed "s/^${key}:[[:space:]]*//" || true
}

resolve_backend() {
    local file="$1"
    local backend
    backend="$(parse_header "$file" "Backend")"

    if [ -z "$backend" ] || [ "$backend" = "auto" ]; then
        backend="$(auto_select_backend "$file")"
        if [ -z "$backend" ]; then
            die "No available backend found. Install opencode, claude, or codex CLI."
        fi
        echo "Auto-selected backend: $backend" >&2
    fi

    local runner="$PLUGIN_ROOT/backends/${backend}/run.sh"
    if [ ! -f "$runner" ]; then
        die "Unknown backend '${backend}': no runner found at backends/${backend}/run.sh"
    fi
    echo "$backend"
}

auto_select_backend() {
    local instruction_file="$1"
    local skill_dir
    skill_dir="$PLUGIN_ROOT"

    local files_header
    files_header="$(parse_header "$instruction_file" "Files")"
    local file_count=1
    if [ -n "$files_header" ]; then
        file_count=$(echo "$files_header" | tr ',' '\n' | wc -l | tr -d ' ')
    fi

    for backend in opencode claude codex; do
        local config="${skill_dir}/backends/${backend}/config.yaml"
        [ -f "$config" ] || continue

        local check_cmd
        check_cmd="$(grep '^check_command:' "$config" | sed 's/^check_command:[[:space:]]*//')"
        if [ -n "$check_cmd" ] && ! eval "$check_cmd" >/dev/null 2>&1; then
            continue
        fi

        if [ "$file_count" -gt 3 ]; then
            if grep -q 'cross_file: false' "$config"; then
                continue
            fi
        fi

        echo "$backend"
        return 0
    done

    echo ""
    return 1
}

resolve_model() {
    local backend="$1" model="$2"
    local config_file="$PLUGIN_ROOT/backends/${backend}/config.yaml"

    # Precedence when no explicit Model: header is given:
    #   1. Model: header (passed in as $model)
    #   2. per-backend env override (e.g. OPENCODE_DELEGATE_MODEL) — machine-local,
    #      keeps personal defaults out of the committed config so fresh installs stay portable
    #   3. config.yaml default_model (kept empty for opencode so it defers to opencode.json)
    #   4. empty — the backend runner omits --model and the CLI picks its own default
    if [ -z "$model" ]; then
        local env_var
        env_var="$(printf '%s' "$backend" | tr '[:lower:]' '[:upper:]')_DELEGATE_MODEL"
        model="${!env_var:-}"
    fi
    if [ -z "$model" ]; then
        model="$(grep '^default_model:' "$config_file" | sed 's/^default_model:[[:space:]]*//' | tr -d '"')"
    fi

    # Nothing resolved — let the backend runner handle an empty model
    [ -n "$model" ] || return

    # Resolve alias → id; pass through unchanged if it is not a known alias
    # (e.g. a raw dynamic model ID like ollama/qwen3.6:27b)
    local resolved
    resolved="$(awk -v alias="$model" '
        /^ *- alias:/ { a=$NF }
        /^ *id:/ { if (a == alias) { print $NF; exit } }
    ' "$config_file" 2>/dev/null)"
    echo "${resolved:-$model}"
}

get_model_escalation() {
    local backend="$1" current_model="$2"
    local config_file="$PLUGIN_ROOT/backends/${backend}/config.yaml"
    awk -v cur="$current_model" '
        /^ *- alias:/ { prev=alias; alias=$NF }
        /^ *id:/ {
            if ($NF == cur || alias == cur) { if (prev != "") print prev; exit }
        }
    ' prev="" alias="" "$config_file" 2>/dev/null
}

list_backend_models() {
    local backend="$1"
    local config_file="$PLUGIN_ROOT/backends/${backend}/config.yaml"
    awk '/^ *- alias:/ { printf "%s ", $NF }' "$config_file" 2>/dev/null
}

is_backend_available() {
    local backend="$1"
    local config_file="$PLUGIN_ROOT/backends/${backend}/config.yaml"
    [ -f "$config_file" ] || return 1
    local check_cmd
    check_cmd="$(grep '^check_command:' "$config_file" | sed 's/^check_command:[[:space:]]*//')"
    [ -z "$check_cmd" ] && return 0
    eval "$check_cmd" >/dev/null 2>&1
}

suggest_fallback() {
    local reason="$1" failed_backend="$2" failed_model="$3" task_file="${4:-}"
    local skill_dir
    skill_dir="$PLUGIN_ROOT"

    local file_count=1
    if [ -n "$task_file" ] && [ -f "$task_file" ]; then
        local files_header
        files_header="$(parse_header "$task_file" "Files")"
        if [ -n "$files_header" ]; then
            file_count=$(echo "$files_header" | tr ',' '\n' | wc -l | tr -d ' ')
        fi
    fi

    # Scenario 1: backend unavailable — find alternative backend
    if [ "$reason" = "no_backend" ]; then
        for alt in opencode claude codex; do
            [ "$alt" = "$failed_backend" ] && continue
            is_backend_available "$alt" || continue
            if [ "$file_count" -gt 3 ]; then
                grep -q 'cross_file: false' "$skill_dir/backends/${alt}/config.yaml" && continue
            fi
            local alt_default
            alt_default="$(grep '^default_model:' "$skill_dir/backends/${alt}/config.yaml" | sed 's/^default_model:[[:space:]]*//' | tr -d '"')"
            printf '{"action":"switch_backend","backend":"%s","model":"%s","reason":"%s CLI not found, %s is available"}\n' \
                "$alt" "${alt_default:-default}" "$failed_backend" "$alt"
            return 0
        done
        printf '{"action":"implement_directly","reason":"no backends available"}\n'
        return 0
    fi

    # Scenario 2: abort/fail — try escalating model within same backend first
    if [ "$reason" = "aborted" ] || [ "$reason" = "fail" ]; then
        if [ -n "$failed_model" ] && [ -n "$failed_backend" ]; then
            local next_model
            next_model="$(get_model_escalation "$failed_backend" "$failed_model")"
            if [ -n "$next_model" ]; then
                printf '{"action":"escalate_model","backend":"%s","model":"%s","reason":"%s failed with %s, escalating to %s"}\n' \
                    "$failed_backend" "$next_model" "$failed_model" "$failed_backend" "$next_model"
                return 0
            fi
        fi

        # No higher model in same backend — try cross-backend fallback
        for alt in claude codex opencode; do
            [ "$alt" = "$failed_backend" ] && continue
            is_backend_available "$alt" || continue
            if [ "$file_count" -gt 3 ]; then
                grep -q 'cross_file: false' "$skill_dir/backends/${alt}/config.yaml" && continue
            fi
            local cost_tier
            cost_tier="$(grep '^cost_tier:' "$skill_dir/backends/${alt}/config.yaml" | sed 's/^cost_tier:[[:space:]]*//')"
            local alt_default
            alt_default="$(grep '^default_model:' "$skill_dir/backends/${alt}/config.yaml" | sed 's/^default_model:[[:space:]]*//' | tr -d '"')"
            printf '{"action":"switch_backend","backend":"%s","model":"%s","cost_tier":"%s","reason":"%s/%s failed, suggesting %s"}\n' \
                "$alt" "${alt_default:-default}" "$cost_tier" "$failed_backend" "$failed_model" "$alt"
            return 0
        done

        printf '{"action":"implement_directly","reason":"no alternative backends available after %s/%s failure"}\n' \
            "$failed_backend" "$failed_model"
        return 0
    fi

    printf '{"action":"none","reason":"unknown failure reason: %s"}\n' "$reason"
}

check_backend_available() {
    local backend="$1"
    local config_file="$PLUGIN_ROOT/backends/${backend}/config.yaml"
    if [ -f "$config_file" ]; then
        local check_cmd
        check_cmd="$(grep '^check_command:' "$config_file" | sed 's/^check_command:[[:space:]]*//')"
        if [ -n "$check_cmd" ] && ! eval "$check_cmd" >/dev/null 2>&1; then
            local suggestion
            suggestion="$(suggest_fallback "no_backend" "$backend" "" "${INSTRUCTION_FILE:-}")"
            json_output "no_backend" "" "$SLUG" "" "" "" "${backend} CLI not found" "$suggestion"
            exit 10
        fi
    fi
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
        if [ -f "${dir}agent.log" ]; then
            last_log=" | $(tail -1 "${dir}agent.log")"
        fi
        backend=""
        if [ -f "${dir}.bridge_backend" ]; then
            backend=" [$(cat "${dir}.bridge_backend")]"
        fi
        echo "  $slug -> $branch$backend$last_log"
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

# Monitors a backend process for stalls, failure loops, and wall-clock timeout.
# Kills $pid and writes a reason to $abort_file if any limit is triggered.
is_alive() { kill -0 "$1" 2>/dev/null; }

start_watcher() {
    local pid="$1" log="$2" wall_timeout="$3" max_fails="$4" fail_pattern="$5" abort_file="$6" stall_seconds="$7"
    (
        elapsed=0
        last_size=0
        stall_elapsed=0
        while is_alive "$pid"; do
            sleep 10
            # Re-check after sleep — process may have exited while we slept
            is_alive "$pid" || break
            elapsed=$((elapsed + 10))

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
                stall_elapsed=$((stall_elapsed + 10))

                # CPU-based liveness: if the process is actively consuming CPU,
                # it's computing (e.g. a local model tokenising) — reset stall timer.
                # Remote models block on network I/O so CPU stays ~0; for those,
                # the heartbeat below provides visibility instead.
                cpu_raw=$(ps -p "$pid" -o %cpu= 2>/dev/null | tr -d ' .')
                if [ -n "$cpu_raw" ] && [ "$cpu_raw" -gt 0 ] 2>/dev/null; then
                    stall_elapsed=0
                fi

                # Heartbeat: log a "still waiting" line every 60 s during silence
                # so `bridge.sh --logs` shows the process is alive and the stall budget.
                if [ "$stall_elapsed" -gt 0 ] && [ $(( stall_elapsed % 60 )) -eq 0 ]; then
                    echo "[BRIDGE] $(date '+%H:%M:%S') Waiting: no output for ${stall_elapsed}s, process alive (limit ${stall_seconds}s)" >> "$log"
                fi

                if [ "$stall_elapsed" -ge "$stall_seconds" ]; then
                    echo "[BRIDGE] $(date '+%H:%M:%S') Stall: no log activity for ${stall_seconds}s" >> "$log"
                    echo "stall: no activity for ${stall_seconds}s" > "$abort_file"
                    kill "$pid" 2>/dev/null || true
                    break
                fi
            else
                stall_elapsed=0
                last_size=$cur_size
            fi

            # Failure loop detection — strip ANSI codes before counting
            if [ -n "$fail_pattern" ] && [ "$max_fails" -gt 0 ]; then
                fail_count=$(sed 's/\x1b\[[0-9;]*m//g' "$log" 2>/dev/null | grep -cE "$fail_pattern" 2>/dev/null) || fail_count=0
                fail_count=$(echo "$fail_count" | tr -d '[:space:]')
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

if [ "${1:-}" = "--backends" ]; then
    skill_dir="$PLUGIN_ROOT"
    echo "Installed backends:"
    for config in "$skill_dir"/backends/*/config.yaml; do
        [ -f "$config" ] || continue
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

if [ "${1:-}" = "--models" ]; then
    skill_dir="$PLUGIN_ROOT"
    backend_filter="${2:-}"
    for config in "$skill_dir"/backends/*/config.yaml; do
        [ -f "$config" ] || continue
        dir="$(dirname "$config")"
        name="$(basename "$dir")"
        [ -z "$backend_filter" ] || [ "$name" = "$backend_filter" ] || continue

        check_cmd="$(grep '^check_command:' "$config" | sed 's/^check_command:[[:space:]]*//')"
        if [ -n "$check_cmd" ] && ! eval "$check_cmd" >/dev/null 2>&1; then
            echo "$name: (unavailable)"
            continue
        fi

        models_value="$(grep '^models:' "$config" | sed 's/^models:[[:space:]]*//')"
        if [ "$models_value" = "dynamic" ]; then
            list_cmd="$(grep '^list_models_command:' "$config" | sed 's/^list_models_command:[[:space:]]*//')"
            if [ -n "$list_cmd" ]; then
                echo "$name: (dynamic — querying CLI)"
                eval "$list_cmd" 2>/dev/null | sed 's/^/  /' || echo "  (query failed)"
            else
                echo "$name: (dynamic — pass any model ID directly)"
            fi
        else
            default_model="$(grep '^default_model:' "$config" | sed 's/^default_model:[[:space:]]*//')"
            echo "$name:"
            # Parse alias/description blocks from model entries (indented)
            awk -v defmodel="$default_model" '
                function flush() {
                    if (alias != "" && desc != "") {
                        marker=""
                        if (alias == defmodel) marker=" (default)"
                        print "  " alias marker sec " — " desc
                    }
                    alias=""; desc=""; sec=""
                }
                /^ *- alias:/ { flush(); alias=$NF }
                /^ *security_ok: *true/ { if (alias != "") sec=" [security-approved]" }
                /^ *description:/ {
                    if (alias != "") {
                        sub(/^ *description: *"?/, ""); sub(/"$/, "")
                        desc=$0
                    }
                }
                END { flush() }
            ' "$config"
        fi
    done
    exit 0
fi

if [ "${1:-}" = "--suggest" ]; then
    [ -n "${2:-}" ] || die "--suggest requires a JSON argument: '{\"reason\":\"...\",\"backend\":\"...\",\"model\":\"...\",\"task_file\":\"...\"}'"
    sg_input="$2"
    sg_reason="$(echo "$sg_input" | sed -n 's/.*"reason" *: *"\([^"]*\)".*/\1/p')"
    sg_backend="$(echo "$sg_input" | sed -n 's/.*"backend" *: *"\([^"]*\)".*/\1/p')"
    sg_model="$(echo "$sg_input" | sed -n 's/.*"model" *: *"\([^"]*\)".*/\1/p')"
    sg_task="$(echo "$sg_input" | sed -n 's/.*"task_file" *: *"\([^"]*\)".*/\1/p')"
    suggest_fallback "$sg_reason" "$sg_backend" "$sg_model" "$sg_task"
    exit 0
fi

if [ "${1:-}" = "--security-check" ]; then
    [ -n "${2:-}" ] || die "--security-check requires: <backend> <model>"
    sc_backend="$2"
    sc_model="${3:-}"
    sc_config="$PLUGIN_ROOT/backends/${sc_backend}/config.yaml"
    if [ ! -f "$sc_config" ]; then
        printf '{"approved":false,"reason":"unknown backend: %s"}\n' "$sc_backend"
        exit 0
    fi
    if [ -z "$sc_model" ]; then
        sc_model="$(grep '^default_model:' "$sc_config" | sed 's/^default_model:[[:space:]]*//' | tr -d '"')"
    fi
    approved="$(awk -v model="$sc_model" '
        /^ *- alias:/ { alias=$NF }
        /^ *id:/ { id=$NF }
        /^ *security_ok: *true/ { if (alias == model || id == model) { print "true"; exit } }
        /^ *security_ok: *false/ { if (alias == model || id == model) { print "false"; exit } }
    ' "$sc_config" 2>/dev/null)"
    if [ "$approved" = "true" ]; then
        printf '{"approved":true,"backend":"%s","model":"%s"}\n' "$sc_backend" "$sc_model"
    else
        # Find the first security-approved model across all backends
        skill_dir="$PLUGIN_ROOT"
        suggestion=""
        for b in claude codex opencode; do
            cfg="$skill_dir/backends/$b/config.yaml"
            [ -f "$cfg" ] || continue
            sec_model="$(awk '
                /^ *- alias:/ { alias=$NF }
                /^ *security_ok: *true/ { print alias; exit }
            ' "$cfg" 2>/dev/null)"
            if [ -n "$sec_model" ]; then
                suggestion="$(printf ',"suggested_backend":"%s","suggested_model":"%s"' "$b" "$sec_model")"
                break
            fi
        done
        printf '{"approved":false,"backend":"%s","model":"%s"%s}\n' "$sc_backend" "${sc_model:-default}" "$suggestion"
    fi
    exit 0
fi

if [ "${1:-}" = "--logs" ]; then
    slug="${2:-}"
    if [ -n "$slug" ]; then
        log="${AGENTS_DIR}/${slug}/agent.log"
        if [ -f "$log" ]; then
            cat "$log"
        else
            echo "No log found for slug: $slug"
        fi
    else
        for log in "$AGENTS_DIR"/*/agent.log; do
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
[ -n "$SLUG" ] || die "Usage: bridge.sh <slug> | --status | --cleanup <slug> | --logs [slug] | --backends | --models [backend] | --suggest <json>"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    die "Not inside a Git repository"
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
WALL_TIMEOUT="$(parse_header "$INSTRUCTION_FILE" "Timeout")"
MAX_FAILS="$(parse_header "$INSTRUCTION_FILE" "MaxFails")"
FAIL_PATTERN="$(parse_header "$INSTRUCTION_FILE" "FailPattern")"
STALL_SECONDS="$(parse_header "$INSTRUCTION_FILE" "StallTimeout")"

WALL_TIMEOUT="${WALL_TIMEOUT:-$DEFAULT_WALL_TIMEOUT}"
MAX_FAILS="${MAX_FAILS:-$DEFAULT_MAX_FAILS}"
FAIL_PATTERN="${FAIL_PATTERN:-$DEFAULT_FAIL_PATTERN}"
STALL_SECONDS="${STALL_SECONDS:-$DEFAULT_STALL_SECONDS}"

[ -n "$BRANCH" ] || die "No Branch: header found in $INSTRUCTION_FILE"

# Resolve and validate backend
BACKEND="$(resolve_backend "$INSTRUCTION_FILE")"
BACKEND_DIR="$PLUGIN_ROOT/backends/${BACKEND}"
BACKEND_RUNNER="${BACKEND_DIR}/run.sh"

[ -f "$BACKEND_RUNNER" ] || die "Backend runner not found: $BACKEND_RUNNER"
[ -x "$BACKEND_RUNNER" ] || chmod +x "$BACKEND_RUNNER"

# Check backend CLI availability
check_backend_available "$BACKEND"

# Resolve model alias → id and apply backend default
MODEL="$(resolve_model "$BACKEND" "$MODEL")"

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
    echo "$BACKEND" > "${WORKTREE_PATH}/.bridge_backend"

elif [ "$MODE" = "feedback" ]; then
    [ -d "$WORKTREE_PATH" ] || die "No worktree found for slug $SLUG -- cannot apply feedback"
    cp "$INSTRUCTION_FILE" "${WORKTREE_PATH}/.local_feedback.md"
    echo "$BACKEND" > "${WORKTREE_PATH}/.bridge_backend"

    if [ -z "$TEST_CMD" ]; then
        ORIGINAL_TASK=".local_task_${SLUG}.md"
        if [ -f "$ORIGINAL_TASK" ]; then
            TEST_CMD="$(parse_header "$ORIGINAL_TASK" "Test")"
        fi
    fi
fi

SPEC_IN_WORKTREE="${WORKTREE_PATH}/.local_${MODE}.md"
LOG_FILE="${WORKTREE_PATH}/agent.log"
ABORT_FILE="${WORKTREE_PATH}/.bridge_abort"

rm -f "$ABORT_FILE"

echo "Invoking ${BACKEND} backend in $WORKTREE_PATH..."
echo "[$(date '+%H:%M:%S')] Starting ${BACKEND} for $SLUG ($MODE mode) | timeout=${WALL_TIMEOUT}s stall=${STALL_SECONDS}s max_fails=${MAX_FAILS}" > "$LOG_FILE"
echo "  Follow progress: bridge.sh --logs $SLUG"

# Use exec inside the subshell so the PID we track IS the backend process,
# allowing the watcher to kill it directly.
OPENCODE_EXIT=0
(
    exec "$BACKEND_RUNNER" "$WORKTREE_PATH" "$SPEC_IN_WORKTREE" "$MODEL" "$MODE"
) >> "$LOG_FILE" 2>&1 &
OC_PID=$!

WATCHER_PID=$(start_watcher "$OC_PID" "$LOG_FILE" "$WALL_TIMEOUT" "$MAX_FAILS" "$FAIL_PATTERN" "$ABORT_FILE" "$STALL_SECONDS")

wait "$OC_PID" 2>/dev/null || OPENCODE_EXIT=$?
kill "$WATCHER_PID" 2>/dev/null || true
wait "$WATCHER_PID" 2>/dev/null || true

echo "[$(date '+%H:%M:%S')] ${BACKEND} finished (exit: $OPENCODE_EXIT)" >> "$LOG_FILE"

# Watcher writes the kill reason here before sending SIGTERM
ABORT_REASON=""
if [ -f "$ABORT_FILE" ]; then
    ABORT_REASON="$(cat "$ABORT_FILE")"
    rm -f "$ABORT_FILE"
fi

rm -f "${WORKTREE_PATH}/.local_task.md" "${WORKTREE_PATH}/.local_feedback.md"

if [ -n "$ABORT_REASON" ]; then
    SUGGESTION="$(suggest_fallback "aborted" "$BACKEND" "$MODEL" "$INSTRUCTION_FILE")"
    json_output "aborted" "$BRANCH" "$SLUG" "$WORKTREE_PATH" "" "" "Agent aborted: $ABORT_REASON" "$SUGGESTION"
    exit 2
fi

if [ "$OPENCODE_EXIT" -ne 0 ]; then
    json_output "error" "$BRANCH" "$SLUG" "$WORKTREE_PATH" "" "" "${BACKEND} exited with code $OPENCODE_EXIT"
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
    SUGGESTION="$(suggest_fallback "fail" "$BACKEND" "$MODEL" "$INSTRUCTION_FILE")"
    json_output "fail" "$BRANCH" "$SLUG" "$WORKTREE_PATH" "$TEST_EXIT_CODE" "$TEST_CMD" "Test gate failed" "$SUGGESTION"
    exit 1
fi
