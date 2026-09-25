# How delegation and orchestration work

This document explains what happens, end to end, when a Claude Code session hands coding work to
another agent through code-delegate: who decides what, which files are written, what `bridge.sh`
does with them, and where a new model provider plugs in. It describes the code as of v1.3.x.

For adding a backend see [authoring-backends.md](authoring-backends.md). For how the benefit is
measured see [benchmark-methodology.md](benchmark-methodology.md).

## The four roles

| Role | What it is | Responsibility |
|---|---|---|
| **Orchestrator** | The Claude Code session you talk to | Plans, classifies tasks, writes task files, runs the bridge, reviews and merges results. Implements directly what shouldn't be delegated. |
| **Skills** | `skills/{delegate,plan,distribute,dispatch,…}/SKILL.md` | Instructions the orchestrator follows. `delegate` bundles `plan → distribute → dispatch`. |
| **Bridge** | `bin/bridge.sh` | Deterministic shell dispatcher: resolves backend and model, creates an isolated git worktree, runs the backend, watches it, runs the test gate, prints a JSON verdict. No LLM inside. |
| **Backend** | `backends/<name>/{config.yaml,run.sh}` + a CLI (`opencode`, `claude`, `codex`) | Runs the delegate agent in the worktree with the task spec as its prompt. |

The key property: the **orchestrator spends its tokens on deciding and reviewing**, while the tokens
for reading, writing and iterating on code are spent by the delegate — for opencode, on a local or
self-hosted model that costs no Claude tokens.

## End-to-end flow

```mermaid
sequenceDiagram
    actor U as User
    participant O as Orchestrator (Claude Code)
    participant B as bridge.sh
    participant W as Git worktree<br/>.git/worktrees_agents/<slug>
    participant R as backends/<name>/run.sh
    participant D as Delegate CLI<br/>(opencode / claude / codex)

    U->>O: "implement X"
    O->>O: plan: split into bounded sub-tasks
    O->>B: bridge.sh --backends / --models
    O->>U: distribution summary (DELEGATE / LARGER MODEL / IMPLEMENT DIRECTLY)
    U->>O: approve (or override models)
    O->>O: write .local_task_<slug>.md (headers + spec)
    O->>B: bridge.sh <slug>  (one per task, parallel in background)
    B->>B: resolve backend + model, check availability
    B->>W: git worktree add -b <Branch>, symlink deps
    B->>R: run.sh <worktree> <spec> <model> task
    R->>D: CLI with preamble + spec as prompt
    D->>W: read / edit / run tests
    B-->>B: watcher: wall timeout, stall, failure loop
    B->>W: test gate (Test: header)
    B->>O: last stdout line = JSON status
    O->>W: review diff
    alt needs fixes
        O->>B: .local_feedback_<slug>.md + bridge.sh <slug>
    else good
        O->>U: summary; user merges
        O->>B: bridge.sh --cleanup <slug>
    end
```

## 1. Activation

Delegation is opt-in per user. The README tells users to add a short directive to
`~/.claude/CLAUDE.md` ("when you reach the implementation phase, invoke `code-delegate:delegate`").
This repository's own `CLAUDE.md` adds stricter house rules. With the plugin installed, the skills
are available as `code-delegate:*` and `bin/` is put on `PATH`, so `bridge.sh` runs as a bare
command.

Not delegated, by rule: one-line fixes and config edits, exploratory reads, git operations and
reviews, and anything the user says to do directly.

## 2. Plan: task files

The orchestrator splits the work into sub-tasks of at most 2–3 files each and writes one
`.local_task_<slug>.md` per sub-task in the project root. The slug is the branch name with `/`
replaced by `-` (`feat/logger` → `feat-logger`).

```markdown
---
Branch: feat/logger
Backend: opencode
Model: ollama/qwen3-coder:30b
Test: python3 -m unittest tests.test_logger
Files: app/logger.py, tests/test_logger.py
---

## Objective
…one sentence…

## File Operations
### CREATE app/logger.py
- bullet per requirement (what, not how — no code in specs)

## Constraints
- No changes outside listed files
```

