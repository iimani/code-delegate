#!/bin/bash
# code-delegate/tests/hooks/run.sh
#
# Tests for hooks/session-end-cleanup.sh: an idle delegate worktree is removed only
# when its branch is merged and it has no uncommitted or untracked work.
#
# Usage: tests/hooks/run.sh

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOOK="$REPO_ROOT/hooks/session-end-cleanup.sh"
WORK="$(mktemp -d)"
[ -n "${KEEP:-}" ] && echo "work: $WORK" || trap 'rm -rf "$WORK"' EXIT
FAILED=0

check() {
    if [ "$2" = "$3" ]; then echo "ok    $1"; else echo "FAIL  $1: expected $3, got $2"; FAILED=1; fi
}

OLD="$(date -v-2d +%Y%m%d%H%M 2>/dev/null || date -d '2 days ago' +%Y%m%d%H%M)"

cd "$WORK" || exit 1
git init -q -b main repo && cd repo || exit 1
git config user.email t@localhost && git config user.name t
echo base > README.md && git add -A && git commit -qm seed

# add_worktree <slug> <merged:yes|no> <age:old|new> <dirty:yes|no>
add_worktree() {
    local slug="$1" merged="$2" age="$3" dirty="$4" wt=".git/worktrees_agents/$1"
    git worktree add -q "$wt" -b "delegate/$slug"
    echo "$slug" > "$wt/$slug.txt"
    git -C "$wt" add "$slug.txt" && git -C "$wt" commit -qm "$slug"
    [ "$merged" = yes ] && git merge -q --no-ff --no-edit "delegate/$slug"
    [ "$dirty" = yes ] && echo "unfinished" > "$wt/wip.txt"
    echo "log" > "$wt/agent.log"
    [ "$age" = old ] && touch -t "$OLD" "$wt/agent.log"
    return 0
}

add_worktree merged-clean-old yes old no
add_worktree merged-dirty-old yes old yes
add_worktree unmerged-clean-old no old no
add_worktree merged-clean-new yes new no

mkdir -p sub && cd sub || exit 1   # the hook must work from a subdirectory too
output="$("$BASH" "$HOOK" 2>&1)"
cd .. || exit 1

exists() { [ -d ".git/worktrees_agents/$1" ] && echo kept || echo removed; }
check "merged, clean, idle worktree is removed" "$(exists merged-clean-old)" removed
check "merged but uncommitted work is kept" "$(exists merged-dirty-old)" kept
check "unmerged idle worktree is kept" "$(exists unmerged-clean-old)" kept
check "recently active worktree is kept" "$(exists merged-clean-new)" kept
check "uncommitted work still on disk" "$(cat .git/worktrees_agents/merged-dirty-old/wip.txt 2>/dev/null)" unfinished
echo "$output" | grep -q "kept (has uncommitted changes): merged-dirty-old" && r=yes || r=no
check "reports why a worktree was kept" "$r" yes

exit "$FAILED"
