# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
