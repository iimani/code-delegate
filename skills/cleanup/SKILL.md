---
name: cleanup
description: Remove a code-delegate agent worktree after its branch has been approved or merged
argument-hint: <slug> — the branch slug to clean up
trigger: /code-delegate:cleanup
allowed-tools:
  - Bash
---

# Code Delegate Cleanup

Remove an agent worktree after its branch has been reviewed and merged.

The user provides a slug (e.g., `feat-logger`).

Before cleanup:
1. Check if the branch has been merged: `git branch --merged "$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|.*/||' || echo main)" | grep <branch>`
2. If not merged, warn the user and ask for confirmation
3. If merged, proceed

Run: `bridge.sh --cleanup <slug>`

Confirm removal to the user.
