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

read_env_value() {
    local key="$1"
    if [[ -f "${SCRIPT_DIR}/.env" ]]; then
        grep -E "^${key}=" "${SCRIPT_DIR}/.env" | tail -1 | cut -d= -f2- || true
    fi
}

API_PORT="${API_PORT:-$(read_env_value API_PORT)}"
API_PORT="${API_PORT:-8741}"
UI_PORT="${UI_PORT:-$(read_env_value UI_PORT)}"
UI_PORT="${UI_PORT:-3000}"
NEXT_FALLBACK_PORT=$((UI_PORT + 1))
JARVIS_OPEN_DASHBOARD="${JARVIS_OPEN_DASHBOARD:-$(read_env_value JARVIS_OPEN_DASHBOARD)}"
JARVIS_OPEN_DASHBOARD="${JARVIS_OPEN_DASHBOARD:-true}"

# Track child PIDs for cleanup
UI_PID=""
NEXTJS_PID=""
PROXY_PID=""
OLLAMA_PID=""
TUNNEL_PID=""
OVERLAY_PID=""
RUNTIME_DIR="${SCRIPT_DIR}/data/runtime"
LIFECYCLE_FILE="${RUNTIME_DIR}/lifecycle.json"

write_lifecycle_state() {
    local lifecycle_status="${1:-running}"
    if ! command -v python >/dev/null 2>&1; then
        return 0
    fi
    mkdir -p "${RUNTIME_DIR}"
    JARVIS_LIFECYCLE_STATUS="${lifecycle_status}" \
    JARVIS_LIFECYCLE_FILE="${LIFECYCLE_FILE}" \
    JARVIS_LIFECYCLE_MODE="${MODE}" \
    JARVIS_LIFECYCLE_HOME="${SCRIPT_DIR}" \
    JARVIS_API_PORT_VALUE="${API_PORT}" \
    JARVIS_UI_PORT_VALUE="${UI_PORT}" \
    JARVIS_PARENT_PID="$$" \
    JARVIS_UI_PID="${UI_PID}" \
    JARVIS_NEXTJS_PID="${NEXTJS_PID}" \
    JARVIS_PROXY_PID="${PROXY_PID}" \
    JARVIS_OLLAMA_PID="${OLLAMA_PID}" \
    JARVIS_TUNNEL_PID="${TUNNEL_PID}" \
    JARVIS_OVERLAY_PID="${OVERLAY_PID}" \
    python - <<'PY' || true
import json
import os
import time
from pathlib import Path

path = Path(os.environ["JARVIS_LIFECYCLE_FILE"])
previous = {}
if path.exists():
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        previous = {}

status = os.environ.get("JARVIS_LIFECYCLE_STATUS", "running")
started_at = time.time() if status == "starting" else previous.get("started_at") or time.time()
payload = {
    "status": status,
    "mode": os.environ.get("JARVIS_LIFECYCLE_MODE", "full"),
    "jarvis_home": os.environ.get("JARVIS_LIFECYCLE_HOME", ""),
    "api_port": int(os.environ.get("JARVIS_API_PORT_VALUE") or 8741),
    "ui_port": int(os.environ.get("JARVIS_UI_PORT_VALUE") or 3000),
    "started_at": started_at,
    "updated_at": time.time(),
    "processes": {
        "parent_pid": os.environ.get("JARVIS_PARENT_PID", ""),
        "ui_pid": os.environ.get("JARVIS_UI_PID", ""),
        "nextjs_pid": os.environ.get("JARVIS_NEXTJS_PID", ""),
        "proxy_pid": os.environ.get("JARVIS_PROXY_PID", ""),
        "ollama_pid": os.environ.get("JARVIS_OLLAMA_PID", ""),
        "tunnel_pid": os.environ.get("JARVIS_TUNNEL_PID", ""),
        "overlay_pid": os.environ.get("JARVIS_OVERLAY_PID", ""),
    },
}
path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
PY
}

