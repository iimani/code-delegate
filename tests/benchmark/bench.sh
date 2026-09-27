#!/bin/bash
# code-delegate benchmark entry point. All logic lives in lib/bench.py.
#
#   ./bench.sh doctor                         preflight checks
#   ./bench.sh compare  [--models a,b] [tasks...]   Claude tokens with vs. without delegation
#   ./bench.sh scorecard [--models a,b] [tasks...]  delegate-only quality matrix
#   ./bench.sh report results/<run>           rebuild a summary
#   ./bench.sh selftest                       validate tasks (no LLM calls)
#
# Configure per machine in bench.local.env (see bench.env.example).
# Methodology: docs/benchmark-methodology.md
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  echo "FATAL: python3 (3.9+) is required" >&2
  exit 1
fi

exec python3 "$(cd "$(dirname "$0")" && pwd)/lib/bench.py" "$@"
