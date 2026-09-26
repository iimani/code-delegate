#!/bin/bash
# code-delegate/tests/bridge/run.sh
#
# Tests for the fast path (`bridge.sh run` / `bridge.sh wait`) using a scripted
# fake backend, so no LLM or agent CLI is needed. Each test runs against a
# throwaway copy of the plugin and a throwaway git repository.
#
# Usage: tests/bridge/run.sh [test-name...]

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="$(mktemp -d)"
if [ -n "${BRIDGE_TEST_KEEP:-}" ]; then
    echo "keeping test workspace: $WORK"
else
    trap 'rm -rf "$WORK"' EXIT
fi
PASSED=0
FAILED=0
FAILURES=()

# --- fixtures ---

make_plugin() {
    local dest="$WORK/plugin"
    [ -d "$dest" ] && return
    mkdir -p "$dest"
    cp -R "$REPO_ROOT/bin" "$REPO_ROOT/backends" "$dest/"
    mkdir -p "$dest/backends/fake"
    cat > "$dest/backends/fake/config.yaml" <<'EOF'
name: fake
description: Scripted test backend
check_command: "true"
default_model: fake
models:
  - alias: fake
    id: fake
    description: "scripted"
    security_ok: false
capabilities:
  - single-file
tags:
  security_ok: false
  cross_file: true
  type_reasoning: false
cost_tier: free
EOF
    # Behaviour comes from the task body's "Behaviour:" line:
    #   good        write the correct file and commit it
    #   good-nocommit  write the correct file, leave it uncommitted
    #   fixround    wrong first, correct in feedback mode
    #   bad         always wrong
    #   nothing     change nothing
    #   slow        sleep 12 s, then correct
    cat > "$dest/backends/fake/run.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
WORKTREE="$1"; SPEC="$2"; MODE="$4"
cd "$WORKTREE"
behaviour="$(grep -m1 '^Behaviour:' ".local_task.md" 2>/dev/null | sed 's/^Behaviour:[[:space:]]*//' || true)"
[ -n "$behaviour" ] || behaviour="$(cat .fake_behaviour 2>/dev/null || echo good)"
echo "$behaviour" > .fake_behaviour
target="$(grep -m1 '^Target:' ".local_task.md" 2>/dev/null | sed 's/^Target:[[:space:]]*//' || cat .fake_target)"
echo "$target" > .fake_target
echo "[fake] mode=$MODE behaviour=$behaviour target=$target"
case "$behaviour" in
    good) echo ok > "$target"; git add "$target"; git commit -qm "fake: $target" ;;
    good-nocommit) echo ok > "$target" ;;
    fixround) if [ "$MODE" = "feedback" ]; then echo ok > "$target"; else echo wrong > "$target"; fi ;;
    bad) echo wrong > "$target" ;;
    nothing) : ;;
    slow) sleep 12; echo ok > "$target" ;;
esac
EOF
    chmod +x "$dest/backends/fake/run.sh"
}

new_repo() {
    local repo="$WORK/repo-$1"
    rm -rf "$repo"
    mkdir -p "$repo"
    cd "$repo" || exit 1
    git init -q
    git config user.email test@localhost
    git config user.name test
    printf 'base\n' > README.md
    printf '.fake_*\n' > .gitignore
    git add -A && git commit -qm seed
}

# write_task <slug> <behaviour> <target> [extra header lines...]
write_task() {
    local slug="$1" behaviour="$2" target="$3"; shift 3
    {
        echo "---"
        echo "Branch: t/$slug"
        echo "Backend: fake"
        echo "Test: grep -qx ok $target"
        echo "StallTimeout: 60"
        for extra in "$@"; do echo "$extra"; done
        echo "---"
        echo "Behaviour: $behaviour"
        echo "Target: $target"
    } > ".local_task_${slug}.md"
}

bridge() { "$WORK/plugin/bin/bridge.sh" "$@"; }

# --- assertions ---

CURRENT=""
fail() { echo "      $CURRENT: $*" >&2; return 1; }
assert_eq() { [ "$1" = "$2" ] || fail "expected '$2', got '$1' ($3)"; }
assert_contains() { echo "$1" | grep -qF -- "$2" || fail "output lacks '$2' ($3)"; }
json_status() { echo "$1" | tail -1 | sed -n "s/.*\"slug\":\"$2\",\"status\":\"\\([a-z_]*\\)\".*/\\1/p"; }

# --- tests ---

test_pass_applies_uncommitted() {
    new_repo pass; write_task a good out.txt
    local out code; out="$(bridge run a)"; code=$?
    assert_eq "$code" 0 "exit code" &&
    assert_eq "$(json_status "$out" a)" pass "status" &&
    assert_eq "$(cat out.txt 2>/dev/null)" ok "file applied" &&
    assert_eq "$(git status --porcelain -- out.txt)" "?? out.txt" "uncommitted" &&
    assert_eq "$(git log --oneline | wc -l | tr -d ' ')" 1 "no commit added" &&
    { [ ! -d .git/worktrees_agents/a ] || fail "worktree not removed"; } &&
    { ! git show-ref --verify --quiet refs/heads/t/a || fail "branch not deleted"; } &&
    assert_contains "$out" "out.txt" "diffstat"
}

