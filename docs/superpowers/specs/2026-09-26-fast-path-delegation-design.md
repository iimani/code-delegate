# Fast-path delegation — design

Date: 2026-09-26
Status: approved in brainstorming
Branch: `feature/fast-path-delegation` (based on `fix/bridge-stall-and-opencode-lock`)

## Problem

Benchmark evidence (tests/benchmark, 2026-09-25): delegating costs the Claude orchestrator
**more** tokens than implementing directly, on every small task and most large ones.

- Every orchestrator step re-sends its whole context (≥ 26k tokens of Claude Code system prompt
  plus conversation), so each step costs ~30k tokens regardless of what it does.
- The current flow adds ~6 management steps per task: load skill, `bridge.sh --models`, write
  the task file, dispatch, review the worktree, merge. That is ~190k tokens of overhead. It
  replaces roughly one ~30k coding step on small tasks.
- The orchestrator also reads the code in depth to write detailed specs (60–400k tokens in
  explore phases), and falls back to implementing everything itself when a delegate fails.
- Only on the largest task (L3, 762k baseline) did delegation save anything (−11% USD via Sonnet).

Goal: cut the management overhead to ~2–3 orchestrator steps (~50–70k tokens) per delegation
batch, without losing correctness or the user's control over commits.

## Decisions (from brainstorming)

1. On pass, the delegate's changes are **applied to the current branch's working tree,
   uncommitted**. Nothing is committed on anyone's behalf.
2. On a failed test gate, the bridge runs **one automatic fix round** (failing test output
   fed back to the same delegate) before reporting failure.
3. Approach A: a new `bridge.sh run` subcommand plus a new slim `code-delegate:fast` skill.
   The existing `delegate` / `plan` / `distribute` / `dispatch` skills remain unchanged for the
   interactive, reviewed workflow.

## `bridge.sh run`

```
bridge.sh run <slug> [<slug>...] [--max-wait SECONDS]
bridge.sh wait <slug> [<slug>...] [--max-wait SECONDS]
```

For each slug (`.local_task_<slug>.md` must exist):

1. **Validate**: `Branch:` and `Test:` headers required (`run` refuses a task without a test
   gate, status `error`, message says why). The working tree must have no uncommitted changes
   to the files listed in `Files:` (if given), so applying the diff cannot clobber local edits;
   otherwise status `error`.
2. **Start in the background** (detached, `nohup`): a worker process runs the existing
   single-task pipeline (`bridge.sh <slug>`: backend/model resolution, worktree, backend runner,
   watcher, test gate). Output goes to the worktree's `agent.log` as today. The worker's final
   JSON is written to `.git/worktrees_agents/<slug>/.bridge_result`.
3. **Fix round**: if the first attempt's status is `fail` (test gate failed; not `aborted` /
   `error` / `no_backend`), the worker writes `.local_feedback_<slug>.md` containing the
   `Branch:` header and the last 60 lines of the test output with the instruction "The test
   gate `<Test>` fails with the output below. Fix the implementation so it passes; do not
   weaken or delete tests.", and runs `bridge.sh <slug>` again (feedback mode, same worktree).
   At most one fix round.
4. **Apply on pass**: the worker computes the delegate's full change against the base commit
   the worktree was created from (committed + uncommitted + untracked files, excluding bridge
   files `agent.log`, `.bridge_*`, `.local_*`), applies it to the main working tree with
   `git apply --3way`, then removes the worktree and deletes the branch. If the apply fails,
   status `apply_conflict`, worktree and branch kept, message names the conflicting files.
5. **Wait**: `run` waits until all listed tasks have a `.bridge_result` or `--max-wait`
   (default 540 s, under Claude Code's 600 s Bash limit) elapses, then prints the report and
   exits. Tasks still running are reported as `running`. `bridge.sh wait <slugs>` resumes
   waiting (same report format) and can be repeated.

### Report (stdout)

One block per task, then one JSON line (array) for tools:

```
== feat-logger: pass (opencode / ollama/qwen3-coder:30b, 2 attempts, 143s)
 shop/util/log.py      | 41 +++++
 tests/test_log.py     | 28 ++++
 2 files changed, 69 insertions(+)
 applied to working tree (uncommitted)
== fix-ranges: fail (opencode / ollama/qwen3-coder:30b, 2 attempts, 390s)
 test gate: python3 -m unittest discover -s tests -t .
 FAILED (failures=1)  … last 15 lines of test output …
 worktree kept: .git/worktrees_agents/fix-ranges
[{"slug":"feat-logger","status":"pass",...},{"slug":"fix-ranges","status":"fail",...}]
```

Statuses: `pass` (applied), `fail` (gate failed after the fix round), `aborted`, `error`,
`no_backend`, `apply_conflict`, `running`. Exit code 0 when every task passed, 1 otherwise,
3 when any task is still `running`.

### Model selection without discovery

Unchanged resolution order: `Model:` header → `<BACKEND>_DELEGATE_MODEL` → config default;
backend: `Backend:` header → `CODE_DELEGATE_BACKEND` → auto-selection. `CODE_DELEGATE_BACKEND`
is documented as the **per-user default backend** (in addition to its benchmark use), so a user
sets e.g. `CODE_DELEGATE_BACKEND=opencode` and `OPENCODE_DELEGATE_MODEL=sovereign/coder-large`
once and the orchestrator never needs `bridge.sh --models`.

## `code-delegate:fast` skill

A ~30-line SKILL.md; its instructions:

- **When to delegate**: only work that would take many steps to do directly: new modules or
  features spanning several files, mechanical migrations across many files, test suites, larger
  boilerplate. Small or single-spot changes: implement directly. Security-sensitive work
  (auth, crypto, secrets, trust-boundary validation): never to a local model (existing rule).
- **Spec without pre-reading**: identify files with `ls`/`grep -l`; don't read implementation
  files just to write the spec. State requirements, interfaces, constraints and the test
  command, not code. The delegate reads the code.
- **One step to dispatch**: write all task files and run `bridge.sh run <slugs>` in the same
  shell command. Leave `Backend:`/`Model:` empty unless the task needs a specific one.
  `Test:` is mandatory.
- **On pass**: read the diffstat; run the full test suite once if the gate was narrower; commit.
  Read the diff only if something looks off.
- **On `running`**: call `bridge.sh wait <slugs>`.
- **On fail**: the report has the failing output. Small fix: do it directly in the kept
  worktree, or re-run with another model. Don't restart from scratch.

## Benchmark integration

- `tests/benchmark/directive-fast.md`: the fast-path directive (invoke `code-delegate:fast`).
  Run with `BENCH_DIRECTIVE_FILE=tests/benchmark/directive-fast.md`; the directive hash in the
  report distinguishes it. Compare against the existing baselines with `--skip-baseline` and
  `report` merging.
- Phase classifier: `bridge.sh run`/`wait` count as `dispatch`.

## Testing

Bridge tests with fake backends (no LLM), in a new `tests/bridge/run.sh` suite:

1. pass on the first attempt → diff applied uncommitted, worktree and branch removed;
2. fail, then pass in the fix round → 2 attempts, applied;
3. fail twice → `fail`, worktree kept, test output tail in the report;
4. missing `Test:` → `error`;
5. `--max-wait` shorter than the task → `running`, then `wait` returns `pass`;
6. two slugs in parallel → both applied;
7. local edits to a listed file → `error` before dispatch; a conflicting apply → `apply_conflict`.

CI runs the suite (bash + git only).

## Non-goals

- Changing the existing skills' behaviour.
- Auto-escalating to paid models.
- Committing on the user's behalf.
