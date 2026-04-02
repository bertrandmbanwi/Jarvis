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
TTS_VOICE=bf_emma           # Kokoro voice ID
TTS_SPEED=1.05
TTS_BROWSER_FORMAT=opus     # opus | wav

# Optional: STT configuration (Moonshine is primary, Whisper is fallback)
WHISPER_MODEL=small.en      # tiny.en | small.en | medium.en | large-v3

# Optional: cost alerts (USD)
COST_DAILY_ALERT=2.00
COST_MONTHLY_ALERT=60.00
```

## Start Modes

JARVIS supports four launch modes:

```bash
./start.sh text     # Terminal text chat only (no UI, no voice)
./start.sh voice    # Voice interaction only (no web UI)
./start.sh server   # API server + web UI only (no local voice)
./start.sh full     # Everything: voice + API server + web UI (recommended)
```

**Default mode** is `full` if you run `./start.sh` with no arguments.

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
  tests/                      # 265 unit tests (pytest)
  templates/prompts/          # Structured prompt templates (build, feature, fix, etc.)
  jarvis/
    main.py                   # Entry point and mode router
    config/
      settings.py             # All configuration in one place
    core/
      server.py               # FastAPI + WebSocket server
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
      task_tracker.py         # Persistent plan state
      tools_schema.py         # Tool definitions for LLM tool-use
      learning.py             # Pattern learning from past plans
      suggestions.py          # Proactive follow-up suggestions
      templates.py            # Structured prompt template library
      template_evolution.py   # Template A/B testing and evolution
      evolution_pipeline.py   # Cross-session performance evolution
    memory/
      store.py                # ChromaDB vector memory
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
      chrome_extension.py     # Chrome extension bridge
      chrome_sync.py          # Chrome cookie sync
      claude_code.py          # Coding CLI delegation
      work_session.py         # Persistent coding sessions
    voice/
      listener.py             # Microphone capture + Moonshine/whisper STT
      speaker.py              # Kokoro/Edge TTS with chunked streaming
    ui/
      jarvis-ui/              # Next.js 14 web interface
        src/
          components/
            cinematic/        # WebGL particle orb (Three.js)
            chat/             # Chat message interface
            dashboard/        # System status dashboard
            auth/             # PIN entry screen
            settings/         # Settings panel (runtime config)
            shared/           # Reusable UI components
          hooks/
            useJarvisWebSocket.ts  # WebSocket client with audio routing
```

## Tool Categories

JARVIS has 93+ tools organized into these categories:

| Category | Examples |
|----------|---------|
| macOS Control | Open/close apps, volume, brightness, battery, clipboard, notifications |
| File System | Read, write, move, copy, search, list files and directories |
| Shell | Execute terminal commands with safety guards |
| Screen | Take screenshots, OCR text from screen regions |
| Web Search | DuckDuckGo search, fetch page content, read news |
| Browser Automation | Playwright-driven: fill forms, click buttons, navigate sites |
| Calendar/Email | Read Gmail inbox via Chrome, calendar events |
| Weather | Current conditions and forecasts |
| Coding CLI | Delegate coding tasks, scaffold projects, run smart commands |

## Intelligence Tiers

JARVIS uses a tiered model system that routes requests to the appropriate level of intelligence:

| Tier | Purpose | Use Case | Cost |
|------|---------|----------|------|
| Fast | Lightweight model | Quick lookups, simple responses | Lowest |
| Brain | Mid-tier model | General conversation, tool use | Medium |
| Deep | Reasoning model | Complex reasoning, multi-step plans | Highest |
| Local | Ollama (offline) | Offline fallback, no API needed | Free |

The multi-agent planner automatically escalates complex requests to higher tiers and decomposes them into subtasks.

## Voice System

JARVIS supports three TTS engines (in order of quality):

1. **Kokoro** (default): High-quality neural TTS, runs locally, British-accented voices
2. **Edge TTS**: Microsoft's cloud TTS, good quality, free, requires internet
3. **macOS `say`**: Built-in system voice, lowest quality, always available

Speech-to-text uses a two-tier approach:

1. **Moonshine ONNX** (primary): Low hallucination rate, real-time optimized, runs locally. Tokenizer decodes raw model output into text.
2. **faster-whisper** (fallback): Activates automatically if Moonshine fails or is unavailable. Supports hotwords and language hints.

Audio is streamed to the browser in chunked Opus format (~10x smaller than WAV) for low-latency playback.

## Testing

JARVIS ships with 265 unit tests. Run them with:

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

The new PIN will be printed to the console before the server starts.

## Settings Panel

The web UI includes a Settings Panel (gear icon) for runtime configuration. Changes made in the panel are saved via the `/api/settings` REST endpoint and persist across restarts.

You can also query settings directly:

```bash
curl http://localhost:8741/api/settings
```

## Troubleshooting

**JARVIS won't start:**
Check that Ollama is running (`ollama serve`) and your `.env` has a valid `ANTHROPIC_API_KEY`.

**No voice output in browser:**
Make sure FFmpeg is installed (`brew install ffmpeg`). Check browser console for WebSocket errors.

**Microphone not working:**
Verify PortAudio is installed (`brew install portaudio`). Grant microphone permission to Terminal in System Settings > Privacy > Microphone.

**Mobile access not working:**
Install cloudflared (`brew install cloudflared`). The tunnel URL is printed in the console when JARVIS starts.

**High API costs:**
Adjust `COST_DAILY_ALERT` in `.env`. Set `PREFER_CLAUDE=false` to default to local Ollama. The System tab in the UI shows real-time cost tracking.

**Port conflicts:**
JARVIS uses ports 3000 (UI) and 8741 (API). If something else is using those ports, JARVIS will attempt to kill orphaned processes on startup. You can override with `API_PORT` and `UI_PORT` in `.env`.
