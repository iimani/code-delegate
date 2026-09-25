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

# Opt-in usage accounting (set by tests/benchmark, never by normal delegation):
# --format json emits per-step token counts; usage_wrap.py keeps the log
# readable and appends this run's usage to $CODE_DELEGATE_USAGE_LOG.
if [ -n "${CODE_DELEGATE_USAGE_LOG:-}" ]; then
    PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
    exec python3 "$PLUGIN_ROOT/lib/usage_wrap.py" --format opencode-json \
        --backend opencode --model "$MODEL" --log "$CODE_DELEGATE_USAGE_LOG" -- \
        "${CMD[@]}" --format json "$PROMPT_TEXT"
fi

exec "${CMD[@]}" "$PROMPT_TEXT"