stop_listeners_on_ports() {
    local ports=("$@")
    local pids=""
    local pid=""
    local port=""
    for port in "${ports[@]}"; do
        while IFS= read -r pid; do
            if [[ -n "${pid}" ]]; then
                pids="${pids} ${pid}"
            fi
        done < <(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null || true)
    done

    if [[ -z "${pids// /}" ]]; then
        return 0
    fi

    echo "Stopping stale listener(s) on port(s) ${ports[*]}:${pids}"
    for pid in ${pids}; do
        kill "${pid}" 2>/dev/null || true
    done

    for _ in {1..20}; do
        local any_running=""
        for pid in ${pids}; do
            if kill -0 "${pid}" 2>/dev/null; then
                any_running="true"
            fi
        done
        if [[ -z "${any_running}" ]]; then
            return 0
        fi
        sleep 0.25
    done

    for pid in ${pids}; do
        if kill -0 "${pid}" 2>/dev/null; then
            echo "Force stopping stale listener PID ${pid}..."
            kill -9 "${pid}" 2>/dev/null || true
        fi
    done
}

wait_for_http() {
    local url="$1"
    local attempts="${2:-20}"
    for _ in $(seq 1 "${attempts}"); do
        if curl -fsS -m 1 -I "${url}" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.5
    done
    return 1
}

cleanup() {
    echo ""
    echo "Shutting down JARVIS..."
    write_lifecycle_state "stopping"
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
    # Final sweep: kill anything still holding the UI ports
    stop_listeners_on_ports "${UI_PORT}" "${NEXT_FALLBACK_PORT}"
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
    write_lifecycle_state "stopped"
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
write_lifecycle_state "starting"

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

        # Kill stale listeners on the configured UI ports from a previous run.
        stop_listeners_on_ports "${UI_PORT}" "${NEXT_FALLBACK_PORT}"
        # Give the OS a moment to release the port
        sleep 1

        echo "Starting JARVIS UI on http://0.0.0.0:${UI_PORT} ..."
        (cd "${UI_DIR}" && JARVIS_API_PORT="${API_PORT}" npm run dev -- --hostname 0.0.0.0 --port "${UI_PORT}") &
        UI_PID=$!
        if ! wait_for_http "http://127.0.0.1:${UI_PORT}" 24; then
            echo "Warning: UI did not become ready on port ${UI_PORT}. Retrying once..."
            if kill -0 "${UI_PID}" 2>/dev/null; then
                kill "${UI_PID}" 2>/dev/null || true
                wait "${UI_PID}" 2>/dev/null || true
            fi
            stop_listeners_on_ports "${UI_PORT}" "${NEXT_FALLBACK_PORT}"
            sleep 1
            (cd "${UI_DIR}" && JARVIS_API_PORT="${API_PORT}" npm run dev -- --hostname 0.0.0.0 --port "${UI_PORT}") &
            UI_PID=$!
            if ! wait_for_http "http://127.0.0.1:${UI_PORT}" 24; then
                echo "Warning: JARVIS UI is still not responding at http://localhost:${UI_PORT}."
                echo "         Check the UI error above or rerun ./start.sh after freeing port ${UI_PORT}."
            fi
        fi
        if [[ "${JARVIS_OPEN_DASHBOARD}" != "false" && "${JARVIS_OPEN_DASHBOARD}" != "0" ]] && command -v open &>/dev/null; then
            echo "Opening JARVIS Dashboard at http://localhost:${UI_PORT} ..."
            open "http://localhost:${UI_PORT}" >/dev/null 2>&1 || true
        fi
    else
        echo "Warning: UI directory not found at ${UI_DIR}. Skipping UI."
    fi
fi

# Start Cloudflare Tunnel for mobile/remote access (if cloudflared is installed).
# The tunnel exposes the Next.js UI over HTTPS. API and WebSocket
# requests from the phone are proxied through Next.js rewrites, so only one
# tunnel is needed. The tunnel URL is printed to the console.
if [[ -n "${CLOUDFLARED_AVAILABLE}" ]] && [[ "${MODE}" == "full" || "${MODE}" == "server" ]]; then
    echo ""
    echo "Starting Cloudflare Tunnel..."
    TUNNEL_LOG="${SCRIPT_DIR}/data/logs/cloudflared.log"
    mkdir -p "$(dirname "${TUNNEL_LOG}")"
    cloudflared tunnel --url "http://localhost:${UI_PORT}" --no-autoupdate 2>"${TUNNEL_LOG}" &
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
        echo "  JARVIS still works locally at http://localhost:${UI_PORT}"
    fi
fi

write_lifecycle_state "running"

# Launch JARVIS backend
python -m jarvis.main "${MODE}"
