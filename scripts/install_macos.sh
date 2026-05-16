#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/playwright install chromium

npm --prefix jarvis/ui/jarvis-ui ci
npm --prefix jarvis/ui/jarvis-ui run build

mkdir -p "$HOME/Library/LaunchAgents"
PLIST_TARGET="$HOME/Library/LaunchAgents/com.jarvis.assistant.plist"
sed \
  -e "s#/Users/bertrandmbanwi/Documents/Jarvis#$ROOT#g" \
  -e "s#/Users/bertrandmbanwi#$HOME#g" \
  com.jarvis.assistant.plist > "$PLIST_TARGET"

echo "JARVIS installed."
echo "Launch with: ./start.sh full"
echo "Optional launchd install:"
echo "  launchctl unload $PLIST_TARGET 2>/dev/null || true"
echo "  launchctl load $PLIST_TARGET"
