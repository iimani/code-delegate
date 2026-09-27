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

# Opt-in usage accounting (tests/benchmark): codex token parsing isn't
# implemented, so only the backend/model/duration record is written.
if [ -n "${CODE_DELEGATE_USAGE_LOG:-}" ]; then
    PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
    exec python3 "$PLUGIN_ROOT/lib/usage_wrap.py" --format none \
        --backend codex --model "$MODEL" --log "$CODE_DELEGATE_USAGE_LOG" -- \
        "${CMD[@]}" "$PROMPT_TEXT"
fi

exec "${CMD[@]}" "$PROMPT_TEXT"
