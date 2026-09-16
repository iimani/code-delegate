#!/usr/bin/env bash
# code-delegate/tests/benchmark/run.sh
#
# Measures the orchestrator-side cost/token impact of delegating a task via
# code-delegate vs. implementing it directly, using `claude --print
# --output-format json` for structured usage data. Each condition runs in
# its own scratch git repo and its own isolated CLAUDE_CONFIG_DIR, so this
# never touches your real ~/.claude config or the code-delegate repo itself.
#
# Usage:
#   ./run.sh                # run all tasks in tasks/
#   ./run.sh 01-single-file-boilerplate   # run one task by filename stem
#
# Env vars:
#   BENCHMARK_TIMEOUT   seconds per condition (default 300)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TASKS_DIR="$SCRIPT_DIR/tasks"
FIXTURE_DIR="$SCRIPT_DIR/fixture"
RESULTS_DIR="$SCRIPT_DIR/results"
TIMEOUT="${BENCHMARK_TIMEOUT:-300}"

if ! command -v claude &>/dev/null; then
  echo "FATAL: claude CLI not found in PATH" >&2
  exit 1
fi
if ! command -v python3 &>/dev/null; then
  echo "FATAL: python3 required to parse --output-format json results" >&2
  exit 1
fi

WORK_BASE="$(mktemp -d)"
trap 'rm -rf "$WORK_BASE"' EXIT

mkdir -p "$RESULTS_DIR"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
RUN_RESULTS_DIR="$RESULTS_DIR/$RUN_ID"
mkdir -p "$RUN_RESULTS_DIR"

setup_scratch_repo() {
  local dest="$1"
  rm -rf "$dest"
  mkdir -p "$dest"
  cp -r "$FIXTURE_DIR"/. "$dest"/
  git -C "$dest" init -q -b main
  git -C "$dest" config user.email "benchmark@localhost"
  git -C "$dest" config user.name "code-delegate-benchmark"
  git -C "$dest" add -A
  git -C "$dest" commit -q -m "seed"
}

# Installs the code-delegate CLAUDE.md + skill into an isolated
# CLAUDE_CONFIG_DIR — never the real $HOME/.claude — so the "with-skill"
# condition sees the plugin's delegation directive without mutating your
# actual global Claude Code config.
install_delegate_config() {
  local config_dir="$1"
  mkdir -p "$config_dir/skills"
  cp "$REPO_ROOT/CLAUDE.md" "$config_dir/CLAUDE.md"
  cp -r "$REPO_ROOT" "$config_dir/skills/code-delegate"
}

run_condition() {
  local repo="$1" claude_config_dir="$2" prompt_file="$3" out_json="$4" extra_path="${5:-}"
  local prompt
  prompt="$(cat "$prompt_file")"
  (
    cd "$repo" || exit 1
    export CLAUDE_CONFIG_DIR="$claude_config_dir"
    if [ -n "$extra_path" ]; then
      export PATH="$extra_path:$PATH"
    fi
    # Matches backends/claude/run.sh's own flag so this harness measures real
    # production behavior. --permission-mode acceptEdits is NOT a substitute:
    # testing showed it silently denies `git commit` (still exits 0, still
    # reports success) while approving file edits — see README's Limitations
    # section. --dangerously-skip-permissions refuses to run as root, so this
    # harness needs a non-root environment (see README).
    timeout "${TIMEOUT}s" claude --print --output-format json --dangerously-skip-permissions "$prompt"
  ) > "$out_json" 2> "${out_json}.log"
}

extract_metrics() {
  local json_file="$1" label="$2"
  python3 - "$json_file" "$label" <<'PYEOF'
import json, sys

path, label = sys.argv[1], sys.argv[2]
try:
    with open(path) as f:
        data = json.load(f)
except Exception as e:
    print(json.dumps({"label": label, "error": f"could not parse output: {e}"}))
    sys.exit(0)

usage = data.get("usage", {})
print(json.dumps({
    "label": label,
    "is_error": data.get("is_error"),
    "num_turns": data.get("num_turns"),
    "duration_ms": data.get("duration_ms"),
    "total_cost_usd": data.get("total_cost_usd"),
    "input_tokens": usage.get("input_tokens"),
    "output_tokens": usage.get("output_tokens"),
    "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
    "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
}))
PYEOF
}

