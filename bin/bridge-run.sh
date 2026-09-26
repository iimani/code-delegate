#!/bin/bash
# code-delegate/bin/bridge-run.sh
# Fast path, invoked as `bridge.sh run|wait` (see skills/fast/SKILL.md):
#
#   bridge.sh run  <slug>... [--max-wait S]   start tasks in parallel, wait, report
#   bridge.sh wait <slug>... [--max-wait S]   keep waiting for tasks started by `run`
#
# Each task runs the normal single-task pipeline (`bridge.sh <slug>`) in a
# background worker, gets one automatic fix round if its test gate fails, and
# on success has its changes applied to the current working tree, uncommitted.
# `run` returns after --max-wait seconds (default 540, under Claude Code's
# 10-minute Bash limit) and reports unfinished tasks as "running".
#
# Exit status: 0 all passed, 1 any task failed, 3 any task still running.

set -uo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BRIDGE="$PLUGIN_ROOT/bin/bridge.sh"
AGENTS_DIR=".git/worktrees_agents"
RESULTS_DIR="$AGENTS_DIR/.results"
DEFAULT_MAX_WAIT=540
POLL_SECONDS=5
FEEDBACK_LINES=60
REPORT_LINES=15

# Never part of the delegate's change.
EXCLUDES=(
    ':(exclude)agent.log' ':(exclude).bridge_backend' ':(exclude).bridge_model'
    ':(exclude).bridge_base' ':(exclude).bridge_abort' ':(exclude).local_task.md'
    ':(exclude).local_feedback.md' ':(exclude)node_modules' ':(exclude)venv' ':(exclude).venv'
    ':(exclude)vendor' ':(exclude)target' ':(exclude).build'
)

parse_header() {
    grep -m1 "^$2:" "$1" 2>/dev/null | sed "s/^$2:[[:space:]]*//" || true
}

json_escape() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr '\n\t' '  '
}

# write_result <slug> <status> <attempts> <duration_s> <message>
write_result() {
    local slug="$1" status="$2" attempts="$3" duration="$4" message="$5"
    local wt="$AGENTS_DIR/$slug" backend="" model="" worktree=""
    [ -f "$RESULTS_DIR/$slug.backend" ] && backend="$(cat "$RESULTS_DIR/$slug.backend")"
    [ -f "$RESULTS_DIR/$slug.model" ] && model="$(cat "$RESULTS_DIR/$slug.model")"
    [ -d "$wt" ] && worktree="$wt"
    printf '{"slug":"%s","status":"%s","backend":"%s","model":"%s","attempts":%s,"duration_s":%s,"worktree":"%s","message":"%s"}\n' \
        "$(json_escape "$slug")" "$status" "$(json_escape "$backend")" "$(json_escape "$model")" \
        "$attempts" "$duration" "$(json_escape "$worktree")" "$(json_escape "$message")" \
        > "$RESULTS_DIR/$slug.json.tmp"
    mv "$RESULTS_DIR/$slug.json.tmp" "$RESULTS_DIR/$slug.json"
}

# Status and message from the JSON line bridge.sh prints last.
bridge_field() {
    local file="$1" field="$2"
    grep '^{"status"' "$file" 2>/dev/null | tail -1 | sed -n "s/.*\"$field\":\"\\([^\"]*\\)\".*/\\1/p"
}

# Everything bridge.sh printed except its JSON status line (includes the test gate output).
bridge_output_tail() {
    grep -v '^{"status"' "$1" 2>/dev/null | tail -n "$2"
}

remember_backend_model() {
    local slug="$1" wt="$AGENTS_DIR/$1"
    [ -f "$wt/.bridge_backend" ] && cp "$wt/.bridge_backend" "$RESULTS_DIR/$slug.backend"
    [ -f "$wt/.bridge_model" ] && cp "$wt/.bridge_model" "$RESULTS_DIR/$slug.model"
    return 0
}

acquire_apply_lock() {
    local tries=0
    until mkdir "$RESULTS_DIR/.apply.lock" 2>/dev/null; do
        tries=$((tries + 1))
        [ "$tries" -gt 600 ] && return 1
        sleep 0.5
    done
}

release_apply_lock() {
    rmdir "$RESULTS_DIR/.apply.lock" 2>/dev/null || true
}

