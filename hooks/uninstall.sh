#!/bin/bash
set -euo pipefail

SETTINGS="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"

if ! command -v python3 &>/dev/null; then
  echo "Error: python3 required but not found." >&2
  exit 1
fi

if [[ ! -f "$SETTINGS" ]]; then
  echo "Nothing to uninstall."
  exit 0
fi

cp "$SETTINGS" "${SETTINGS}.bak"

python3 - "$SETTINGS" <<'PYEOF'
import json, sys

settings_path = sys.argv[1]
MARKERS = ("code-delegate", "session-start-backends", "pre-bridge-validate", "session-end-cleanup")

def is_delegate_entry(entry):
    for hk in entry.get("hooks", []):
        cmd = hk.get("command", "")
        if any(m in cmd for m in MARKERS):
            return True
    return False

with open(settings_path) as f:
    settings = json.load(f)

hooks = settings.get("hooks", {})
for event in list(hooks.keys()):
    hooks[event] = [e for e in hooks[event] if not is_delegate_entry(e)]
    if not hooks[event]:
        del hooks[event]

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
PYEOF

echo "code-delegate hooks removed. Restart Claude Code to deactivate."
