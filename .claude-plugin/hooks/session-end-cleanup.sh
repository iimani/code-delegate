#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CANDIDATE_1="$SCRIPT_DIR/../bin/bridge.sh"
CANDIDATE_2="$HOME/.claude/plugins/marketplaces/code-delegate/bin/bridge.sh"

if [[ -x "$CANDIDATE_1" ]]; then
  BRIDGE_CMD="$CANDIDATE_1"
elif [[ -x "$CANDIDATE_2" ]]; then
  BRIDGE_CMD="$CANDIDATE_2"
else
  BRIDGE_CMD=""
fi

GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
if [[ -z "$GIT_ROOT" ]]; then
  exit 0
fi

AGENTS_DIR="$GIT_ROOT/.git/worktrees_agents"
if [[ ! -d "$AGENTS_DIR" ]]; then
  exit 0
fi

shopt -s nullglob
dirs=("$AGENTS_DIR"/*)
shopt -u nullglob

if [[ ${#dirs[@]} -eq 0 ]]; then
  exit 0
fi

STALE_HOURS=8
NOW=$(date +%s)

for dir in "${dirs[@]}"; do
  [[ -d "$dir" ]] || continue
  slug=$(basename "$dir")
  branch=$(git -C "$dir" branch --show-current 2>/dev/null || echo "unknown")

  stale=false
  log_age=0

  if [[ -f "$dir/agent.log" ]]; then
    log_mtime=$(stat -f %m "$dir/agent.log" 2>/dev/null || stat -c %Y "$dir/agent.log" 2>/dev/null || echo "$NOW")
    log_age=$(( NOW - log_mtime ))
    if (( log_age > STALE_HOURS * 3600 )); then
      stale=true
    fi
  fi

  merged=false
  if [[ -n "$branch" && "$branch" != "unknown" ]]; then
    if git -C "$GIT_ROOT" branch --merged main 2>/dev/null | grep -qF "$branch"; then
      merged=true
    fi
  fi

  if $stale && { $merged || (( log_age > 24 * 3600 )); }; then
    echo "[code-delegate] Cleaning up stale worktree: $slug (branch: $branch)" >&2
    if [[ -n "$BRIDGE_CMD" ]]; then
      "$BRIDGE_CMD" --cleanup "$slug" >/dev/null 2>&1 || true
    fi
  elif $stale; then
    echo "[code-delegate] Stale worktree (no recent activity): $slug -> $branch" >&2
  else
    echo "[code-delegate] Active worktree: $slug -> $branch" >&2
  fi
done

exit 0
