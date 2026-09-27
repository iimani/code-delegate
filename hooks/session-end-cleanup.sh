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

cd "$GIT_ROOT" || exit 0   # bridge.sh --cleanup resolves worktree paths from the repo root
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

# File modification time in epoch seconds. `date -r` behaves the same with GNU and BSD
# date; `stat -f %m` means something else on Linux (filesystem info) and exits non-zero
# after printing, which corrupted the age calculation.
mtime() {
  date -r "$1" +%s 2>/dev/null || echo "$NOW"
}
# Branches merged into the current branch or main. Strip git's markers: "* " for the
# current branch and "+ " for branches checked out in another worktree (every delegate
# branch is), otherwise no delegate branch would ever match.
MERGED_BRANCHES=$( { git -C "$GIT_ROOT" branch --merged HEAD 2>/dev/null; git -C "$GIT_ROOT" branch --merged main 2>/dev/null; } \
  | sed 's/^[*+ ] //; s/^ *//' | sort -u || true)

for dir in "${dirs[@]}"; do
  [[ -d "$dir" ]] || continue
  slug=$(basename "$dir")
  branch=$(git -C "$dir" branch --show-current 2>/dev/null || echo "unknown")

  stale=false
  log_age=0

  if [[ -f "$dir/agent.log" ]]; then
    log_mtime=$(mtime "$dir/agent.log")
    log_age=$(( NOW - log_mtime ))
    if (( log_age > STALE_HOURS * 3600 )); then
      stale=true
    fi
  else
    dir_mtime=$(mtime "$dir")
    log_age=$(( NOW - dir_mtime ))
    if (( log_age > STALE_HOURS * 3600 )); then
      stale=true
    fi
  fi

  merged=false
  if [[ -n "$branch" && "$branch" != "unknown" ]]; then
    if echo "$MERGED_BRANCHES" | grep -qxF "$branch"; then
      merged=true
    fi
  fi

  # Work that isn't in a merged commit (uncommitted edits, untracked files) is never
  # removed: failed fast-path tasks keep their worktree for the user to finish, and some
  # delegate models never commit. Bridge bookkeeping files don't count.
  dirty=$(git -C "$dir" status --porcelain 2>/dev/null | cut -c4- \
    | grep -vE '^(.*/)?(agent\.log|\.bridge_[a-z]+|\.local_(task|feedback)\.md)$' || true)

  if $stale && $merged && [[ -z "$dirty" ]]; then
    echo "[code-delegate] Removing merged, idle worktree: $slug (branch: $branch)" >&2
    if [[ -n "$BRIDGE_CMD" ]]; then
      "$BRIDGE_CMD" --cleanup "$slug" >/dev/null 2>&1 || true
    fi
  elif $stale; then
    reason="not merged"
    $merged && reason="has uncommitted changes"
    echo "[code-delegate] Idle worktree kept ($reason): $slug -> $branch (remove with: bridge.sh --cleanup $slug)" >&2
  else
    echo "[code-delegate] Active worktree: $slug -> $branch" >&2
  fi
done

exit 0
