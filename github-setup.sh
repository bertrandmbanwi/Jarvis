#!/usr/bin/env bash
# ============================================================
# JARVIS GitHub Setup Script
# Run this ON YOUR MAC (not in the Cowork sandbox).
#
# Prerequisites:
#   - GitHub CLI installed: brew install gh
#   - Authenticated: gh auth login
#
# Usage: ./github-setup.sh
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

REPO_NAME="Jarvis"
GITHUB_USER=$(gh api user --jq '.login' 2>/dev/null || echo "")

if [[ -z "${GITHUB_USER}" ]]; then
    echo "ERROR: GitHub CLI not authenticated."
    echo "Run: brew install gh && gh auth login"
    exit 1
fi

echo "============================================"
echo " JARVIS GitHub Setup"
echo " User: ${GITHUB_USER}"
echo " Repo: ${GITHUB_USER}/${REPO_NAME}"
echo "============================================"
echo ""

# Step 1: Initialize git repo (if not already)
if [[ ! -d ".git" ]]; then
    echo "[1/4] Initializing git repository..."
    git init
    git branch -m main
else
    echo "[1/4] Git repo already initialized."
fi

# Step 2: Stage and commit
echo "[2/4] Staging files and creating initial commit..."
git add -A
git status --short | head -20
echo "... ($(git status --short | wc -l | tr -d ' ') files total)"
echo ""

git commit -m "Initial commit: JARVIS personal AI assistant v0.3.0

Complete Phases 1-6: voice interaction, cinematic web UI, browser automation,
macOS system control, multi-agent coordination, and production hardening.

86 tools across 9+ categories. Tiered LLM routing (Haiku/Sonnet/Opus) with
Kokoro TTS, faster-whisper STT, chunked audio streaming, Opus compression,
per-device audio routing, and Cloudflare tunnel for mobile access."

# Step 3: Create GitHub repo
echo ""
echo "[3/4] Creating public GitHub repository..."
if gh repo view "${GITHUB_USER}/${REPO_NAME}" &>/dev/null; then
    echo "Repository ${GITHUB_USER}/${REPO_NAME} already exists."
else
    gh repo create "${REPO_NAME}" \
        --public \
        --description "JARVIS: Just A Rather Very Intelligent System. A personal AI assistant with voice interaction, cinematic UI, browser automation, and macOS system control." \
        --source . \
        --remote origin
fi

# Step 4: Push
echo ""
echo "[4/4] Pushing to GitHub..."
git push -u origin main

echo ""
echo "============================================"
echo " Done! Your repo is live at:"
echo " https://github.com/${GITHUB_USER}/${REPO_NAME}"
echo "============================================"
echo ""
echo "Next steps (optional):"
echo "  1. Install launchd auto-start:"
echo "     cp com.jarvis.assistant.plist ~/Library/LaunchAgents/"
echo "     launchctl load ~/Library/LaunchAgents/com.jarvis.assistant.plist"
echo ""
echo "  2. Set up Named Cloudflare Tunnel for persistent URL:"
echo "     cloudflared tunnel login"
echo "     cloudflared tunnel create jarvis"
echo "     cloudflared tunnel route dns jarvis jarvis.yourdomain.com"
