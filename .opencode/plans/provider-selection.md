# Provider Selection & Multi-Delegate Improvements

## Todos

### 1. Support provider selection with fallback

Add capability for users to select a provider delegate during runtime, with automatic fallback if the picked provider is unavailable.

**Requirements:**
- Prompt user for provider selection (similar to model picker)
- Auto-detect available providers (test connectivity)
- If selected provider is unavailable, prompt for fallback provider
- Option to let Claude auto-select fallback
- Support `Provider:` header in task files for overrides

**Implementation notes:**
- Store selected providers in config
- Add health check function for each provider
- Add fallback logic in bridge execution flow
- Update task file format to include `Provider:` header

### 2. Support Codex and other models for cheaper implementation

Support delegating implementation tasks to other Claude Code models (not just OpenCode):

**Requirements:**
- Connect to Codex CLI (OpenAI's terminal agent) for cheaper compute
- Implement Codex adapter in bridge.sh
- Support switching between models based on task complexity/cost
- Provide adapter layer for different delegate types in bridge.sh

**Config additions:**
```json
{
  "codex": {
    "provider": "codex",
    "model": "openai/gpts-lite"
  }
}
```

**Tasks:**
1. Test Codex CLI availability and installation
2. Design Codex adapter for bridge.sh
3. Add Codex to provider selection menu
4. Implement cost-aware model selection logic

## Proposed Changes to Files

### TODO.md
- Add new todos for:
  1. Provider selection with fallback
  2. Codex/other models support for cheaper implementation
  3. Delegate to Claude subagents as alternative backend

### bridge.sh
- Add `--provider` flag for provider selection
- Add provider health check function
- Add fallback logic when provider unavailable
- Add Codex, CLI, and subagent adapters
- Update default provider to support multi-delegate

### .claude/skills/opencode-delegate/
- Add provider selection logic in skill implementation
- Add fallback handling
- Add delegate adapters for different backends

### config.json (new)
- Create centralized config file
- Define available providers:
  - opencode/codex (local)
  - codex (API)
  - claude-subagent
- Default model per provider
- Fallback configuration

## Implementation Order

1. Update TODO.md with new todos
2. Design provider configuration format
3. Implement provider discovery and health checks
4. Add fallback mechanism
5. Add Codex adapter
6. Add subagent adapter
7. Update bridge execution flow for multi-provider
8. Create config.json with provider options
9. Add --setup flag for interactive provider selection
