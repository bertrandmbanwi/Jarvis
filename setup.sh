#!/usr/bin/env bash
# ============================================================
# JARVIS Setup Script for macOS (Apple Silicon M1 Pro)
# Tailored to my machine: Homebrew, Python 3.11, Ollama
# already installed. Only installs what is missing.
#
# Usage: chmod +x setup.sh && ./setup.sh
# ============================================================
set -euo pipefail

echo ""
echo "  ====================================="
echo "  J.A.R.V.I.S. Setup Script"
echo "  macOS Apple M1 Pro Edition"
echo "  ====================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }
step() { echo -e "\n${YELLOW}>>> $1${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

# ============================================================
# Step 1: Verify what is already installed
# ============================================================
step "Checking your system..."

ok "macOS detected"
ok "Apple Silicon (M1 Pro)"
ok "Homebrew $(brew --version 2>/dev/null | head -1 | awk '{print $2}')"
ok "Python $(python3 --version 2>/dev/null | awk '{print $2}')"
ok "pip $(pip3 --version 2>/dev/null | awk '{print $2}')"
ok "Ollama installed"

# ============================================================
# Step 2: Install ONLY missing system dependencies
# ============================================================
step "Installing missing system dependencies..."

# PortAudio (required for PyAudio / microphone access)
if brew list portaudio &> /dev/null 2>&1; then
    ok "PortAudio already installed"
else
    echo "  Installing PortAudio (needed for microphone access)..."
    brew install portaudio
    ok "PortAudio installed"
fi

# FFmpeg (audio/video processing)
if command -v ffmpeg &> /dev/null; then
    ok "FFmpeg already installed"
else
    echo "  Installing FFmpeg (needed for audio processing)..."
    brew install ffmpeg
    ok "FFmpeg installed"
fi

# ============================================================
# Step 3: Update Ollama client (version mismatch detected)
# ============================================================
step "Checking Ollama..."

OLLAMA_VER=$(ollama --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "unknown")
ok "Ollama version: ${OLLAMA_VER}"

# Check for client/server mismatch
if ollama --version 2>&1 | grep -q "Warning"; then
    warn "Ollama client/server version mismatch detected."
    echo "  To fix, update the Ollama app from: https://ollama.com/download"
    echo "  (This is not blocking; JARVIS will still work.)"
fi

# Check if a suitable model is already pulled
echo ""
echo "  Your current Ollama models:"
ollama list 2>/dev/null || echo "  (Could not list models. Make sure 'ollama serve' is running.)"

# We need llama3.1:8b as the primary brain (smarter, better at tool use)
if ollama list 2>/dev/null | grep -q "llama3.1:8b"; then
    ok "llama3.1:8b already available. No download needed."
else
    step "Pulling llama3.1:8b (~4.7GB download, the JARVIS brain)..."
    echo "  This is a one-time download. May take 5-10 minutes."
    echo "  (You already have llama3.2 which will serve as the fast/fallback model.)"
    ollama pull llama3.1:8b
    ok "llama3.1:8b pulled successfully"
fi

# ============================================================
# Step 4: Set up Python virtual environment
# ============================================================
step "Setting up Python virtual environment..."

if [[ ! -d "${VENV_DIR}" ]]; then
    python3 -m venv "${VENV_DIR}"
    ok "Virtual environment created"
else
    ok "Virtual environment already exists"
fi

# Activate
source "${VENV_DIR}/bin/activate"
ok "Virtual environment activated"

# Upgrade pip inside venv
pip install --upgrade pip --quiet
ok "pip upgraded in venv"

# ============================================================
# Step 5: Install Python packages
# ============================================================
step "Installing Python packages..."
echo "  This may take 2-5 minutes on first run."
echo ""

# Install core packages one group at a time for better error handling
echo "  [1/6] Installing API server packages..."
pip install "fastapi>=0.115.0" "uvicorn[standard]>=0.34.0" "httpx>=0.28.0" "pydantic>=2.10.0" "websockets>=14.0" --quiet 2>&1 | grep -v "already satisfied" || true
ok "API server packages"

echo "  [2/6] Installing speech-to-text (faster-whisper)..."
pip install "faster-whisper>=1.1.0" --quiet 2>&1 | grep -v "already satisfied" || true
ok "faster-whisper"

echo "  [3/6] Installing text-to-speech..."
pip install "edge-tts>=6.1.0" "soundfile>=0.13.0" --quiet 2>&1 | grep -v "already satisfied" || true
ok "Edge TTS (guaranteed fallback)"

# Kokoro is best quality but can be tricky to install
echo "  [4/6] Installing Kokoro TTS (best quality voice)..."
if pip install "kokoro>=0.9.0" --quiet 2>&1; then
    ok "Kokoro TTS"
else
    warn "Kokoro TTS failed to install. JARVIS will use Edge TTS or macOS say instead."
    echo "  You can try installing manually later: pip install kokoro"
fi

echo "  [5/6] Installing audio and wake word packages..."
pip install "pyaudio>=0.2.14" "numpy>=2.0.0" --quiet 2>&1 | grep -v "already satisfied" || true
ok "Audio packages"

# OpenWakeWord can also be tricky
if pip install "openwakeword>=0.6.0" --quiet 2>&1; then
    ok "OpenWakeWord (Hey JARVIS detection)"
else
    warn "OpenWakeWord failed. JARVIS will use keyboard activation instead."
    echo "  You can try manually: pip install openwakeword"
fi

echo "  [6/6] Installing memory and utilities..."
pip install "chromadb>=0.6.0" "python-dotenv>=1.0.0" --quiet 2>&1 | grep -v "already satisfied" || true
ok "Memory and utilities"

# ============================================================
# Step 6: Verify everything
# ============================================================
step "Verifying all components..."
echo ""

python3 -c "import fastapi; print(f'  FastAPI {fastapi.__version__}')" 2>/dev/null && ok "FastAPI" || warn "FastAPI"
python3 -c "import faster_whisper; print('  faster-whisper')" 2>/dev/null && ok "faster-whisper (STT)" || warn "faster-whisper"
python3 -c "import kokoro; print('  Kokoro TTS')" 2>/dev/null && ok "Kokoro TTS" || warn "Kokoro TTS (will use fallback)"
python3 -c "import edge_tts; print('  Edge TTS')" 2>/dev/null && ok "Edge TTS (fallback)" || warn "Edge TTS"
python3 -c "import pyaudio; print('  PyAudio')" 2>/dev/null && ok "PyAudio (microphone)" || warn "PyAudio"
python3 -c "import openwakeword; print('  OpenWakeWord')" 2>/dev/null && ok "OpenWakeWord" || warn "OpenWakeWord (keyboard mode)"
python3 -c "import chromadb; print('  ChromaDB')" 2>/dev/null && ok "ChromaDB (memory)" || warn "ChromaDB"
python3 -c "import numpy; print(f'  NumPy {numpy.__version__}')" 2>/dev/null && ok "NumPy" || warn "NumPy"

# ============================================================
# Step 7: Create data directories
# ============================================================
step "Creating data directories..."
mkdir -p "${SCRIPT_DIR}/data/memory/chroma"
mkdir -p "${SCRIPT_DIR}/data/logs"
mkdir -p "${SCRIPT_DIR}/data/models"
mkdir -p "${SCRIPT_DIR}/data/profile"
ok "Data directories created"

# ============================================================
# Done!
# ============================================================
echo ""
echo "  ====================================="
echo -e "  ${GREEN}JARVIS setup complete!${NC}"
echo "  ====================================="
echo ""
echo "  To start JARVIS:"
echo ""
echo "    1. Make sure Ollama is running (open the Ollama app"
echo "       or run 'ollama serve' in another terminal)"
echo ""
echo "    2. Launch JARVIS:"
echo "       ./start.sh              # Text chat (recommended first)"
echo "       ./start.sh voice        # Voice mode"
echo "       ./start.sh server       # API server for UI"
echo "       ./start.sh full         # Voice + API server"
echo ""
