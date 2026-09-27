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

# opencode keeps its session state in a local SQLite database. Several
# `opencode run` processes starting at the same moment (parallel dispatch)
# can fail immediately with "database is locked". Retry those quick
# failures a few times with a jittered backoff; anything else, or a failure
# after the agent has been working for a while, is passed through as-is.
# The runner stays the parent, so forward the watcher's SIGTERM to opencode.
run_with_lock_retry() {
    local attempt=1 max_attempts=4 started status output_copy fifo child tee_pid
    output_copy="$(mktemp)"
    fifo="$(mktemp -u)"
    while :; do
        started=$(date +%s)
        # Output goes through a named pipe to tee: live in the log, and a copy
        # we can inspect once tee has finished (bash 3.2 can't wait on >(...)).
        mkfifo "$fifo"
        tee "$output_copy" < "$fifo" &
        tee_pid=$!
        "$@" > "$fifo" 2>&1 &
        child=$!
        trap 'kill -TERM "$child" 2>/dev/null; wait "$child" 2>/dev/null; wait "$tee_pid" 2>/dev/null; rm -f "$fifo" "$output_copy"; exit 143' TERM INT
        status=0
        wait "$child" || status=$?   # runner uses set -e; a failed wait must not exit here
        wait "$tee_pid" || true
        rm -f "$fifo"
        trap - TERM INT
        if [ "$status" -ne 0 ] && [ "$attempt" -lt "$max_attempts" ] \
            && [ $(( $(date +%s) - started )) -lt 60 ] && grep -q "database is locked" "$output_copy"; then
            local delay=$(( attempt * 3 + RANDOM % 5 ))
            echo "[opencode runner] database is locked (attempt ${attempt}/${max_attempts}); retrying in ${delay}s"
            sleep "$delay"
            attempt=$(( attempt + 1 ))
            : > "$output_copy"
            continue
        fi
        rm -f "$output_copy"
        return "$status"
    done
}

# Opt-in usage accounting (set by tests/benchmark, never by normal delegation):
# --format json emits per-step token counts; usage_wrap.py keeps the log
# readable and appends this run's usage to $CODE_DELEGATE_USAGE_LOG.
if [ -n "${CODE_DELEGATE_USAGE_LOG:-}" ]; then
    PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
    run_with_lock_retry python3 "$PLUGIN_ROOT/lib/usage_wrap.py" --format opencode-json \
        --backend opencode --model "$MODEL" --log "$CODE_DELEGATE_USAGE_LOG" -- \
        "${CMD[@]}" --format json "$PROMPT_TEXT"
else
    run_with_lock_retry "${CMD[@]}" "$PROMPT_TEXT"
fi
