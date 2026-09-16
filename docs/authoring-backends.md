# Authoring a New Backend

Add a backend by creating a directory under `backends/` with two files:

## Directory structure

```
backends/mybackend/
├── config.yaml    # Metadata and capabilities
└── run.sh         # Execution script
```

## config.yaml

```yaml
name: mybackend
description: Short description of this backend
check_command: command -v mybackend-cli
default_model: default-model-alias
models:
  - alias: fast
    id: mybackend-fast-v1
    description: "Fast, cheap model"
    security_ok: false
  - alias: smart
    id: mybackend-smart-v2
    description: "Capable model for complex tasks"
    security_ok: true
capabilities:
  - single-file
  - boilerplate
  - crud
tags:
  security_ok: false
  cross_file: false
  type_reasoning: false
cost_tier: free
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Backend identifier (matches directory name) |
| `description` | yes | One-line summary |
| `check_command` | yes | Shell command that exits 0 if the CLI is installed |
| `default_model` | no | Alias used when no `Model:` header and no env override is set. Leave empty (`""`) for backends whose models are machine-specific so fresh installs stay portable. |
| `models` | yes | Either a list of alias/id/description objects, or `dynamic` |
| `list_models_command` | no | Shell command to list available models (for `models: dynamic`) |
| `capabilities` | yes | List: `single-file`, `cross-file`, `type-reasoning`, `boilerplate`, `test-generation`, `crud` |
| `tags.security_ok` | yes | Whether any model in this backend is approved for security tasks |
| `tags.cross_file` | yes | Whether the backend handles multi-file tasks |
| `tags.type_reasoning` | yes | Whether the backend handles complex type systems |
| `cost_tier` | yes | `free` or `paid` |

### Dynamic models

For backends where available models depend on runtime (e.g., local LLM servers):

```yaml
models: dynamic
list_models_command: mybackend-cli models 2>/dev/null
```

The bridge passes any `Model:` header value through as-is. Alias resolution is skipped.

When no `Model:` header is set, the bridge resolves the model in this order: the
per-backend env override `<BACKEND>_DELEGATE_MODEL` (e.g. `OPENCODE_DELEGATE_MODEL`),
then the config `default_model`, then empty — in which case `run.sh` omits `--model`
and the CLI uses its own default. This lets users pin a machine-local default without
committing it.

## run.sh

```bash
#!/bin/bash
set -euo pipefail

WORKTREE_PATH="$1"    # Absolute path to the isolated worktree
SPEC_FILE="$2"        # Path to .local_task.md or .local_feedback.md inside worktree
MODEL="$3"            # Resolved model ID (may be empty)
MODE="$4"             # "task" or "feedback"

TASK_CONTENT="$(cat "$SPEC_FILE")"

# Build your CLI command
CMD=(mybackend-cli run --auto)
if [ -n "$MODEL" ]; then
    CMD+=(--model "$MODEL")
fi

cd "$WORKTREE_PATH"
exec "${CMD[@]}" "$TASK_CONTENT"
```

### Contract

- **Arguments**: `run.sh` receives exactly 4 positional args (worktree path, spec file, model, mode)
- **Working directory**: The script must `cd` into the worktree before executing
- **Output**: All stdout/stderr goes to `agent.log` (the bridge redirects it)
- **Exit code**: 0 = success, non-zero = failure
- **Commits**: The backend should commit its changes to the worktree's branch
- **No interactivity**: The script runs unattended with no TTY

## Enterprise deployments (Bedrock / Vertex / internal gateways)

The `models:` list in `config.yaml` maps human-friendly aliases to the exact model ID the backend CLI expects. Consumer aliases like `opus`/`sonnet`/`haiku` only resolve correctly against Anthropic's API console. If your organization routes Claude Code through Bedrock, Vertex, or an internal proxy, the underlying CLI needs different model ID strings (e.g. Bedrock's `anthropic.claude-sonnet-...` inference profile IDs) and its own auth env vars (`CLAUDE_CODE_USE_BEDROCK`, AWS/GCP credentials, etc.) — set those up for the CLI itself, outside this plugin, then update `backends/claude/config.yaml`'s `id:` fields to match. The same applies to any backend pointed at an internal AI gateway instead of a vendor's public API: `check_command` and `default_model` are the two fields most likely to need a local override.

## Testing

After adding your backend:

```bash
bridge.sh --backends          # Verify it shows as available
bridge.sh --models mybackend  # Verify model listing works
```

Create a simple task file and run `bridge.sh <slug>` to validate end-to-end.
