# Roadmap

## Done

- **Model selection via task file header** — `Model:` header in task/feedback files selects the opencode model (e.g., `lmstudio/qwen/qwen3.5-9b`)
- **Worktree-based parallel execution** — each task runs in an isolated git worktree under `.git/worktrees_agents/`
- **Feedback loop** — write `.local_feedback_<slug>.md` to iterate on an existing worktree
- **Test gate** — `Test:` header runs a command after implementation and reports pass/fail

## Planned Features

### 1. Multi-delegate support

Generalize the bridge beyond OpenCode to support multiple execution backends. Each delegate gets an adapter function that translates the generic "run this task in this directory" call into its CLI invocation.

**Delegates to support:**
- **OpenCode** (local, via LM Studio / Ollama / any OpenAI-compatible server) — already implemented
- **Codex CLI** (OpenAI's terminal agent, `codex`)
- **Claude Code subagent** (via `claude` CLI or Anthropic API)
- **Aider** (terminal-based AI pair programmer)
- **Custom** (user-defined command template)

**Task file header:** `Delegate: opencode | codex | claude | aider | custom`

**Bridge changes:**
- Adapter functions per delegate: `run_opencode()`, `run_codex()`, `run_claude()`, etc.
- `bridge.sh --setup` for interactive delegate/model picker
- Read default delegate from `config.json`

### 2. Fallback chain

When a delegate is unavailable or fails, automatically try the next one in a configured chain.

- `config.json` defines a fallback order (e.g., opencode → codex → claude)
- Health check per delegate before attempting (test CLI availability + connectivity)
- `auto` mode: bridge picks the first available delegate
- Always surface fallback decisions to the user — no silent switching

### 3. Config file

Centralized `config.json` for persistent preferences:

```json
{
  "delegate": "opencode",
  "model": "lmstudio/qwen/qwen3.5-9b",
  "fallback_chain": ["opencode", "codex", "claude"],
  "delegates": {
    "codex": { "model": "gpt-4.1" },
    "claude": { "model": "sonnet" }
  }
}
```

- Read by bridge on every invocation
- Written by `bridge.sh --setup`
- Task file headers override config per-task
