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
