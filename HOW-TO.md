# JARVIS: Setup and Operations Guide

## Prerequisites

Before running JARVIS, make sure you have the following installed on your Mac:

| Tool | Purpose | Install |
|------|---------|---------|
| Python 3.11+ | Backend runtime | `brew install python@3.11` |
| Node.js 18+ | Web UI (Next.js) | `brew install node` |
| Ollama | Local LLM fallback | [ollama.com/download](https://ollama.com/download) |
| FFmpeg | Audio encoding (Opus compression) | `brew install ffmpeg` |
| PortAudio | Microphone access | `brew install portaudio` |
| Homebrew | Package manager | [brew.sh](https://brew.sh) |

Optional (recommended):

| Tool | Purpose | Install |
|------|---------|---------|
| cloudflared | Remote/mobile access via HTTPS tunnel | `brew install cloudflared` |
| Claude Code CLI | Delegate coding tasks via CLI | `npm install -g @anthropic-ai/claude-code` |
| Google Chrome | Required for Chrome Extension (browser bridge) | [google.com/chrome](https://www.google.com/chrome/) |

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/Jarvis.git
cd Jarvis

# 2. Run the setup script (installs Python deps, pulls Ollama models)
chmod +x setup.sh
./setup.sh

# 3. Create your .env file with API keys
cp .env.example .env   # then edit with your keys
# OR create manually:
echo 'ANTHROPIC_API_KEY=sk-ant-your-key-here' > .env

# 4. Start JARVIS
./start.sh full
```

JARVIS will be available at **http://localhost:3000** in your browser.

## Environment Variables (.env)

Create a `.env` file in the project root. `ANTHROPIC_API_KEY` is required for the cloud LLM backend. Without it, JARVIS falls back to Ollama (local, free, slower).

```bash
# Required for cloud LLM intelligence
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here

# Optional: override LLM model tiers
CLAUDE_FAST_MODEL=claude-haiku-4-5-20251001
CLAUDE_BRAIN_MODEL=claude-sonnet-4-6
CLAUDE_DEEP_MODEL=claude-opus-4-6

# Optional: prefer local Ollama instead of cloud API
PREFER_CLAUDE=true

# Optional: TTS configuration
TTS_ENGINE=kokoro           # kokoro | edge | say
TTS_VOICE=bf_emma           # Kokoro voice ID (bf = British female)
TTS_SPEED=1.05
TTS_BROWSER_FORMAT=opus     # opus | wav

# Optional: STT configuration (Moonshine is primary, faster-whisper is fallback)
STT_ENGINE=auto             # moonshine | faster-whisper | whisper | auto
WHISPER_MODEL=small.en      # tiny.en | small.en | medium.en | large-v3

# Optional: cost alerts (USD)
COST_DAILY_ALERT=2.00
COST_MONTHLY_ALERT=60.00

# Optional: port overrides
API_PORT=8741               # Backend API server
UI_PORT=3741                # Next.js dev server (proxied to 3000)

# Optional: Ollama configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_FAST_MODEL=llama3.2:latest
```

## Start Modes

JARVIS supports four launch modes:

```bash
./start.sh text     # Terminal text chat only (no UI, no voice)
./start.sh voice    # Voice interaction only (no web UI)
./start.sh server   # API server + web UI only (no local voice)
./start.sh full     # Everything: voice + API + UI + overlay + tunnel (recommended)
```

**Default mode** is `full` if you run `./start.sh` with no arguments.

### What `./start.sh full` launches

The full startup sequence brings up six components in order:

1. **Ollama** (if not already running): Local LLM backend on port 11434
2. **Desktop Overlay** (macOS only): Native Swift overlay app, built from source
3. **Next.js UI**: Web interface on port 3000
4. **Cloudflare Tunnel** (if cloudflared is installed): HTTPS URL for mobile access
5. **JARVIS Backend**: FastAPI server on port 8741 with voice listener
6. **Chrome Extension** (if installed): Auto-connects via WebSocket within ~30 seconds

The script also handles cleanup of orphaned processes from previous runs, installs missing dependencies (python-multipart, Playwright Chromium, PyYAML), and sets up a persistent browser profile.

## Chrome Extension (Browser Bridge)

The Chrome extension gives JARVIS direct control over your browser tabs, navigation, page content, forms, and screenshots.

### Installation

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable **Developer mode** (toggle in the top-right corner)
3. Click **Load unpacked**
4. Select the `jarvis/extensions/chrome/` directory from the JARVIS project
5. The JARVIS extension icon will appear in your toolbar

### How It Works

The extension connects to the JARVIS backend via WebSocket (`ws://localhost:8741/ws/extension`). It uses a `chrome.alarms` keepalive that fires every ~24 seconds, surviving Chrome's Manifest V3 service worker termination. This means:

- Start Chrome first, then start JARVIS: the extension auto-connects within ~30 seconds
- Start JARVIS first, then open Chrome: the extension connects immediately on load
- JARVIS restarts: the extension detects the new server and reconnects automatically
- No manual interaction needed: you never have to click the extension icon for it to come online

### Badge Status

The extension icon shows a badge indicating connection status:

| Badge | Meaning |
|-------|---------|
| (no badge, green) | Connected to JARVIS |
| ! (gray) | Disconnected, retrying |
| ... (orange) | Processing a command |

### Capabilities

JARVIS can ask the extension to: list open tabs, open/close/switch tabs, navigate to URLs, take screenshots of the active tab, read page content, click elements, type text, fill forms, scroll, and execute scoped JavaScript (restricted to localhost and JARVIS tunnel URLs).

### Extension Popup

Click the extension icon to see connection status, manually connect/disconnect, or send the current page to JARVIS for analysis.

## Desktop Overlay (macOS)

The desktop overlay is a native Swift application that shows JARVIS' state as a floating panel above all windows.

### What It Shows

- A miniature particle orb (Three.js rendered in WKWebView)
- Current state label: STANDING BY, LISTENING, PROCESSING, SPEAKING
- User utterance text (what you said)
- JARVIS response text (what it is saying)
- Color-coded status dot matching the current state

### Building Manually

The overlay is built automatically by `./start.sh full`. To build and run it manually:

```bash
cd desktop-overlay
bash build-overlay.sh
open build/JarvisOverlay.app
```

The overlay connects to JARVIS via `ws://localhost:8741/ws/overlay` and updates in real-time.

### Configuration

The overlay window is positioned in the bottom-right corner of the screen with 50px padding. It ignores mouse events (click-through) and appears on all Spaces. The app runs as a background agent (no Dock icon, no menu bar entry).

## Accessing from Your Phone

JARVIS includes built-in Cloudflare Tunnel support for mobile access. When you have `cloudflared` installed, the tunnel starts automatically with `./start.sh full`.

The console will print a URL like:
```
https://random-words-here.trycloudflare.com
```

Open that URL on your phone's browser. The JARVIS UI is fully responsive and the microphone works over HTTPS. You will be prompted for a PIN on first connect (displayed in the JARVIS console on your Mac).

For a persistent URL (instead of random words each time), set up a Named Cloudflare Tunnel:
```bash
cloudflared tunnel login
cloudflared tunnel create jarvis
cloudflared tunnel route dns jarvis jarvis.yourdomain.com
```

## Auto-Start on Boot (macOS launchd)

To have JARVIS start automatically when you log into your Mac:

```bash
# Copy the launchd plist to your LaunchAgents
cp com.jarvis.assistant.plist ~/Library/LaunchAgents/

# Edit the plist if JARVIS is not in ~/Jarvis
# (update the path in ProgramArguments)

# Load (activate) the service
launchctl load ~/Library/LaunchAgents/com.jarvis.assistant.plist

# Verify it is running
launchctl list | grep jarvis

# To stop the auto-start service
launchctl unload ~/Library/LaunchAgents/com.jarvis.assistant.plist
```

Logs are written to `/tmp/jarvis-stdout.log` and `/tmp/jarvis-stderr.log`.

## Project Structure

```
Jarvis/
  .env                        # Your API keys (git-ignored)
  setup.sh                    # One-time setup script
  start.sh                    # Launch script (text/voice/server/full)
  requirements.txt            # Python dependencies
  com.jarvis.assistant.plist  # macOS auto-start config
  tests/                      # Unit tests (pytest)
  templates/prompts/          # Structured prompt templates (build, feature, fix, etc.)
  desktop-overlay/
    JarvisOverlay.swift       # macOS native overlay (Swift + WKWebView)
    build-overlay.sh          # Compile and bundle into .app
  jarvis/
    main.py                   # Entry point and mode router
    config/
      settings.py             # All configuration in one place
    core/
      server.py               # FastAPI + WebSocket server (UI, overlay, extension)
      brain.py                # Conversation engine, tool dispatch
      llm.py                  # LLM API + Ollama backend abstraction
      auth.py                 # PIN-based mobile authentication
      cache.py                # Response caching layer
      cost_tracker.py         # Per-request cost logging
      hardening.py            # Rate limiting, input validation, retry logic
      perf.py                 # Performance monitoring
      proactive.py            # Proactive suggestions engine
      profile.py              # User preference learning
      settings_api.py         # REST API for runtime settings
      dispatch_registry.py    # Task routing registry + success tracker
      monitor.py              # Conversation quality monitor
    agent/
      coordinator.py          # Multi-agent task orchestration
      planner.py              # Task decomposition (plan-and-execute)
      executor.py             # Subtask execution with tool access
      qa_agent.py             # Quality assurance verification
      task_tracker.py         # Persistent plan state
      tools_schema.py         # Tool definitions for LLM tool-use
      learning.py             # Pattern learning from past plans
      suggestions.py          # Proactive follow-up suggestions
      templates.py            # Structured prompt template library
      template_evolution.py   # Template A/B testing and evolution
      evolution_pipeline.py   # Cross-session performance evolution
      ab_testing.py           # A/B testing framework
    memory/
      store.py                # Abstract memory interface
      sqlite_store.py         # SQLite-backed semantic memory
      facts.py                # Explicit user fact storage
      preferences.py          # Implicit preference tracking
    tools/
      mac_control.py          # macOS: apps, system, volume, brightness
      filesystem.py           # File operations: read, write, search
      shell.py                # Terminal command execution
      screen.py               # Screenshots and OCR
      weather.py              # Weather lookups
      web_search.py           # DuckDuckGo search
      web_browse.py           # Fetch and parse web pages
      browser_agent.py        # Playwright browser automation
      calendar_email.py       # Calendar and email via Chrome/Gmail
      chrome_extension.py     # Chrome extension bridge (tab/DOM control)
      chrome_sync.py          # Chrome cookie sync
      claude_code.py          # Coding CLI delegation
      notes_access.py         # Apple Notes integration
      work_session.py         # Persistent coding sessions
    voice/
      listener.py             # Microphone capture + Moonshine/whisper STT + wake word
      speaker.py              # Kokoro/Edge TTS with chunked Opus streaming
    extensions/
      chrome/                 # Chrome extension (Manifest V3)
        manifest.json         # Extension metadata and permissions
        background.js         # Service worker with alarms keepalive
        content.js            # Content script for DOM interaction
        popup.html            # Extension popup UI
        popup.js              # Popup controller
    ui/
      jarvis-ui/              # Next.js 14 web interface
        src/
          components/
            cinematic/        # WebGL particle orb (Three.js GLSL shaders)
            chat/             # Chat message interface
            dashboard/        # System status dashboard
            auth/             # PIN entry screen
            settings/         # Settings panel (runtime config)
            shared/           # Reusable UI components (status bar, plan progress, etc.)
          hooks/
            useJarvisWebSocket.ts  # WebSocket client with audio routing
```

## Tool Categories

JARVIS has 109+ tools organized into these categories:

| Category | Examples |
|----------|---------|
| macOS Control | Open/close apps, volume, brightness, battery, clipboard, notifications |
| File System | Read, write, move, copy, search, list files and directories |
| Shell | Execute terminal commands with safety guards |
| Screen | Take screenshots, OCR text from screen regions |
| Web Search | DuckDuckGo search, fetch page content, read news |
| Browser Automation | Playwright: fill forms, click buttons, navigate sites, persistent sessions |
| Chrome Extension | Tab management, DOM interaction, screenshots, page reading, form filling |
| Calendar/Email | Read Gmail inbox via Chrome, calendar events |
| Apple Notes | Read, search, and create notes via AppleScript |
| Weather | Current conditions and forecasts |
| Coding CLI | Delegate coding tasks via Claude Code, scaffold projects, smart commands |
| Work Sessions | Persistent multi-step coding sessions that survive restarts |

## Intelligence Tiers

JARVIS uses a tiered model system that routes requests to the appropriate level of intelligence:

| Tier | Model | Use Case | Cost |
|------|-------|----------|------|
| Fast | Claude Haiku 4.5 | Quick lookups, simple responses | Lowest ($1/$5 per 1M tokens) |
| Brain | Claude Sonnet 4.6 | General conversation, tool use | Medium ($3/$15 per 1M tokens) |
| Deep | Claude Opus 4.6 | Complex reasoning, multi-step plans | Highest ($5/$25 per 1M tokens) |
| Local | Ollama (llama3.1:8b) | Offline fallback, no API needed | Free |

The multi-agent planner automatically escalates complex requests to higher tiers and decomposes them into subtasks.

## Voice System

JARVIS supports three TTS engines (in order of quality):

1. **Kokoro** (default): High-quality neural TTS, runs locally, British-accented voices (bf_emma)
2. **Edge TTS**: Microsoft's cloud TTS, good quality, free, requires internet
3. **macOS `say`**: Built-in system voice, lowest quality, always available

Speech-to-text uses a two-tier approach:

1. **Moonshine ONNX** (primary): Low hallucination rate, real-time optimized, runs locally. Tokenizer decodes raw model output into text.
2. **faster-whisper** (fallback): Activates automatically if Moonshine fails or is unavailable. Supports hotwords and language hints.

Wake word detection uses OpenWakeWord with a "hey_jarvis" model. The wake word listener runs continuously in the background with a configurable threshold (default 0.7) and an 8-second followup window after activation.

Audio is streamed to the browser in chunked Opus format (~10x smaller than WAV) for low-latency playback.

## Multi-Agent System

JARVIS includes a full multi-agent pipeline for complex task execution:

| Component | Purpose |
|-----------|---------|
| Planner | Decomposes complex requests into ordered subtasks |
| Executor | Runs each subtask with access to the full tool registry |
| QA Agent | Verifies task quality and retries if below threshold |
| Coordinator | Orchestrates parallel and sequential execution |
| Learning | Captures patterns from successful plans for reuse |
| Evolution Pipeline | A/B tests prompt templates and evolves them over sessions |
| Task Tracker | Persists plan state so multi-step work survives restarts |

The UI shows real-time plan progress via the PlanProgress component, with per-subtask status indicators.

## WebSocket Endpoints

The FastAPI server exposes three WebSocket endpoints:

| Endpoint | Purpose | Client |
|----------|---------|--------|
| `/ws` | Main client connection (voice, chat, audio) | Next.js UI, mobile browser |
| `/ws/overlay` | Desktop overlay state and text updates | JarvisOverlay.app (Swift) |
| `/ws/extension` | Chrome extension command/response channel | Chrome extension (background.js) |

## API Endpoints

Key REST API endpoints:

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /health/ping` | None | Lightweight liveness probe (used by Chrome extension keepalive) |
| `GET /health` | Required | Full health report with backend, memory, cache stats |
| `POST /auth/login` | None | PIN verification, returns session token |
| `GET /auth/status` | None | Check if current request is authenticated |
| `GET /api/settings` | Required | Read runtime settings |
| `PUT /api/settings` | Required | Update runtime settings |
| `POST /voice/transcribe` | None | Upload audio for speech-to-text |
| `POST /clear` | Required | Clear conversation history |

## Testing

JARVIS ships with unit tests. Run them with:

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

Test modules cover: hardening (retry, rate limiting, input sanitization, fork bomb detection), cost tracking, multi-agent coordination and routing, planner heuristics and decomposition, learning/evolution pipeline, and memory subsystems.

To run with coverage:

```bash
python -m pytest tests/ -v --cov=jarvis --cov-report=term-missing
```

## PIN Authentication

JARVIS uses PIN-based authentication for browser and mobile access. The PIN is displayed in the terminal on first launch and persists across restarts.

To regenerate the PIN:

```bash
JARVIS_REGEN_PIN=true ./start.sh full
```

The new PIN will be printed to the console before the server starts. Local connections (from the same machine) bypass PIN authentication automatically.

## Settings Panel

The web UI includes a Settings Panel (gear icon) for runtime configuration. Changes made in the panel are saved via the `/api/settings` REST endpoint and persist across restarts.

You can also query settings directly:

```bash
curl http://localhost:8741/api/settings
```

## Data Storage

JARVIS stores persistent data in the `data/` directory:

| Path | Purpose |
|------|---------|
| `data/auth/` | Authentication credentials and session tokens |
| `data/browser-profile/` | Persistent Chromium profile (cookies, sessions) |
| `data/costs/` | Daily and monthly cost tracking records |
| `data/learning/` | Learned patterns from successful task plans |
| `data/logs/` | Application logs |
| `data/memory/` | Semantic memory database |
| `data/models/` | Local model caches |
| `data/plans/` | Saved multi-step plan states |
| `data/profile/` | User profile and preference data |
| `data/sessions/` | Persistent work session state |
| `data/jarvis_dispatch.db` | Tool dispatch tracking (SQLite) |
| `data/jarvis_experiments.db` | A/B testing experiment data (SQLite) |
| `data/jarvis_memory.db` | Semantic memory with FTS (SQLite) |

## Troubleshooting

**JARVIS won't start:**
Check that Ollama is running (`ollama serve`) and your `.env` has a valid `ANTHROPIC_API_KEY`.

**No voice output in browser:**
Make sure FFmpeg is installed (`brew install ffmpeg`). Check browser console for WebSocket errors.

**Microphone not working:**
Verify PortAudio is installed (`brew install portaudio`). Grant microphone permission to Terminal in System Settings > Privacy > Microphone.

**Mobile access not working:**
Install cloudflared (`brew install cloudflared`). The tunnel URL is printed in the console when JARVIS starts.

**Chrome extension not connecting:**
Verify the extension is loaded in `chrome://extensions/` with Developer mode enabled. The extension auto-reconnects every ~24 seconds via the keepalive alarm. Check the extension's service worker console (click "Inspect views: service worker" on the extensions page) for connection logs.

**Desktop overlay not showing:**
The overlay only builds on macOS. Check that `desktop-overlay/build-overlay.sh` ran successfully during startup. You can rebuild manually with `cd desktop-overlay && bash build-overlay.sh && open build/JarvisOverlay.app`.

**High API costs:**
Adjust `COST_DAILY_ALERT` in `.env`. Set `PREFER_CLAUDE=false` to default to local Ollama. The System tab in the UI shows real-time cost tracking.

**Port conflicts:**
JARVIS uses ports 3000 (UI) and 8741 (API). If something else is using those ports, JARVIS will attempt to kill orphaned processes on startup. You can override with `API_PORT` and `UI_PORT` in `.env`.