| Header | Required | Meaning |
|---|---|---|
| `Branch` | yes | Branch created for the worktree |
| `Backend` | no | `opencode`, `claude`, `codex`, or `auto` (default) |
| `Model` | no | Model id or alias (`opus`, `ollama/qwen3-coder:30b`) |
| `Test` | no | Shell command run in the worktree after the agent exits — the test gate |
| `Files` | no | Files the agent may touch; also used by auto-routing (more than 3 files → skip backends with `cross_file: false`) |
| `Timeout` | no | Wall-clock kill limit, seconds (default 3600) |
| `StallTimeout` | no | Kill after this many seconds without log output (default 300) |
| `MaxFails` / `FailPattern` | no | Kill after N matches of a failure regex in the log (default 8 / `build commands failed\|compilation error\|FAILED\|npm ERR!`) |

The task files are the plan: no separate prose spec is written, because only the task file reaches
the delegate.

## 3. Distribute: classification

For each task the orchestrator picks one of four outcomes (full criteria in
`skills/distribute/SKILL.md`):

- **DELEGATE** — bounded (≤ 2–3 files), boilerplate-heavy, no hard type reasoning, recoverable if
  wrong. Default target: opencode.
- **DELEGATE (larger model)** — still bounded, but beyond a small model's ceiling (e.g. generics).
  Target: a bigger opencode model or `claude`/`sonnet`.
- **DELEGATE (security-approved)** — see [Security tiering](#security-tiering).
- **IMPLEMENT DIRECTLY** — cross-file invariants, architectural ripples, schema migrations,
  security work with no approved model, or tasks shorter to do than to specify.

It shows a distribution summary with the live model list from `bridge.sh --models`, waits for the
user's approval or overrides, then writes `Backend:`/`Model:` headers into the task files.

## 4. Dispatch: what `bridge.sh <slug>` does

1. **Pick the instruction file.** `.local_feedback_<slug>.md` if present (feedback mode, reuses the
   existing worktree), else `.local_task_<slug>.md` (task mode).
2. **Resolve the backend**, first match wins:
   1. the `Backend:` header (anything other than empty/`auto`);
   2. the `CODE_DELEGATE_BACKEND` environment variable (used by the benchmark to pin a backend;
      never overrides an explicit header);
   3. auto-selection: the first of `opencode`, `claude`, `codex` whose `check_command` succeeds,
      which has live models (for `models: dynamic` backends such as opencode, `opencode models`
      must return something), and which allows cross-file work if `Files:` lists more than 3 files.
3. **Check availability.** CLI missing, or CLI present but no models loaded → exit code 10,
   status `no_backend`, with a fallback suggestion.
4. **Resolve the model**, first match wins: `Model:` header → `<BACKEND>_DELEGATE_MODEL` env var
   (e.g. `OPENCODE_DELEGATE_MODEL`) → `default_model` in `config.yaml` → none (the CLI's own
   default). Aliases are mapped to ids from `config.yaml`. For dynamic backends the model must
   appear in the live list, otherwise the bridge fails with the list of available models.
5. **Create the worktree** at `.git/worktrees_agents/<slug>` on a new branch `Branch:` (or reuse
   it). Dependency folders (`node_modules`, `venv`, `.venv`, `vendor`, `target`, `.build`) are
   symlinked from the main checkout.
6. **Run the backend**: `backends/<backend>/run.sh <worktree> <spec> <model> <task|feedback>`,
   with output going to `<worktree>/agent.log`. Each runner wraps the spec in a prompt;
   opencode's adds an agent-role preamble ("implement the spec, no plans, no questions, no
   external URLs"). Runners start the CLI in unattended mode (`--dangerously-skip-permissions` /
   `--full-auto`) inside the worktree.
7. **Watch** the process every 10 s and kill it, recording a reason, when:
   - the wall-clock `Timeout` is reached;
   - the log hasn't grown for `StallTimeout` seconds and the process uses no CPU (CPU activity
     resets the stall timer; a heartbeat line is logged every 60 s of silence);
   - `FailPattern` has matched `MaxFails` times.
