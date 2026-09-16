---
name: status
description: This skill should be used when the user asks what delegated agents are running, wants progress on background coding tasks, or asks about active worktrees. Trigger phrases include "what's running", "check agent status", "show active agents", "is the delegate done yet", "what worktrees are open". Shows active code-delegate agent worktrees, their backends, branches, and last log line.
allowed-tools:
  - Bash
---

# Code Delegate Status

Show the user what code-delegate agents are currently running or have completed.

Run: `bridge.sh --status`

Present the output in a clean table format to the user showing:
- Slug and branch name
- Which backend was used
- Last line of the agent log