# Which task stems to run
declare -a STEMS=()
if [ $# -gt 0 ]; then
  STEMS=("$@")
else
  for f in "$TASKS_DIR"/*.txt; do
    [ -f "$f" ] || continue
    STEMS+=("$(basename "$f" .txt)")
  done
fi

echo ""
echo "================================================"
echo " code-delegate benchmark — orchestrator cost impact"
echo " (claude backend only — see README for opencode)"
echo "================================================"
echo ""

ALL_METRICS="[]"

for stem in "${STEMS[@]}"; do
  task_file="$TASKS_DIR/${stem}.txt"
  if [ ! -f "$task_file" ]; then
    echo "SKIP $stem — no task file at $task_file"
    continue
  fi

  echo "--- $stem ---"

  # Baseline: no code-delegate CLAUDE.md/skill, isolated empty config dir.
  baseline_repo="$WORK_BASE/${stem}-baseline"
  baseline_config="$WORK_BASE/${stem}-baseline-config"
  setup_scratch_repo "$baseline_repo"
  mkdir -p "$baseline_config"
  baseline_out="$RUN_RESULTS_DIR/${stem}.baseline.json"
  echo "  running baseline (implement directly)..."
  run_condition "$baseline_repo" "$baseline_config" "$task_file" "$baseline_out"

  # With-skill: code-delegate CLAUDE.md/skill installed, bin/ on PATH so
  # bridge.sh resolves as a bare command (same as the plugin-framework
  # PATH injection a real install gets).
  skill_repo="$WORK_BASE/${stem}-with-skill"
  skill_config="$WORK_BASE/${stem}-with-skill-config"
  setup_scratch_repo "$skill_repo"
  install_delegate_config "$skill_config"
  skill_out="$RUN_RESULTS_DIR/${stem}.with-skill.json"
  echo "  running with-skill (delegate)..."
  run_condition "$skill_repo" "$skill_config" "$task_file" "$skill_out" "$skill_config/skills/code-delegate/bin"

  baseline_metrics="$(extract_metrics "$baseline_out" "baseline")"
  skill_metrics="$(extract_metrics "$skill_out" "with-skill")"

  echo "  baseline:   $baseline_metrics"
  echo "  with-skill: $skill_metrics"
  echo ""

  ALL_METRICS="$(python3 -c "
import json, sys
all_metrics = json.loads(sys.argv[1])
all_metrics.append({'task': sys.argv[2], 'baseline': json.loads(sys.argv[3]), 'with_skill': json.loads(sys.argv[4])})
print(json.dumps(all_metrics))
" "$ALL_METRICS" "$stem" "$baseline_metrics" "$skill_metrics")"
done

echo "$ALL_METRICS" > "$RUN_RESULTS_DIR/summary.json"
python3 - "$RUN_RESULTS_DIR/summary.json" "$RUN_RESULTS_DIR/summary.md" <<'PYEOF'
import json, sys

in_path, out_path = sys.argv[1], sys.argv[2]
with open(in_path) as f:
    rows = json.load(f)

lines = ["# code-delegate benchmark results", "", "| Task | Orchestrator cost (baseline) | Orchestrator cost (with-skill) | Delta | Turns (baseline / with-skill) |", "|---|---|---|---|---|"]
for row in rows:
    b, s = row["baseline"], row["with_skill"]
    bc, sc = b.get("total_cost_usd"), s.get("total_cost_usd")
    delta = f"{sc - bc:+.4f}" if isinstance(bc, (int, float)) and isinstance(sc, (int, float)) else "n/a"
    lines.append(
        f"| {row['task']} | ${bc if bc is not None else 'n/a'} | ${sc if sc is not None else 'n/a'} | {delta} | "
        f"{b.get('num_turns', 'n/a')} / {s.get('num_turns', 'n/a')} |"
    )
lines.append("")
lines.append("Cost is **orchestrator-side only** (the main `claude --print` session in each condition). "
              "The with-skill condition's implementation work happens in a *separate* nested `claude` CLI call "
              "made by `backends/claude/run.sh` inside the isolated worktree — that call's own cost isn't "
              "captured here (it doesn't use `--output-format json`). A positive delta on a task that should "
              "DELEGATE is still the expected/interesting result: it means the orchestrator spent less on "
              "reading/writing/editing code itself, even though total system cost moved rather than vanished. "
              "See README.md for what this does and doesn't measure, including why opencode's real savings "
              "can't be shown by this harness alone.")

with open(out_path, "w") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines))
PYEOF

echo ""
echo "Full results: $RUN_RESULTS_DIR/"
