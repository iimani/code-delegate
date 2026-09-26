# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Reworked `tests/benchmark/` (`bench.sh doctor|compare|scorecard|report|selftest`). The headline metric is the Claude tokens (orchestrator plus any Claude delegate) spent on the same task with vs. without delegation. Correctness is judged by hidden tests the model never sees, and a "correct runs only" saving is reported. The harness is portable: models come from `opencode models`, and per-machine settings go in `bench.local.env`. Auth and context isolation (`--setting-sources project`, or an isolated config dir) are checked by probes. Six stdlib-Python tasks cover every routing bucket, including a mutation-scored test-writing task. A dry-run mode with a fake orchestrator and backend runs in CI.
- `docs/benchmark-methodology.md` and `docs/how-delegation-works.md`
- Benchmark delegate targets beyond opencode: `claude:<model>` pins delegates to a Claude model, and `auto` leaves routing to the orchestrator to score the complete delegation flow. `compare --skip-baseline` plus multi-directory `report --out` reuse an earlier baseline
- Large benchmark tier (`--tier large`): a layered order/inventory service fixture and six larger tasks (cross-layer resource, mutation-scored test suites, tuple→exception migration, report export, symptom-only bug hunt, multi-feature request)
- Benchmark report: break-even estimate per delegate target (fixed overhead, ratio, task size where delegation starts saving Claude tokens) and a per-phase breakdown of orchestrator tokens from session transcripts (captured into `raw/`)
- `CLAUDE_DELEGATE_SETTING_SOURCES` env var: passed as `--setting-sources` to delegate `claude` processes (opt-in)
- `CODE_DELEGATE_BACKEND` env var: pins the backend for tasks whose `Backend:` is empty or `auto` (an explicit header still wins)
- `CODE_DELEGATE_USAGE_LOG` env var: when set, backend runners record per-run token usage (claude via `stream-json`, opencode via `--format json`) through `lib/usage_wrap.py`; unset means unchanged behaviour

### Removed
- The TypeScript benchmark fixture and `tests/benchmark/run.sh`, replaced by the above

## [1.3.0] - 2026-09-16

### Added
- CI workflow: shellcheck, JSON manifest validation, backend `config.yaml` schema check, and a manual `workflow_dispatch` job for the live-prompt scenario suite (#27)
- Trust-model note in README covering `eval` usage in `check_command`/`list_models_command`/`Test:`
- Enterprise deployment guidance (Bedrock/Vertex/internal gateway model IDs) in `docs/authoring-backends.md`
- Trigger-phrase coverage in `status`, `backends`, and `cleanup` skill descriptions for natural-language invocation
- Routing and dispatch now factor in *live* model availability for `models: dynamic` backends (opencode), not just whether the CLI is installed: `Backend: auto` skips a dynamic backend with zero live models, direct dispatch to one fails fast with `no_backend` + a fallback suggestion instead of failing deep inside `run.sh`, and an unresolved `Model:` value is validated against the live list before dispatch (error lists what's actually available)
- `tests/benchmark/` — measures the orchestrator's token/cost impact of delegating via code-delegate vs. implementing directly, using `claude --print --output-format json` in isolated scratch repos/config dirs (never touches real `~/.claude` or this repo). See `tests/benchmark/README.md` for methodology and known limitations, including why it can't measure opencode's actual savings

### Fixed
- `bridge.sh`'s JSON status output is now properly escaped — a `Test:` command containing a double quote (e.g. `--grep "foo"`) no longer corrupts the JSON line every skill parses as the bridge's result
- Removed unused `FILES` variable in `bridge.sh` (dead code flagged by shellcheck)
- Removed non-functional `trigger:` frontmatter key from all 7 `SKILL.md` files — it isn't a supported field; slash-command binding is by skill directory name
- Synced `.codex-plugin/plugin.json` version with the Claude plugin manifests (was still 1.0.0)

### Changed
- Collapsed the "security-approved backend/model" policy to a single source of truth (`config.yaml`'s `security_ok`); `CLAUDE.md`, `AGENTS.md`, `delegate`, and `distribute` skills now point at `bridge.sh --security-check` instead of each hardcoding "currently claude/opus"
- Trimmed `delegate/SKILL.md`'s duplicated Distribution Analysis and Execution Protocol sections down to pointers at `distribute`/`dispatch`, which remain the canonical copies (the two had already drifted in wording)
- Documented that `<BACKEND>_DELEGATE_MODEL` env overrides apply to every backend, not just opencode

## [1.2.0] - 2026-06-20

### Added
- Sub-skill: plan — writes .local_task_*.md specs from requirements (#21)
- Sub-skill: distribute — classifies tasks and assigns Backend/Model headers (#21)
- Sub-skill: dispatch — executes task files via bridge.sh with parallel dispatch (#21)
- Bundled flow section in delegate skill (plan → distribute → dispatch)

### Changed
- Delegate skill updated with sub-skill references and bundled flow documentation

## [1.1.0] - 2026-06-17

### Added
- Claude Code hooks: session-start backend availability check (#11)
- Claude Code hooks: pre-bridge task file validation (#12)
- Claude Code hooks: session-end stale worktree cleanup (#13)
- Declarative hooks.json manifest for native plugin auto-discovery
- install.sh / uninstall.sh for manual hook wiring into settings.json
- Plugin cache path fallback alongside marketplaces path

### Changed
- Removed unused Glob from delegate skill's allowed-tools
- Lowered default stall timeout from 600s to 300s

## [1.0.0] - 2026-06-10

### Added
- Multi-backend code delegation via bridge.sh (opencode, claude, codex)
- Auto-selection of backends based on task complexity and availability
- Model alias resolution and escalation (haiku -> sonnet -> opus)
- Cross-backend fallback suggestions on failure
- Tiered security delegation (local models blocked from auth/crypto tasks)
- Parallel task dispatch with isolated Git worktrees
- Watcher with timeout, stall detection, and failure loop counting
- Test gate support (optional post-implementation test command)
- Feedback loop for iterative fixes on failed tasks
- Skills: delegate, status, backends, cleanup
- Cross-platform support: Claude Code, Codex CLI, OpenCode CLI
- 13 workflow validation test scenarios