# Apply the delegate's change (committed + uncommitted + new files, relative to
# the commit its worktree started from) to the main working tree, uncommitted.
apply_change() {
    local slug="$1" wt="$AGENTS_DIR/$1" patch="$RESULTS_DIR/$1.patch" base
    base="$(cat "$wt/.bridge_base" 2>/dev/null)"
    if [ -z "$base" ]; then
        echo "worktree has no recorded base commit"
        return 2
    fi
    ( cd "$wt" && git add -A -- . "${EXCLUDES[@]}" >/dev/null 2>&1 \
        && git diff --cached --binary "$base" -- . "${EXCLUDES[@]}" ) > "$patch" || {
        echo "could not compute the delegate's diff"
        return 2
    }
    if [ ! -s "$patch" ]; then
        return 3
    fi
    git apply --stat "$patch" > "$RESULTS_DIR/$slug.diffstat" 2>/dev/null || true
    acquire_apply_lock || { echo "timed out waiting for another task to finish applying"; return 2; }
    local out status=0
    out="$(git apply --whitespace=nowarn "$patch" 2>&1)" || status=$?
    release_apply_lock
    if [ "$status" -ne 0 ]; then
        echo "$out" | head -5
        return 1
    fi
    return 0
}

worker() {
    local slug="$1" started attempts=1 status message task="./.local_task_${1}.md"
    local branch test_cmd header value
    started=$(date +%s)
    # bridge.sh deletes the task file after the first attempt; keep a copy for the fix round.
    cp "$task" "$RESULTS_DIR/$slug.task.md" 2>/dev/null && task="$RESULTS_DIR/$slug.task.md"
    branch="$(parse_header "$task" "Branch")"
    test_cmd="$(parse_header "$task" "Test")"

    "$BRIDGE" "$slug" > "$RESULTS_DIR/$slug.attempt1.out" 2>&1
    remember_backend_model "$slug"
    status="$(bridge_field "$RESULTS_DIR/$slug.attempt1.out" status)"
    message="$(bridge_field "$RESULTS_DIR/$slug.attempt1.out" message)"

    if [ "$status" = "fail" ]; then
        attempts=2
        # Same delegate for the fix round: pin the backend/model the first attempt used.
        local used_backend used_model
        used_backend="$(cat "$RESULTS_DIR/$slug.backend" 2>/dev/null)"
        used_model="$(cat "$RESULTS_DIR/$slug.model" 2>/dev/null)"
        {
            printf -- '---\nBranch: %s\nTest: %s\n' "$branch" "$test_cmd"
            [ -n "$used_backend" ] && printf 'Backend: %s\n' "$used_backend"
            [ -n "$used_model" ] && printf 'Model: %s\n' "$used_model"
            for header in Timeout StallTimeout MaxFails FailPattern; do
                value="$(parse_header "$task" "$header")"
                [ -n "$value" ] && printf '%s: %s\n' "$header" "$value"
            done
            printf -- '---\n\n'
            printf 'The test gate `%s` fails with the output below. Fix the implementation so it passes; do not weaken or delete tests.\n\n```\n' "$test_cmd"
            bridge_output_tail "$RESULTS_DIR/$slug.attempt1.out" "$FEEDBACK_LINES"
            printf '```\n'
        } > "./.local_feedback_${slug}.md"
        "$BRIDGE" "$slug" > "$RESULTS_DIR/$slug.attempt2.out" 2>&1
        status="$(bridge_field "$RESULTS_DIR/$slug.attempt2.out" status)"
        message="$(bridge_field "$RESULTS_DIR/$slug.attempt2.out" message)"
    fi
    [ -n "$status" ] || { status="error"; message="bridge.sh produced no status (see $RESULTS_DIR/$slug.attempt${attempts}.out)"; }

    if [ "$status" = "pass" ]; then
        local apply_msg apply_status=0
        apply_msg="$(apply_change "$slug")" || apply_status=$?
        case "$apply_status" in
            0)
                git worktree remove --force "$AGENTS_DIR/$slug" >/dev/null 2>&1 || true
                [ -n "$branch" ] && git branch -D "$branch" >/dev/null 2>&1 || true
                message="applied to working tree (uncommitted)" ;;
            3)
                status="no_changes"
                message="test gate passed but the delegate changed nothing" ;;
            1)
                status="apply_conflict"
                message="could not apply to the working tree: $apply_msg" ;;
            *)
                status="error"
                message="$apply_msg" ;;
        esac
    else
        bridge_output_tail "$RESULTS_DIR/$slug.attempt${attempts}.out" "$REPORT_LINES" > "$RESULTS_DIR/$slug.tail"
    fi
    write_result "$slug" "$status" "$attempts" "$(( $(date +%s) - started ))" "$message"
}

