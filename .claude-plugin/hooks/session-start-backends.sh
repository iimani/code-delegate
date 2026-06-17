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
  exit 0
fi

"$BRIDGE_CMD" --backends 2>&1 | while IFS= read -r line; do
  echo "[code-delegate] $line" >&2
done

exit 0
