#!/bin/bash
set -uo pipefail

INPUT=$(cat)

CMD=$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null <<< "$INPUT" || echo "")

if [[ "$CMD" != *"bridge.sh"* ]]; then
  exit 0
fi

# Extract words after bridge.sh token
AFTER_BRIDGE=$(echo "$CMD" | sed 's/.*bridge\.sh//' | xargs)
FIRST_ARG=$(echo "$AFTER_BRIDGE" | awk '{print $1}')

if [[ -z "$FIRST_ARG" || "$FIRST_ARG" == --* ]]; then
  exit 0
fi

SLUG="$FIRST_ARG"
TASK_FILE=".local_task_${SLUG}.md"

if [[ ! -f "$TASK_FILE" ]]; then
  exit 0
fi

if grep -qm1 "^Branch:" "$TASK_FILE" 2>/dev/null; then
  exit 0
fi

echo "[code-delegate] Task file '$TASK_FILE' is missing required 'Branch:' header." >&2
echo "[code-delegate] Add 'Branch: feat/your-branch-name' to the YAML frontmatter." >&2
echo "{\"decision\":\"block\",\"reason\":\"Task file '${TASK_FILE}' is missing required 'Branch:' header. Add 'Branch: feat/your-branch-name' to the YAML frontmatter.\"}"
exit 2
