---
name: backends
description: List installed code-delegate backends, their availability, models, and capabilities
trigger: /code-delegate:backends
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
