# Additional TODO Items for Provider Improvements

## New Todos to Add to TODO.md

### Before implementing provider selection and multi-delegate support, add these todos to TODO.md:

1. **Support provider selection with fallback mechanism**
   - Add capability for users to select different provider delegates during runtime
   - Implement provider auto-detection (test LM Studio, Ollama, OAI servers)
   - Add automatic fallback when picked provider is unavailable
   - Fallback options: prompt user for manual selection OR let Claude auto-select
   - Support `Provider:` header in task files to override config per-task
   - Update bridge.sh to handle multiple delegates with fallback chaining

2. **Support delegation to Codex and other models for cheaper implementation**
   - Add Codex CLI (OpenAI) as a delegate option
   - Support additional API models (gpt-4.1, o3, o4-mini) via OpenAI
   - Support switching models based on cost/complexity preferences
   - Test Codex CLI installation and basic connectivity
   - Design adapter pattern for different delegate types in bridge.sh
   - Implement cost-aware routing logic (simple tasks → cheaper models)

### Config File Design (config.json)

```json
{
  "providers": {
    "opencode": {
      "name": "OpenCode (Local)",
      "defaultModel": "qwen/qwen3.5-9b",
      "description": "Local OpenCode via LM Studio or Ollama"
    },
    "codex": {
      "name": "Codex (OpenAI)",
      "defaultModel": "openai/gpts-lite",
      "description": "OpenAI Codex CLI for terminal automation",
      "costPerToken": "0.01"
    },
    "claude": {
      "name": "Claude (API)",
      "defaultModel": "claude/sonnet-3.5",
      "description": "Anthropic Claude via API"
    }
  },
  "defaultDelegate": "opencode",
  "defaultModel": "qwen/qwen3.5-9b",
  "fallbackDelegate": "codex",
  "fallbackModel": "openai/gpts-lite"
}
```

### bridge.sh Changes

- Add `--provider` flag to run with specific provider
- Add `--setup` flag for interactive provider/model selection
- Implement provider health check function (test connectivity)
- Add delegate adapter functions for each provider type:
  - `run_local_task()` - OpenCode worktree-based execution
  - `run_codex_task()` - OpenAI terminal-based task execution
  - `run_claude_task()` - Anthropic API task execution
- Add fallback logic:
  ```bash
  # For each delegate in fallback chain
  attempt_provider "opencode" || attempt_provider "codex" || attempt_provider "claude"
  ```
- Update status output to include delegate information

### CLAUDE.md Updates

- Add fallback behavior when delegate is unavailable
- Handle different delegate outputs (worktree vs terminal vs API response)
- Update skill routing logic for multi-delegate scenarios
