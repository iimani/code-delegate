#!/bin/bash
# Dry-run backend: applies the task's reference solution ($BENCH_DRYRUN_SOLUTION)
# and commits it, then records a synthetic usage entry like the real runners do.
set -euo pipefail

WORKTREE_PATH="$1"
MODEL="$3"

cd "$WORKTREE_PATH"
echo "[fake] applying reference solution from ${BENCH_DRYRUN_SOLUTION:?}"
cp -R "${BENCH_DRYRUN_SOLUTION}/." .
git add -A -- . ':!.local_task.md' ':!.local_feedback.md' ':!agent.log' ':!.bridge_backend' ':!.bridge_abort' 2>/dev/null || git add -A
git commit -q -m "fake backend: reference solution" || true
echo "[tool] write"

if [ -n "${CODE_DELEGATE_USAGE_LOG:-}" ]; then
    printf '{"backend":"fake","model":"%s","exit_code":0,"duration_ms":1,"input_tokens":4000,"output_tokens":800,"reasoning_tokens":0,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"total_cost_usd":0,"num_turns":2,"tool_calls":1,"parsed":true}\n' \
        "${MODEL:-fake}" >> "$CODE_DELEGATE_USAGE_LOG"
fi
