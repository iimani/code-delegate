#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCENARIOS_DIR="$SCRIPT_DIR/scenarios"
SKILL_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TIMEOUT="${WORKFLOW_TEST_TIMEOUT:-120}"

GLOBAL_CLAUDE_MD="$HOME/.claude/CLAUDE.md"
if [[ ! -f "$GLOBAL_CLAUDE_MD" ]]; then
  echo "Installing CLAUDE.md to $GLOBAL_CLAUDE_MD"
  cp "$SKILL_ROOT/CLAUDE.md" "$GLOBAL_CLAUDE_MD"
fi

SKILL_DEST="$HOME/.claude/skills/opencode-delegate"
if [[ ! -d "$SKILL_DEST" ]]; then
  echo "Installing skill to $SKILL_DEST"
  cp -r "$SKILL_ROOT" "$SKILL_DEST"
fi

if ! command -v claude &>/dev/null; then
  echo "FATAL: claude CLI not found in PATH" >&2
  exit 1
fi

RESULTS_DIR="$SCRIPT_DIR/results"
mkdir -p "$RESULTS_DIR"
find "$RESULTS_DIR" -name "*.out" -delete

passed=0
failed=0
total=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
RESET='\033[0m'

run_scenario() {
  local scenario_file="$1"
  local name
  name="$(basename "$scenario_file" .txt)"

  local description="" prompt=""
  local -a expects=() forbids=()

  while IFS= read -r line; do
    case "$line" in
      DESCRIPTION:*) description="${line#DESCRIPTION: }" ;;
      PROMPT:*) prompt="${line#PROMPT: }" ;;
      EXPECT:*) expects+=("${line#EXPECT: }") ;;
      FORBID:*) forbids+=("${line#FORBID: }") ;;
    esac
  done < "$scenario_file"

  if [[ -z "$prompt" ]]; then
    echo -e "${YELLOW}SKIP${RESET} $name — no PROMPT defined"
    return 0
  fi

  echo -e "${BOLD}RUN${RESET}  $name: $description"

  local output_file="$RESULTS_DIR/$name.out"

  timeout "${TIMEOUT}s" claude --print "$prompt" > "$output_file" 2>&1
  local exit_code=$?
  if [[ $exit_code -ne 0 ]]; then
    if [[ $exit_code -eq 124 ]]; then
      echo -e "  ${RED}TIMEOUT${RESET} after ${TIMEOUT}s"
    else
      echo -e "  ${RED}ERROR${RESET} claude --print failed (exit $exit_code)"
    fi
    echo -e "  Output: $(head -3 "$output_file" 2>/dev/null)"
    failed=$((failed + 1))
    return 0
  fi

  local scenario_passed=true
  local -a failures=()

  for pattern in "${expects[@]}"; do
    if ! grep -qi "$pattern" "$output_file"; then
      scenario_passed=false
      failures+=("EXPECT missing: '$pattern'")
    fi
  done

  for pattern in "${forbids[@]}"; do
    if grep -qi "$pattern" "$output_file"; then
      scenario_passed=false
      local match
      match="$(grep -i "$pattern" "$output_file" | head -1)"
      failures+=("FORBID found: '$pattern' → $match")
    fi
  done

  if $scenario_passed; then
    echo -e "  ${GREEN}PASS${RESET}"
    passed=$((passed + 1))
  else
    echo -e "  ${RED}FAIL${RESET}"
    for f in "${failures[@]}"; do
      echo -e "    $f"
    done
    echo -e "  Full output: $output_file"
    failed=$((failed + 1))
  fi
}

echo ""
echo "================================================"
echo " opencode-delegate workflow validation"
echo "================================================"
echo ""

for scenario_file in "$SCENARIOS_DIR"/*.txt; do
  [[ -f "$scenario_file" ]] || continue
  total=$((total + 1))
  run_scenario "$scenario_file"
  echo ""
done

echo "================================================"
if [[ $failed -eq 0 ]]; then
  echo -e " ${GREEN}ALL $total SCENARIOS PASSED${RESET}"
else
  echo -e " ${RED}$failed/$total FAILED${RESET}, $passed passed"
fi
echo "================================================"

[[ $failed -eq 0 ]]
