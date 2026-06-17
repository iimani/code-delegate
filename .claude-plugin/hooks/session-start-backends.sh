#!/bin/bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CANDIDATE_1="$SCRIPT_DIR/../bin/bridge.sh"
CANDIDATE_2="$HOME/.claude/plugins/marketplaces/code-delegate/bin/bridge.sh"
CANDIDATE_3="$HOME/.claude/plugins/cache/code-delegate/code-delegate/*/bin/bridge.sh"

BRIDGE_CMD=""
for candidate in "$CANDIDATE_1" "$CANDIDATE_2" $CANDIDATE_3; do
  if [[ -x "$candidate" ]]; then
    BRIDGE_CMD="$candidate"
    break
  fi
done
[[ -n "$BRIDGE_CMD" ]] || exit 0

"$BRIDGE_CMD" --backends 2>&1 | sed 's/^/[code-delegate] /' >&2 || true

exit 0
