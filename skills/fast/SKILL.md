---
name: fast
description: Low-overhead delegation. Use when a coding task is large enough to be worth handing off (a feature or module spanning several files, a mechanical migration, a test suite, bulk boilerplate) and should run in one step without a planning/approval round. Writes task files and runs `bridge.sh run`, which dispatches in parallel, retries once on failing tests, and applies passing work to the working tree uncommitted.
allowed-tools:
  - Bash
---

# Fast delegation

Every step you take re-sends your whole context, so delegation only pays off if it replaces many of your own steps. Keep the whole flow to **one dispatch step** plus a short follow-up.

**Delegate only large work**: new modules or features across several files, migrations across many files, test suites, bulk boilerplate. Implement small or single-spot changes yourself. Never send auth, crypto, secret handling or trust-boundary validation to a local model (check with `bridge.sh --security-check <backend> <model>`).

**Don't read code to write the spec.** Find the relevant files with `ls`/`grep -l`; the delegate reads them itself. Split independent parts into separate tasks (they run in parallel).

**One step:** write every task file and start them in the same command:

```bash
cat > .local_task_feat-x.md <<'EOF'
---
Branch: feat/x
Test: <command that proves the task is done, e.g. python3 -m unittest tests.test_x>
Files: path/a.py, path/b.py
---
## Objective
One sentence.
## Requirements
- Bullets: behaviour, names/signatures, edge cases, constraints. No code.
EOF
bridge.sh run feat-x
```

- `Test:` is required and must be **one line** (only the first line of a header is read). Prefer the project's full test command, so the gate is the only test run you need. `Files:` protects your uncommitted edits in those files.
- Leave `Backend:`/`Model:` out unless this task needs a specific one; the user's defaults (`CODE_DELEGATE_BACKEND`, `<BACKEND>_DELEGATE_MODEL`) apply.

**Read the report:**

- `pass`: changes are applied to the working tree, uncommitted, and the gate passed on them. In **one** step: glance at the diffstat, commit, and write your summary. Re-run tests only if `Test:` was narrower than the full suite; read the diff only if the diffstat looks wrong.
- `running`: run `bridge.sh wait <slugs>` (it waits up to 9 minutes per call).
- `fail` (after one automatic fix round), `aborted`, `apply_conflict`: the report shows the failing output and keeps the worktree. Either finish it yourself (fix in the worktree, then `git merge <branch>` or copy the files), or `bridge.sh --cleanup <slug>` and re-run with another `Model:`. Don't start over from scratch.
- `no_changes`: the test already passed without changes; check the `Test:` command.
