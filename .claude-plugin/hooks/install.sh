#!/bin/bash
set -euo pipefail

HOOKS_DIR="$(cd "$(dirname "$0")" && pwd)"
SETTINGS="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"

if ! command -v python3 &>/dev/null; then
  echo "Error: python3 required but not found." >&2
  exit 1
fi

# Check if already installed (skip with --force)
if [[ "$*" != *"--force"* ]] && [[ -f "$SETTINGS" ]]; then
  already=$(python3 - "$SETTINGS" <<'PYEOF'
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
    hooks = data.get("hooks", {})
    events = ["SessionStart", "PreToolUse", "Stop"]
    found = 0
    for ev in events:
        for entry in hooks.get(ev, []):
            for h in entry.get("hooks", []):
                if "code-delegate" in h.get("command", ""):
                    found += 1
                    break
    print("yes" if found >= 3 else "no")
except Exception:
    print("no")
PYEOF
  )
  if [[ "$already" == "yes" ]]; then
    echo "code-delegate hooks already installed. Use --force to reinstall."
    exit 0
  fi
fi

mkdir -p "$(dirname "$SETTINGS")"
[[ -f "$SETTINGS" ]] || echo '{}' > "$SETTINGS"
cp "$SETTINGS" "${SETTINGS}.bak"

python3 - "$SETTINGS" "$HOOKS_DIR" <<'PYEOF'
import json, sys

settings_path = sys.argv[1]
hooks_dir = sys.argv[2]

with open(settings_path) as f:
    settings = json.load(f)

settings.setdefault("hooks", {})
h = settings["hooks"]

# SessionStart
h.setdefault("SessionStart", [])
ss_cmd = f'bash "{hooks_dir}/session-start-backends.sh"'
if not any("code-delegate" in hk.get("command", "") for e in h["SessionStart"] for hk in e.get("hooks", [])):
    h["SessionStart"].append({"hooks": [{"type": "command", "command": ss_cmd, "timeout": 10}]})

# PreToolUse
h.setdefault("PreToolUse", [])
ptu_cmd = f'bash "{hooks_dir}/pre-bridge-validate.sh"'
if not any(
    e.get("matcher") == "Bash" and "code-delegate" in hk.get("command", "")
    for e in h["PreToolUse"]
    for hk in e.get("hooks", [])
):
    h["PreToolUse"].append({"matcher": "Bash", "hooks": [{"type": "command", "command": ptu_cmd, "timeout": 10}]})

# Stop
h.setdefault("Stop", [])
stop_cmd = f'bash "{hooks_dir}/session-end-cleanup.sh"'
if not any("code-delegate" in hk.get("command", "") for e in h["Stop"] for hk in e.get("hooks", [])):
    h["Stop"].append({"hooks": [{"type": "command", "command": stop_cmd, "timeout": 30}]})

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
PYEOF

echo "code-delegate hooks installed."
echo "  SessionStart: session-start-backends.sh"
echo "  PreToolUse (Bash): pre-bridge-validate.sh"
echo "  Stop: session-end-cleanup.sh"
echo "Restart Claude Code to activate."
