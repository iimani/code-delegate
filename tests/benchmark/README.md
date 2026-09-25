# Benchmark

Measures how many **Claude tokens** a Claude Code session spends on the same coding task **with**
code-delegate (delegating to an opencode model) vs. **without** it — and whether both produced
correct code, judged by hidden tests. A second mode scores delegate models on their own.

Portable: it tests whatever `opencode models` lists on the machine it runs on — a home Ollama box,
LM Studio, or a company's self-hosted platform configured as an opencode provider.

**Read [docs/benchmark-methodology.md](../../docs/benchmark-methodology.md)** for what is measured,
testing conditions, scoring and caveats.

## Quickstart

```bash
cd tests/benchmark
cp bench.env.example bench.local.env   # set BENCH_MODELS (cheapest first)
./bench.sh doctor                       # preflight: tools, Claude login + isolation, models
./bench.sh compare --reps 1 01 04       # small first run: two tasks, one rep
./bench.sh compare                      # full: all tasks, BENCH_REPS reps
./bench.sh scorecard                    # model × task-class pass-rate matrix
```

Results go to `results/<timestamp>-<mode>/` (gitignored): `summary.md`, `summary.json`,
`runs.jsonl`, `env.json`, and `raw/` artifacts for every run.

Requirements: bash, git, python3 ≥ 3.9, `claude` CLI logged in (`claude` → `/login`) or env
credentials, `opencode` with at least one model, non-root user.

## No-LLM checks (run in CI)

```bash
./bench.sh selftest                      # hidden tests fail on fixture, pass on reference solution
./bench.sh compare --dry-run --reps 1    # whole pipeline via real bridge.sh, fake orchestrator/backend
python3 -m unittest discover -s lib -p 'test_*.py'
```

## Layout

```
bench.sh              entry point (runs lib/bench.py)
bench.env.example     configuration keys; copy to bench.local.env
preamble.md           prepended to every task prompt (both conditions)
directive.md          delegation directive for the with-delegation condition
fixture/              stdlib Python project every run starts from
tasks/<NN-slug>/      prompt.md, task.yaml, hidden/ tests, solution/
lib/bench.py          harness (doctor, compare, scorecard, selftest)
lib/report.py         aggregation and summary.md
lib/dryrun/           fake orchestrator + fake backend for --dry-run
```
