#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

git pull --ff-only

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.txt

npm --prefix jarvis/ui/jarvis-ui ci
npm --prefix jarvis/ui/jarvis-ui run build

bash scripts/validate.sh
