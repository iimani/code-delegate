#!/bin/bash
# ~/.claude/skills/opencode-delegate/bridge.sh
# Embedded execution bridge for the opencode-delegate skill

TASK_FILE=".local_task.md"
FEEDBACK_FILE=".local_feedback.md"

# 1. Determine which instruction file to look for locally
if [ -f "$FEEDBACK_FILE" ]; then
    INSTRUCTION_FILE="$FEEDBACK_FILE"
    echo "🔄 Processing Claude's feedback loop..."
elif [ -f "$TASK_FILE" ]; then
    INSTRUCTION_FILE="$TASK_FILE"
    echo "🚀 Processing fresh architecture spec..."
else
    echo "❌ Error: Neither $TASK_FILE nor $FEEDBACK_FILE found in the current folder."
    exit 1
fi

# 2. Git Safety Checkpoint (Runs seamlessly if the current folder is a repo)
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    CURRENT_BRANCH=$(git branch --show-current)
    BACKUP_BRANCH="opencode-backup-$(date +%s)"
    
    echo "🛡️ Git detected. Creating safety checkpoint branch: $BACKUP_BRANCH"
    git checkout -b "$BACKUP_BRANCH"
    git add .
    git commit -m "Pre-OpenCode execution backup" --allow-empty
    git checkout "$CURRENT_BRANCH"
else
    echo "⚠️ Not a Git repository. Skipping safety backup..."
fi

# 3. Trigger OpenCode
echo "💻 Invoking OpenCode via LM Studio..."
opencode run "Read $INSTRUCTION_FILE and implement or fix the requested code directly in the workspace."

# 4. Clean up temporary state files
rm -f "$TASK_FILE" "$FEEDBACK_FILE"

echo "✅ OpenCode execution finished. Handing control back to Claude Code."