# Refuses tasks that can't be run safely; writes an error result for them.
validate() {
    local slug="$1" task="./.local_task_${1}.md" files dirty
    if [ ! -f "$task" ]; then
        write_result "$slug" "error" 0 0 "no task file $task"; return 1
    fi
    if [ -z "$(parse_header "$task" "Branch")" ]; then
        write_result "$slug" "error" 0 0 "task file has no Branch: header"; return 1
    fi
    if [ -z "$(parse_header "$task" "Test")" ]; then
        write_result "$slug" "error" 0 0 "task file has no Test: header; bridge.sh run needs a test gate"; return 1
    fi
    if [ -d "$AGENTS_DIR/$slug" ]; then
        write_result "$slug" "error" 0 0 "a worktree for $slug already exists (bridge.sh --cleanup $slug, or use feedback)"; return 1
    fi
    files="$(parse_header "$task" "Files" | tr ',' '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | grep -v '^$' || true)"
    if [ -n "$files" ]; then
        # shellcheck disable=SC2086
        dirty="$(echo "$files" | xargs git status --porcelain -- 2>/dev/null | grep -v '^??' || true)"
        if [ -n "$dirty" ]; then
            write_result "$slug" "error" 0 0 "uncommitted changes in files this task touches; commit or stash them first: $(echo "$dirty" | awk '{print $2}' | tr '\n' ' ')"
            return 1
        fi
    fi
    return 0
}

is_running() {
    local pid
    pid="$(cat "$RESULTS_DIR/$1.pid" 2>/dev/null)" || return 1
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

wait_for() {
    local max_wait="$1"; shift
    local waited=0 pending slug
    while :; do
        pending=0
        for slug in "$@"; do
            [ -f "$RESULTS_DIR/$slug.json" ] || { is_running "$slug" && pending=1; }
        done
        [ "$pending" -eq 0 ] && break
        [ "$waited" -ge "$max_wait" ] && break
        sleep "$POLL_SECONDS"
        waited=$((waited + POLL_SECONDS))
    done
}

report() {
    local slug result status json_lines="" exit_code=0 line
    for slug in "$@"; do
        if [ -f "$RESULTS_DIR/$slug.json" ]; then
            result="$(cat "$RESULTS_DIR/$slug.json")"
        elif is_running "$slug"; then
            result="$(printf '{"slug":"%s","status":"running","message":"still running; call: bridge.sh wait %s"}' "$slug" "$slug")"
        else
            result="$(printf '{"slug":"%s","status":"error","message":"no run in progress or result for this slug"}' "$slug")"
        fi
        status="$(echo "$result" | sed -n 's/.*"status":"\([a-z_]*\)".*/\1/p')"
        line="$(echo "$result" | sed -n 's/.*"backend":"\([^"]*\)","model":"\([^"]*\)","attempts":\([0-9]*\),"duration_s":\([0-9]*\).*/\1 \/ \2, \3 attempt(s), \4s/p')"
        echo "== $slug: $status${line:+ ($line)}"
        case "$status" in
            pass)
                [ -f "$RESULTS_DIR/$slug.diffstat" ] && sed 's/^/ /' "$RESULTS_DIR/$slug.diffstat"
                echo " applied to working tree (uncommitted)" ;;
            running) echo " still running; call: bridge.sh wait $slug"; exit_code=3 ;;
            *)
                echo " $(echo "$result" | sed -n 's/.*"message":"\(.*\)"}$/\1/p')"
                [ -f "$RESULTS_DIR/$slug.tail" ] && sed 's/^/ | /' "$RESULTS_DIR/$slug.tail"
                [ -d "$AGENTS_DIR/$slug" ] && echo " worktree kept: $AGENTS_DIR/$slug"
                [ "$exit_code" -eq 0 ] && exit_code=1 ;;
        esac
        json_lines="${json_lines:+$json_lines,}$result"
    done
    echo "[$json_lines]"
    return "$exit_code"
}

# --- Main ---

cd "$(git rev-parse --show-toplevel 2>/dev/null)" || { echo '[{"status":"error","message":"not inside a git repository"}]'; exit 1; }
mkdir -p "$RESULTS_DIR"

MODE="${1:-}"; shift || true
if [ "$MODE" = "--worker" ]; then
    worker "$1"
    exit 0
fi

MAX_WAIT="$DEFAULT_MAX_WAIT"
SLUGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --max-wait) MAX_WAIT="${2:?--max-wait needs seconds}"; shift 2 ;;
        --max-wait=*) MAX_WAIT="${1#--max-wait=}"; shift ;;
        *) SLUGS+=("$1"); shift ;;
    esac
done
if [ "${#SLUGS[@]}" -eq 0 ]; then
    echo "usage: bridge.sh run|wait <slug>... [--max-wait SECONDS]" >&2
    exit 2
fi

if [ "$MODE" = "run" ]; then
    for slug in "${SLUGS[@]}"; do
        rm -f "$RESULTS_DIR/$slug".*
        validate "$slug" || continue
        nohup "$0" --worker "$slug" > "$RESULTS_DIR/$slug.worker.log" 2>&1 &
        echo $! > "$RESULTS_DIR/$slug.pid"
    done
elif [ "$MODE" != "wait" ]; then
    echo "usage: bridge.sh run|wait <slug>... [--max-wait SECONDS]" >&2
    exit 2
fi

wait_for "$MAX_WAIT" "${SLUGS[@]}"
report "${SLUGS[@]}"
