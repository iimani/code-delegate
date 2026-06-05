# Roadmap

## Planned Features

### Delegate to Claude subagents as alternative backend
When OpenCode/LM Studio is unavailable or when a task requires higher reasoning capability,
the bridge should support delegating to Claude models (Sonnet/Haiku) via the Anthropic API
as an alternative execution backend. This would allow:

- **Fallback chain**: OpenCode (local, free) → Claude Haiku (cheap) → Claude Sonnet (capable)
- **Model routing by task complexity**: boilerplate/tests → local model, architectural changes → Claude
- **Cost-aware dispatch**: user sets a budget or tier preference, bridge picks the backend
- **API key management**: read `ANTHROPIC_API_KEY` from env, skip if not set

Implementation approach: add a `Backend:` header to task files (`local` | `haiku` | `sonnet` | `auto`),
and a `--backend` flag to bridge.sh. The `auto` mode would try local first, fall back to API on failure.

### Multi-delegate support with interactive selection

The skill should support multiple delegate backends beyond OpenCode, and let the user choose
which one to use. On first invocation (or via a `--setup` command), the skill prompts the user
to select their preferred delegate and model.

**Supported delegates:**
- **OpenCode** (local, via LM Studio / Ollama / any OpenAI-compatible server)
- **Codex CLI** (OpenAI's terminal agent)
- **Claude Code subagent** (via `Agent` tool or Anthropic API)
- **Aider** (terminal-based AI pair programmer)
- **Custom** (user-defined command template)

**Model selection per delegate:**
- Each delegate exposes its own model list (e.g., OpenCode → qwen/deepseek/llama, Codex → gpt-4.1/o3/o4-mini)
- The skill stores the user's preference in `~/.claude/skills/opencode-delegate/config.json`
- Users can override per-task via a `Model:` header in the task file
- The `--setup` flag re-runs the interactive selection

**Config format:**
```json
{
  "delegate": "opencode",
  "model": "qwen/qwen3.5-9b",
  "fallback_delegate": "codex",
  "fallback_model": "gpt-4.1"
}
```

**Bridge changes:**
- `bridge.sh --setup` → interactive delegate/model picker
- `bridge.sh` reads `config.json` for default delegate
- Task file `Delegate:` and `Model:` headers override config per-task
- Each delegate gets an adapter function in bridge.sh that translates the generic
  "run this task in this directory" call into the delegate-specific CLI invocation
