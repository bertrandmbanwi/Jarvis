#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python}"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT/.venv/bin/python"
fi

"$PYTHON_BIN" -m compileall -q jarvis tests scripts
"$PYTHON_BIN" -m ruff check .
"$PYTHON_BIN" -m mypy jarvis
"$PYTHON_BIN" -m pytest tests -q
"$PYTHON_BIN" scripts/check_tool_contracts.py
"$PYTHON_BIN" scripts/run_evals.py --offline
"$PYTHON_BIN" -m bandit -q -r jarvis

if [[ -d "$ROOT/jarvis/ui/jarvis-ui/node_modules" ]]; then
  # Next.js can cache absolute paths in .next. On macOS, using the same checkout
  # through different casing (Jarvis vs jarvis) can poison that cache and create
  # duplicate module warnings or prerender failures. Validation should always be
  # path-clean and reproducible.
  rm -rf "$ROOT/jarvis/ui/jarvis-ui/.next"
  npm --prefix "$ROOT/jarvis/ui/jarvis-ui" run lint
  npm --prefix "$ROOT/jarvis/ui/jarvis-ui" run build
  npm --prefix "$ROOT/jarvis/ui/jarvis-ui" audit --audit-level=high
else
  echo "Skipping frontend validation because node_modules is not installed."
fi
