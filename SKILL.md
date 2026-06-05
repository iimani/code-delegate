---
global: true
description: Delegate code implementation, heavy boilerplate generation, or bug fixes to a local OpenCode/LM Studio instance, and automatically manage Git safety checkpoints.
---

# OpenCode Delegation Skill

This global skill allows Claude Code to act as a high-level Architect and Code Reviewer, offloading token-heavy coding tasks to a local OpenCode instance running on top of LM Studio.

## Usage
When the user asks you to implement a complex plan, write heavy boilerplate, or generate exhaustive test suites, use this skill instead of writing the code yourself.

## Execution Protocol
1. **Plan**: Formulate your architectural plan and display it to the user.
2. **Write Spec**: Save your exact implementation instructions into a file named `.local_task.md` in the current working directory.
3. **Execute Handoff**: Run the local bridge tool by executing this precise terminal command:
   `~/.claude/skills/opencode-delegate/bridge.sh`
4. **Review**: Once the command finishes, read the modified files in the directory.
5. **Fix Loop**: If the local model introduced bugs, write the required corrections into `.local_feedback.md` in the current working directory and run `~/.claude/skills/opencode-delegate/bridge.sh` again.

## Notes
- Do not write massive blocks of code directly if this skill is available.
- Always use the exact path `~/.claude/skills/opencode-delegate/bridge.sh` to run the tool.

