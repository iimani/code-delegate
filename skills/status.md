---
name: status
description: Show active delegate agent worktrees, their backends, branches, and last log line
---

# Delegate Status

Show the user what delegate agents are currently running or have completed.

Run: `bridge.sh --status`

Present the output in a clean table format to the user showing:
- Slug and branch name
- Which backend was used
- Last line of the agent log
