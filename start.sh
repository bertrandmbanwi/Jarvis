#!/usr/bin/env bash
# ============================================================
# JARVIS Launch Script
# Usage: ./start.sh [text|voice|server|full]
# Default: full (voice + API server + UI)
#
# Modes:
#   text   - Terminal text chat only
#   voice  - Voice interaction only (no UI)
#   server - API server only (no voice, no UI)
#   full   - Voice + API server + Next.js UI (recommended)
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
UI_DIR="${SCRIPT_DIR}/jarvis/ui/jarvis-ui"
MODE="${1:-full}"

# Track child PIDs for cleanup
UI_PID=""
NEXTJS_PID=""
PROXY_PID=""
OLLAMA_PID=""
TUNNEL_PID=""
OVERLAY_PID=""

cleanup() {
    echo ""
    echo "Shutting down JARVIS..."
    if [[ -n "${UI_PID}" ]] && kill -0 "${UI_PID}" 2>/dev/null; then
        echo "Stopping UI server..."
        kill -- -"${UI_PID}" 2>/dev/null || kill "${UI_PID}" 2>/dev/null || true
        wait "${UI_PID}" 2>/dev/null || true
    fi
    if [[ -n "${NEXTJS_PID}" ]] && kill -0 "${NEXTJS_PID}" 2>/dev/null; then
        kill "${NEXTJS_PID}" 2>/dev/null || true
    fi
    if [[ -n "${PROXY_PID}" ]] && kill -0 "${PROXY_PID}" 2>/dev/null; then
        kill "${PROXY_PID}" 2>/dev/null || true
    fi
    if [[ -n "${TUNNEL_PID}" ]] && kill -0 "${TUNNEL_PID}" 2>/dev/null; then
        echo "Stopping Cloudflare Tunnel..."
        kill "${TUNNEL_PID}" 2>/dev/null || true
    fi
    # Final sweep: kill anything still holding ports 3000 and 3001
    for pid in $(lsof -ti :3000,:3001 2>/dev/null || true); do
        kill "${pid}" 2>/dev/null || true
    done
    if [[ -n "${OVERLAY_PID}" ]] && kill -0 "${OVERLAY_PID}" 2>/dev/null; then
        echo "Stopping Desktop Overlay..."
        kill "${OVERLAY_PID}" 2>/dev/null || true
    fi
    # Also kill any orphaned overlay processes by name
    pkill -f "JarvisOverlay" 2>/dev/null || true
    if [[ -n "${OLLAMA_PID}" ]] && kill -0 "${OLLAMA_PID}" 2>/dev/null; then
        echo "Stopping Ollama..."
        kill "${OLLAMA_PID}" 2>/dev/null || true
    fi
    echo "JARVIS shut down."
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# Check virtual environment
if [[ ! -d "${VENV_DIR}" ]]; then
    echo "Virtual environment not found. Run ./setup.sh first."
    exit 1
fi

# Activate virtual environment
source "${VENV_DIR}/bin/activate"

# Ensure python-multipart is installed (required for browser voice upload)
python -c "import multipart" 2>/dev/null || pip install python-multipart -q

# Ensure Playwright is installed with Chromium (required for browser automation)
if python -c "import playwright" 2>/dev/null; then
    if ! python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.chromium.executable_path; p.stop()" 2>/dev/null; then
        echo "Installing Playwright Chromium browser..."
        playwright install chromium
    fi
else
    echo "Installing Playwright..."
    pip install playwright -q
    echo "Installing Playwright Chromium browser..."
    playwright install chromium
fi

# Check for Claude Code CLI (optional, for development tasks)
if command -v claude &>/dev/null; then
    echo "Claude Code CLI: found ($(claude --version 2>/dev/null || echo 'version unknown'))"
else
    echo "Note: Claude Code CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
    echo "      (Browser automation will still work without it.)"
fi

# Browser automation uses Playwright with a persistent profile stored in
# data/browser-profile/. Sessions, cookies, and logins persist between restarts.
# The first time JARVIS browses a site, you may need to sign in. After that,
# the session is saved and reused automatically (just like a normal browser).
# This is more reliable than Chrome CDP, which has strict restrictions on macOS.
BROWSER_PROFILE="${SCRIPT_DIR}/data/browser-profile"
mkdir -p "${BROWSER_PROFILE}"
echo "Browser automation: persistent profile at data/browser-profile/"
echo "  (Sessions and logins persist between JARVIS restarts)"

# Detect cloudflared for remote/mobile access via Cloudflare Tunnel.
# This gives you an HTTPS URL accessible from your phone (mic works over HTTPS).
# Quick Tunnel: random *.trycloudflare.com URL, no account needed.
# Named Tunnel: persistent URL, requires free Cloudflare account + domain.
CLOUDFLARED_AVAILABLE=""
if command -v cloudflared &>/dev/null; then
    CLOUDFLARED_AVAILABLE="true"
    echo ""
    echo "Cloudflare Tunnel: cloudflared found ($(cloudflared --version 2>&1 | head -1))"
    echo "  A tunnel will start after JARVIS is ready. Check the logs for your phone URL."
else
    echo ""
    echo "Note: Install cloudflared for mobile/phone access:"
    echo "  brew install cloudflared"
    echo "  (Gives you a free HTTPS URL to access JARVIS from your phone)"
fi

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo ""
    echo "Ollama is not running. Starting it in the background..."
    ollama serve &
    OLLAMA_PID=$!
    sleep 2
    echo "Ollama started (PID: ${OLLAMA_PID})"
    echo ""
fi

# Ensure pyyaml is installed (required for prompt templates)
python -c "import yaml" 2>/dev/null || pip install pyyaml -q

# Ensure data directories exist for SQLite databases
mkdir -p "${SCRIPT_DIR}/data"
mkdir -p "${SCRIPT_DIR}/templates/prompts"

# Build and launch desktop overlay (macOS only, optional)
OVERLAY_DIR="${SCRIPT_DIR}/desktop-overlay"
OVERLAY_APP="${OVERLAY_DIR}/build/JarvisOverlay.app"
OVERLAY_BIN="${OVERLAY_APP}/Contents/MacOS/JarvisOverlay"
if [[ "${MODE}" == "full" ]] && [[ -f "${OVERLAY_DIR}/JarvisOverlay.swift" ]]; then
    if command -v swiftc &>/dev/null; then
        # Build if executable is missing (not just .app directory)
        if [[ ! -x "${OVERLAY_BIN}" ]]; then
            # Clean stale/broken builds
            rm -rf "${OVERLAY_DIR}/build" 2>/dev/null || true
            echo "Building JARVIS Desktop Overlay..."
            # Run in subshell so build failure does not kill start.sh
            set +e
            (cd "${OVERLAY_DIR}" && bash build-overlay.sh) 2>&1 | tail -5
            BUILD_EXIT=${PIPESTATUS[0]}
            set -e
            if [[ "${BUILD_EXIT}" -eq 0 ]]; then
                echo "Overlay build succeeded."
            else
                echo "Warning: Overlay build failed (exit ${BUILD_EXIT}). JARVIS will continue without the desktop overlay."
                echo "         You can retry manually: cd desktop-overlay && bash build-overlay.sh"
            fi
        fi
        if [[ -x "${OVERLAY_BIN}" ]]; then
            # Kill any orphaned overlay instances from previous runs
            pkill -f "JarvisOverlay" 2>/dev/null || true
            sleep 0.5
            echo "Launching Desktop Overlay..."
            # Launch the binary directly (not via 'open') so we get the real PID
            "${OVERLAY_BIN}" &
            OVERLAY_PID=$!
        fi
    else
        echo "Note: swiftc not found. Skipping desktop overlay build."
        echo "      Install Xcode Command Line Tools with: xcode-select --install"
    fi
fi

cd "${SCRIPT_DIR}"

# Start the Next.js UI for modes that need it
if [[ "${MODE}" == "full" || "${MODE}" == "server" ]]; then
    if [[ -d "${UI_DIR}" ]] && [[ -f "${UI_DIR}/package.json" ]]; then
        # Check if node_modules exist
        if [[ ! -d "${UI_DIR}/node_modules" ]]; then
            echo "Installing UI dependencies..."
            (cd "${UI_DIR}" && npm install)
        fi

        # Kill any orphaned processes on ports 3000/3001 from a previous run
        # lsof can return multiple PIDs (one per line), so iterate over each
        while IFS= read -r pid; do
            if [[ -n "${pid}" ]]; then
                echo "Port 3000/3001 in use (PID: ${pid}). Killing orphaned process..."
                kill "${pid}" 2>/dev/null || true
            fi
        done < <(lsof -ti :3000,:3001 2>/dev/null || true)
        # Give the OS a moment to release the port
        sleep 1

        echo "Starting JARVIS UI on http://0.0.0.0:3000 ..."
        (cd "${UI_DIR}" && npm run dev -- --hostname 0.0.0.0 --port 3000) &
        UI_PID=$!
        # Give the dev server a moment to start
        sleep 3
    else
        echo "Warning: UI directory not found at ${UI_DIR}. Skipping UI."
    fi
fi

# Start Cloudflare Tunnel for mobile/remote access (if cloudflared is installed).
# The tunnel exposes the Next.js UI (port 3000) over HTTPS. API and WebSocket
# requests from the phone are proxied through Next.js rewrites, so only one
# tunnel is needed. The tunnel URL is printed to the console.
if [[ -n "${CLOUDFLARED_AVAILABLE}" ]] && [[ "${MODE}" == "full" || "${MODE}" == "server" ]]; then
    echo ""
    echo "Starting Cloudflare Tunnel..."
    TUNNEL_LOG="${SCRIPT_DIR}/data/logs/cloudflared.log"
    mkdir -p "$(dirname "${TUNNEL_LOG}")"
    cloudflared tunnel --url http://localhost:3000 --no-autoupdate 2>"${TUNNEL_LOG}" &
    TUNNEL_PID=$!
    # Wait for cloudflared to print the tunnel URL (usually takes 3-5 seconds)
    echo "Waiting for tunnel URL..."
    for i in {1..15}; do
        TUNNEL_URL=$(grep -oE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "${TUNNEL_LOG}" 2>/dev/null | head -1 || true)
        if [[ -n "${TUNNEL_URL}" ]]; then
            # Read the PIN from the auth hash file location.
            # The Python process prints the PIN to stdout, but we also
            # display it here in the tunnel URL banner for convenience.
            echo ""
            echo "=================================================="
            echo "  JARVIS Mobile Access (open on your phone):"
            echo "  ${TUNNEL_URL}"
            echo ""
            echo "  You will be prompted for a PIN on first connect."
            echo "  The PIN is shown above when JARVIS starts."
            echo "=================================================="
            echo ""
            break
        fi
        sleep 1
    done
    if [[ -z "${TUNNEL_URL:-}" ]]; then
        echo "Warning: Could not get tunnel URL. Check ${TUNNEL_LOG} for details."
        echo "  JARVIS still works locally at http://localhost:3000"
    fi
fi

# Launch JARVIS backend
python -m jarvis.main "${MODE}"