test_uncommitted_delegate_work_is_applied() {
    new_repo nocommit; write_task a good-nocommit out.txt
    local out; out="$(bridge run a)"
    assert_eq "$(json_status "$out" a)" pass "status" &&
    assert_eq "$(cat out.txt 2>/dev/null)" ok "file applied"
}

test_fix_round() {
    new_repo fix; write_task a fixround out.txt
    local out; out="$(bridge run a)"
    assert_eq "$(json_status "$out" a)" pass "status" &&
    assert_contains "$out" '"attempts":2' "two attempts" &&
    assert_eq "$(cat out.txt 2>/dev/null)" ok "fixed file applied"
}

test_fail_twice_keeps_worktree() {
    new_repo bad; write_task a bad out.txt
    local out code; out="$(bridge run a)"; code=$?
    assert_eq "$code" 1 "exit code" &&
    assert_eq "$(json_status "$out" a)" fail "status" &&
    assert_contains "$out" '"attempts":2' "fix round attempted" &&
    assert_contains "$out" "worktree kept" "worktree kept" &&
    { [ ! -f out.txt ] || fail "failed change was applied"; }
}

test_missing_test_gate() {
    new_repo notest
    printf -- '---\nBranch: t/a\nBackend: fake\n---\nBehaviour: good\nTarget: out.txt\n' > .local_task_a.md
    local out; out="$(bridge run a)"
    assert_eq "$(json_status "$out" a)" error "status" &&
    assert_contains "$out" "Test:" "explains"
}

test_no_changes() {
    new_repo nothing; printf 'ok\n' > out.txt; git add out.txt; git commit -qm pre
    write_task a nothing out.txt
    local out; out="$(bridge run a)"
    assert_eq "$(json_status "$out" a)" no_changes "status"
}

test_max_wait_then_wait() {
    new_repo slow; write_task a slow out.txt
    local out code; out="$(bridge run a --max-wait 2)"; code=$?
    assert_eq "$code" 3 "run exit code while running" &&
    assert_eq "$(json_status "$out" a)" running "status while running" &&
    out="$(bridge wait a --max-wait 60)" && code=$? &&
    assert_eq "$code" 0 "wait exit code" &&
    assert_eq "$(json_status "$out" a)" pass "status after wait" &&
    assert_eq "$(cat out.txt 2>/dev/null)" ok "applied after wait"
}

test_parallel() {
    new_repo parallel; write_task a good one.txt; write_task b fixround two.txt
    local out; out="$(bridge run a b)"
    assert_eq "$(json_status "$out" a)" pass "a" &&
    assert_eq "$(json_status "$out" b)" pass "b" &&
    assert_eq "$(cat one.txt two.txt 2>/dev/null | tr '\n' ' ')" "ok ok " "both applied"
}

test_dirty_listed_file_refused() {
    new_repo dirty; printf 'mine\n' > out.txt; git add out.txt; git commit -qm pre; printf 'edited\n' > out.txt
    write_task a good out.txt "Files: out.txt"
    local out; out="$(bridge run a)"
    assert_eq "$(json_status "$out" a)" error "status" &&
    assert_contains "$out" "uncommitted changes" "explains" &&
    assert_eq "$(cat out.txt)" edited "local edit untouched"
}

test_apply_conflict() {
    new_repo conflict; printf 'base\n' > out.txt; git add out.txt; git commit -qm pre
    write_task a slow out.txt
    bridge run a --max-wait 1 >/dev/null
    printf 'local change\n' > out.txt      # user edits the file while the delegate works
    local out; out="$(bridge wait a --max-wait 60)"
    assert_eq "$(json_status "$out" a)" apply_conflict "status" &&
    assert_eq "$(cat out.txt)" "local change" "local edit untouched" &&
    assert_contains "$out" "worktree kept" "worktree kept for manual merge"
}

# --- runner ---

ALL_TESTS=(test_pass_applies_uncommitted test_uncommitted_delegate_work_is_applied test_fix_round
           test_fail_twice_keeps_worktree test_missing_test_gate test_no_changes test_max_wait_then_wait
           test_parallel test_dirty_listed_file_refused test_apply_conflict)
[ $# -gt 0 ] && ALL_TESTS=("$@")

make_plugin
for t in "${ALL_TESTS[@]}"; do
    CURRENT="$t"
    if ( "$t" ); then
        PASSED=$((PASSED + 1)); echo "ok    $t"
    else
        FAILED=$((FAILED + 1)); echo "FAIL  $t"
    fi
done
echo ""
echo "$PASSED passed, $FAILED failed"
[ "$FAILED" -eq 0 ]
