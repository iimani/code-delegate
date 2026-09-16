# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-09-16

### Added
- CI workflow: shellcheck, JSON manifest validation, backend `config.yaml` schema check, and a manual `workflow_dispatch` job for the live-prompt scenario suite (#27)
- Trust-model note in README covering `eval` usage in `check_command`/`list_models_command`/`Test:`
- Enterprise deployment guidance (Bedrock/Vertex/internal gateway model IDs) in `docs/authoring-backends.md`
- Trigger-phrase coverage in `status`, `backends`, and `cleanup` skill descriptions for natural-language invocation

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
