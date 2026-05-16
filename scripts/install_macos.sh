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

bash scripts/package_macos_app.sh --install-user

.venv/bin/python -m jarvis.core.app_lifecycle install-agent

echo "JARVIS installed."
echo "Launch with: ./start.sh full"
echo "Optional launchd install:"
echo "  launchctl bootstrap gui/$(id -u) $HOME/Library/LaunchAgents/com.jarvis.assistant.plist"
echo "  launchctl bootout gui/$(id -u) $HOME/Library/LaunchAgents/com.jarvis.assistant.plist"
