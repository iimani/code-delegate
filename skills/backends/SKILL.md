---
name: backends
description: This skill should be used when the user asks which delegation backends or models are available, whether a CLI (opencode/claude/codex) is installed, or wants to compare backend capabilities/cost before delegating. Trigger phrases include "what backends do I have", "list available models", "is opencode installed", "which backend should I use". Lists installed code-delegate backends, their availability, models, and capabilities.
allowed-tools:
  - Bash
---

# Code Delegate Backends

List all available delegation backends and their status.

Run: `bridge.sh --backends`

Present the output as a formatted table:

| Backend  | Available | Cost | Capabilities                     |
|----------|-----------|------|----------------------------------|
| opencode | yes       | free | single-file, boilerplate, crud   |
| claude   | yes       | paid | cross-file, type-reasoning, ...  |
| codex    | no        | paid | single-file, boilerplate         |

If a backend is unavailable, note which CLI command is missing.
