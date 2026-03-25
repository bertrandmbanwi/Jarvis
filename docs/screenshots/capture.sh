#!/usr/bin/env bash
# Quick screenshot capture helper for JARVIS README images.
# Requires: Chrome + a running JARVIS instance.
# Usage: ./capture.sh [JARVIS_URL]
set -euo pipefail

URL="${1:-http://localhost:8080}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Capturing JARVIS screenshots from ${URL} ..."
echo "Saving to: ${DIR}"

# Voice / Orb view (default landing page)
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --headless --screenshot="${DIR}/voice-orb.png" \
    --window-size=1600,900 --hide-scrollbars \
    "${URL}" 2>/dev/null || true

# Chat view
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --headless --screenshot="${DIR}/chat-view.png" \
    --window-size=1600,900 --hide-scrollbars \
    "${URL}/?view=chat" 2>/dev/null || true

# System / Dashboard view
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --headless --screenshot="${DIR}/system-dashboard.png" \
    --window-size=1600,900 --hide-scrollbars \
    "${URL}/?view=system" 2>/dev/null || true

echo ""
echo "Done. Screenshots saved:"
ls -lh "${DIR}"/*.png 2>/dev/null || echo "(no screenshots captured; check URL)"
echo ""
echo "Note: Headless Chrome may not render WebGL correctly."
echo "For best results, take manual screenshots from the live UI"
echo "and save them as voice-orb.png, chat-view.png, system-dashboard.png"
