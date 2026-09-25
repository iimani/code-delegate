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

# Opt-in usage accounting (set by tests/benchmark, never by normal delegation):
# stream JSON events through usage_wrap.py, which keeps the log readable and
# appends this run's token usage to $CODE_DELEGATE_USAGE_LOG.
if [ -n "${CODE_DELEGATE_USAGE_LOG:-}" ]; then
    PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
    exec python3 "$PLUGIN_ROOT/lib/usage_wrap.py" --format claude-stream \
        --backend claude --model "$MODEL" --log "$CODE_DELEGATE_USAGE_LOG" -- \
        "${CMD[@]}" --output-format stream-json "$PROMPT_TEXT"
fi

exec "${CMD[@]}" "$PROMPT_TEXT"
