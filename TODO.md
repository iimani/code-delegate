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