8. **Test gate.** If the agent exited 0 and `Test:` is set, run it in the worktree.
9. **Report.** The last stdout line is JSON:

   ```json
   {"status":"pass|fail|error|aborted|no_backend","branch":"feat/logger","slug":"feat-logger",
    "worktree":".git/worktrees_agents/feat-logger","test_exit_code":0,
    "test_command":"…","message":"…","suggestion":{…}}
   ```

   | Status | Exit code | Meaning |
   |---|---|---|
   | `pass` | 0 | Agent finished; test gate passed or there was none |
   | `fail` | 1 | Test gate failed; worktree kept for feedback |
   | `error` | agent's code | Bridge problem or the agent crashed |
   | `aborted` | 2 | Killed by the watcher |
   | `no_backend` | 10 | Backend unavailable |

   `fail`, `aborted` and `no_backend` carry a **suggestion**: escalate to the next model up in the
   same backend (the alias listed just above the current one in `config.yaml`; for claude,
   haiku → sonnet → opus), else
   switch to another available backend, else implement directly. The orchestrator must show the
   suggestion to the user rather than act on it.

Several tasks run in parallel by calling the bridge once per slug in the background; each has its
own worktree and log. `bridge.sh --status` and `--logs [slug]` show progress.

## 5. Review, feedback, merge

On `pass` the orchestrator reviews the delegate's changes. Note that runners **do not tell the
delegate to commit**: depending on the model, the work may be committed on the branch or left
uncommitted in the worktree. Review both (`git -C <worktree> status` / `git diff`, and
`git diff main..<branch>`). A `pass` with no changes at all means the delegate did nothing; the
orchestrator must ask before taking over.

To request fixes, the orchestrator writes `.local_feedback_<slug>.md` (same `Branch:`, specific
instructions) and runs `bridge.sh <slug>` again. The feedback goes to the same worktree, and the
original `Test:` gate is reused.

The user decides on merging. Afterwards `bridge.sh --cleanup <slug>` removes the worktree.

## Security tiering

- Auth logic, token or signature validation (JWT, OAuth, HMAC), cryptography, secret handling and
  input validation at trust boundaries are **never sent to local models**, which aren't auditable.
- Such tasks may go to a backend+model marked `security_ok: true` in its `config.yaml` (currently
  `claude`/`opus`). `bridge.sh --security-check <backend> <model>` answers
  `{"approved": true|false, …}` and names an approved alternative.
- With no approved model, the orchestrator implements the task itself.

This is enforced by the orchestrator writing an explicit `Backend:`/`Model:` for such tasks. An
explicit header is never overridden by `CODE_DELEGATE_BACKEND` or auto-routing.

## Plugging in a model provider

**An OpenAI-compatible endpoint (Ollama, LM Studio, vLLM, a company "sovereign AI" gateway)** needs
no code change. Add it as an opencode provider in `~/.config/opencode/opencode.json`:

```json
{
  "provider": {
    "sovereign": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Company AI platform",
      "options": { "baseURL": "https://ai.internal.example/v1", "apiKey": "{env:SOVEREIGN_API_KEY}" },
      "models": { "coder-large": { "name": "coder-large" } }
    }
  }
}
```

`opencode models` then lists `sovereign/coder-large`, which works in `Model:` headers, as
`OPENCODE_DELEGATE_MODEL`, and in the benchmark's `BENCH_MODELS`. The model must support tool
calling through the endpoint. Run `tests/benchmark/bench.sh doctor --models sovereign/coder-large`
to check it.

**A different agent CLI or API** gets its own backend directory; see
[authoring-backends.md](authoring-backends.md).

## Environment variables

| Variable | Read by | Effect |
|---|---|---|
| `<BACKEND>_DELEGATE_MODEL` | bridge | Default model for that backend when no `Model:` header |
| `CODE_DELEGATE_BACKEND` | bridge | Backend for tasks whose `Backend:` is empty or `auto` |
| `CODE_DELEGATE_USAGE_LOG` | backend runners | If set, the runner streams the CLI's JSON events through `lib/usage_wrap.py`, keeps `agent.log` readable, and appends one JSON line of token usage per run to this file. Unset in normal use, which leaves runner behaviour unchanged. |

## Hooks

`.claude-plugin/hooks/` contains optional hooks (`install.sh` adds them to your settings):

- on session start, print backend availability;
- before any Bash call to `bridge.sh <slug>`, block it if the task file lacks `Branch:`;
- on stop, list agent worktrees, and remove ones idle for more than 8 hours whose branch is
  merged into `main` (or idle for more than 24 hours).
