# JARVIS Project Handoff Document

**Date:** March 24, 2026
**Author:** Becs (with Claude assistance)
**Version:** 0.3.0
**Platform:** macOS (Apple Silicon M1 Pro)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture Summary](#2-architecture-summary)
3. [Project Structure](#3-project-structure)
4. [Phase Status](#4-phase-status)
5. [What Has Been Completed](#5-what-has-been-completed)
6. [Current Difficulties and Unresolved Issues](#6-current-difficulties-and-unresolved-issues)
7. [What Remains To Be Done](#7-what-remains-to-be-done)
8. [Key Files Reference](#8-key-files-reference)
9. [Environment Setup](#9-environment-setup)
10. [How to Run](#10-how-to-run)
11. [Technical Decisions and Tradeoffs](#11-technical-decisions-and-tradeoffs)
12. [Known Bugs and Workarounds](#12-known-bugs-and-workarounds)

---

## 1. Project Overview

JARVIS (Just A Rather Very Intelligent System) is a personal AI assistant inspired by Iron Man's JARVIS. It combines voice interaction, a cinematic web UI, browser automation, and macOS system control into a single assistant that runs locally on your Mac.

The goal: talk to JARVIS from your phone or laptop, have it respond with voice on the device you spoke from, and have it carry out tasks on your Mac (browse the web, control apps, run shell commands, write code) all while you may be away from the computer.

**Core Tech Stack:**

- Backend: Python 3.11 + FastAPI + WebSocket
- Frontend: React 18 + Next.js 14 + TypeScript + Tailwind CSS + Three.js (Arc Reactor)
- Intelligence: Anthropic Claude API (Haiku/Sonnet/Opus tiers) + Ollama local fallback
- Voice STT: OpenWakeWord (wake word) + faster-whisper (transcription)
- Voice TTS: Kokoro (primary) > Edge TTS (fallback) > macOS `say` (last resort)
- Browser Automation: Chrome Extension (primary, DOM-based) + Playwright + Claude Computer Use API (fallback)
- Memory: ChromaDB vector store
- User Profile: JSON-based preference store (data/profile/profile.json)
- Task Decomposition: Automatic multi-step planning with progress tracking
- Mobile Access: Cloudflare Quick Tunnel (free HTTPS URL)

---

## 2. Architecture Summary

### Multi-Tier LLM Strategy

| Tier   | Model          | Cost/Call | Use Cases                              |
|--------|----------------|-----------|----------------------------------------|
| Fast   | Haiku 4.5      | ~$0.002   | Intent routing, voice acks, simple Q&A |
| Brain  | Sonnet 4.6     | ~$0.015   | Agent tasks, tool use, complex chat    |
| Deep   | Opus 4.6       | ~$0.04    | Multi-step reasoning, code gen         |

### Agentic Architecture (v2)

1. User input arrives (voice or text, from terminal or browser/phone)
2. `JarvisBrain` routes to appropriate LLM tier based on content
3. `AgentExecutor` invokes Claude with tool schemas (native tool_use)
4. Claude decides which tools to call, chains multiple calls as needed
5. Tools execute (shell, browser, filesystem, web search, etc.)
6. Final response returned to user (text + voice)

### Communication Flow

```
Phone/Browser --> Cloudflare Tunnel --> Next.js (port 3000) --> [rewrites] --> FastAPI (port 8741)
                                                                   |
Terminal Voice --> FastAPI directly (port 8741)                    |
                                                                   v
                                                          JarvisBrain --> Claude API / Ollama
                                                              |
                                                          AgentExecutor --> Tools (browser, shell, etc.)
```

### WebSocket Protocol

Messages from server to client:

- `{token, done: false}` - Streaming response tokens
- `{token: "", done: true, full_response, session_cost}` - Stream complete
- `{voice_user_message}` - Voice input from terminal (broadcast to UI)
- `{voice_speaking: true, amplitude_envelope, audio_duration, voice_audio}` - TTS started (with audio data)
- `{voice_speaking: false}` - TTS finished
- `{error}` - Error message

Messages from client to server:

- `{message: "text"}` - Send a chat message
- `{browser_mic: true/false}` - Browser mic recording state (pauses terminal mic)

---

## 3. Project Structure

```
Jarvis/
├── jarvis/
│   ├── main.py                    # Entry point (text/voice/server/full modes)
│   ├── config/settings.py         # Environment config, model tiers, pricing
│   ├── core/
│   │   ├── auth.py                # PIN authentication, session tokens, rate limiting
│   │   ├── brain.py               # Central orchestration, conversation routing
│   │   ├── llm.py                 # Multi-backend LLM engine (Claude + Ollama)
│   │   ├── profile.py             # User profile management (preferences, notes)
│   │   ├── server.py              # FastAPI + WebSocket server (with auth middleware)
│   │   └── cost_tracker.py        # API usage and cost monitoring
│   ├── agent/
│   │   ├── executor.py            # Claude tool-use agentic loop (v2.1: + subtask execution)
│   │   ├── planner.py             # Task decomposition (LLM-powered multi-step planning)
│   │   ├── task_tracker.py        # Subtask state management and plan persistence
│   │   ├── learning.py             # Learning loop (tool stats, plan patterns, failure analysis)
│   │   └── tools_schema.py        # Tool definitions sent to Claude (86 tools)
│   ├── tools/
│   │   ├── browser_agent.py       # Playwright + Claude Computer Use API
│   │   ├── chrome_extension.py     # Chrome Extension WebSocket bridge (DOM tools)
│   │   ├── chrome_sync.py         # Chrome cookie import for Playwright sessions
│   │   ├── claude_code.py         # Claude Code CLI integration
│   │   ├── filesystem.py          # File operations
│   │   ├── calendar_email.py       # Calendar.app + Mail.app integration (AppleScript)
│   │   ├── mac_control.py         # macOS app control (AppleScript)
│   │   ├── screen.py              # Screenshot capture
│   │   ├── shell.py               # Shell command execution
│   │   ├── web_browse.py          # Web content extraction (BeautifulSoup)
│   │   └── web_search.py          # DuckDuckGo search integration
│   ├── voice/
│   │   ├── listener.py            # Wake word + Whisper transcription
│   │   └── speaker.py             # TTS (Kokoro/Edge/macOS say)
│   ├── extensions/chrome/          # JARVIS Browser Bridge Chrome Extension
│   │   ├── manifest.json          # Manifest V3 config
│   │   ├── background.js          # Service worker (WebSocket, tab mgmt)
│   │   ├── content.js             # Content script (DOM interaction)
│   │   ├── popup.html/popup.js    # Extension popup UI
│   │   └── icons/                 # Extension icons (16/48/128px)
│   ├── memory/store.py            # ChromaDB vector memory
│   └── ui/jarvis-ui/              # Next.js frontend
│       ├── next.config.js         # Rewrites for tunnel proxying
│       ├── src/app/page.tsx       # Main page
│       ├── src/components/
│       │   ├── auth/LoginScreen.tsx  # PIN entry for remote access
│       │   ├── cinematic/         # Arc Reactor, Boot Screen, Cinematic View
│       │   ├── chat/ChatView.tsx  # Chat interface
│       │   ├── dashboard/         # Dashboard view
│       │   └── shared/            # ChatInput, StatusBar
│       ├── src/hooks/
│       │   ├── useAuth.ts             # Auth state, login/logout, token management
│       │   ├── useJarvisWebSocket.ts  # WS connection + audio playback
│       │   ├── useVoiceRecorder.ts    # Browser mic + silence detection
│       │   └── useServerStatus.ts     # Server health polling
│       └── src/lib/types.ts       # TypeScript type definitions
├── data/
│   ├── auth/                      # PIN hash + salt files
│   ├── browser-profile/           # Playwright persistent browser state
│   ├── costs/                     # Cost tracking logs
│   ├── logs/                      # App logs + cloudflared.log
│   ├── memory/                    # ChromaDB store
│   └── models/                    # Downloaded models (Whisper, Kokoro)
├── setup.sh                       # macOS installation script
├── start.sh                       # Launch script (4 modes)
├── requirements.txt               # Python dependencies
├── .env / .env.example            # Environment configuration
└── *.docx                         # Planning documents
```

---

## 4. Phase Status

### Phase 1: Core Foundation - COMPLETE

- Multi-tier LLM engine (Haiku/Sonnet/Opus + Ollama fallback)
- Agentic tool-use loop (Claude native tool_use)
- Voice I/O (wake word, Whisper STT, Kokoro TTS)
- FastAPI + WebSocket server
- macOS tools (shell, filesystem, app control, screenshots)
- ChromaDB memory store
- Cost tracking with daily/monthly alerts

### Phase 2: Voice + UI Polish - COMPLETE

- Cinematic web UI with Arc Reactor animation (Three.js)
- Boot screen animation
- Three view modes: Cinematic, Chat, Dashboard
- Real-time token streaming via WebSocket
- Voice amplitude envelope visualization (orb syncs with speech)
- Browser-based voice input (MediaRecorder + silence detection)
- Terminal-to-browser voice broadcast
- Browser-to-terminal mic coordination (prevents duplicate capture)
- Pronunciation fixes and text naturalization for TTS

### Phase 3: Browser Automation + Mobile Access - COMPLETE

**Completed items:**
- Playwright persistent browser context (sessions/cookies survive restarts)
- Claude Computer Use API integration (beta 2025-11-24, Sonnet 4.6)
- Browser agent with 30-step safety limit and page-alive abort check
- Cloudflare Quick Tunnel for mobile HTTPS access
- Next.js rewrites for single-URL routing (API + WS through tunnel)
- Tunnel-aware URL detection in all UI hooks
- Base64 WAV audio streaming over WebSocket (all 3 TTS backends: Kokoro, Edge, macOS say)
- Dual audio playback: `<audio>` element (primary, iOS-reliable) + Web Audio API (fallback)
- iOS Safari AudioContext unlock with silent WAV primer during user gesture
- Device-targeted audio routing (phone gets WAV, desktop gets animation only)
- `skip_local_playback` flag prevents Mac speakers during phone-originated requests
- Feedback loop prevention (no follow-up window for browser-originated responses)
- Audio-envelope sync (deferred envelope start until `onplaying` event, real duration from `<audio>` element)
- Browser mic state signaling to server (pauses terminal listener)
- Chrome cookie sync: auto-imports cookies from Chrome into Playwright on launch
- Per-URL cookie sync before navigation (preserves login sessions)
- `sync_browser_sessions` tool for on-demand session import
- Premium UI redesign (glassmorphism, 3-layer design tokens, message bubbles, animations)
- Chrome Extension ("JARVIS Browser Bridge") for direct DOM interaction with user's real Chrome
- Extension WebSocket bridge (ws://localhost:8741/ws/extension) with auto-reconnect
- 10 chrome_* tools: navigate, click, type, read_page, find_elements, screenshot, get_tabs, execute_js, fill_form, scroll
- Hybrid browser strategy: extension-first (fast, cheap) with Playwright/Computer Use fallback
- Extension popup UI with connection status and quick actions
- Cost savings: DOM tools ~$0.01-0.03/task vs Computer Use ~$0.20-0.75/task

**Remaining (low priority):**
- Named Cloudflare Tunnel for persistent URL (requires a domain)

### Phase 4: Security + Persistence - COMPLETE

**Completed items:**
- PIN-based authentication for remote access (6-digit PIN, SHA-256 hashed with salt)
- Session tokens (64-char hex, 24h expiry) issued on successful PIN verification
- Rate limiting: 5 failed PIN attempts per 60s per IP
- Local connections (localhost/127.0.0.1) bypass authentication entirely
- FastAPI auth dependency on all protected endpoints (status, chat, clear, health, costs, models, voice/transcribe)
- Auth endpoints: POST /auth/login, GET /auth/status, POST /auth/logout, POST /auth/set-pin
- WebSocket authentication via query parameter token
- Login screen in Next.js UI (sleek PIN pad with auto-advance and paste support)
- Auth token stored in sessionStorage, included in all API/WS requests
- PIN displayed in terminal on startup (new PIN on first run, regenerate with JARVIS_REGEN_PIN=true)
- Periodic cleanup of expired sessions (every 5 minutes)
- CORS already restricted to localhost + *.trycloudflare.com (done in Phase 3)
- Conversation persistence already working (100 turns, auto-save to JSON, done in Phase 1)
- Browser visual intelligence: browser_screenshot and browser_navigate now return actual screenshots to Claude so it can SEE the page (catches 404s, login walls, errors)
- New `get_browser_state` tool: lists all open tabs + returns screenshot of active tab
- New `browser_switch_tab` tool: switch between open tabs by number
- New `browser_upload_file` tool: upload files (resumes, documents) to web form file inputs
- Rich tool results: LLM layer and agent executor now support image content blocks in tool results, not just text strings
- Playwright key mapping fix: KEY_TRANSLATION dict normalizes Claude's key names ("ctrl", "super") to Playwright-compatible names ("Control", "Meta")
- Rate limit retry logic: exponential backoff (3 retries at 5s/10s/20s) for Anthropic 429 errors, plus 0.3s inter-step delay
- Browser agent system prompt rewrite: more directive, minimizes wasted steps
- pycookiecheat import fix: single WARNING at startup instead of repeated ERROR logs
- Custom PIN support via JARVIS_PIN env var (4-8 digits, overrides stored PIN on startup)
- User profile management: JSON-based profile at data/profile/profile.json with API endpoints (GET/PUT /profile) and 4 voice-accessible tools (get_user_profile, update_user_profile, get_user_preference, add_user_note)
- Google Chrome set as default browser (was Safari) for open_url_in_browser and search_in_browser
- 57 tools total (was 42), all registered in schema and registry

**Remaining:**
- (none, Phase 4 complete)

### Phase 5: Intelligence Upgrades - COMPLETE

**Completed items:**
- Task decomposition: complex requests auto-detected via heuristics + LLM check, broken into ordered subtask chains by Claude
- TaskPlanner: dual complexity detection (fast heuristics for obvious cases, LLM fallback for ambiguous ones)
- TaskTracker: full subtask lifecycle (pending, in_progress, completed, failed, skipped) with dependency checking
- Plan-then-execute flow in JarvisBrain: planner creates plan, executor runs each subtask with accumulated context, results synthesized into cohesive response
- Prior context forwarding: each subtask receives results from all completed prior steps
- Subtask retry logic: one automatic retry on failure before marking as failed
- Dependency-aware execution: subtasks with failed dependencies are auto-skipped
- Plan persistence: completed plans saved as JSON to data/plans/ for learning loop (Phase 5b)
- WebSocket plan progress events: plan_created, subtask_started, subtask_completed, subtask_failed, subtask_skipped, plan_completed
- REST endpoints: GET /plan (active plan status), GET /plan/history (recent plans)
- 3 new planning tools: get_plan_status, get_plan_history, cancel_active_plan
- 62 tools total (was 57): added 3 plan tools + 2 app paste/write tools
- Learning loops: automatic analysis of completed plans and tool executions for continuous improvement
- LearningLoop class (jarvis/agent/learning.py): records plan outcomes, tool call success/failure, extracts failure patterns
- Tool reliability tracking: per-tool success rates, average durations, unreliable tool detection (< 80% success with 3+ calls)
- Plan pattern recording: decomposition strategies with outcomes (success/partial/failed) for reference
- Failure log with categorized error patterns (timeout, permission denied, auth, rate limit, etc.)
- Learning context injection: planner system prompt is enriched with insights from past executions (unreliable tools, common failures, successful plan examples)
- Executor tool call tracking: every tool execution is timed and recorded with success/failure status
- Backfill on startup: existing plan JSON files are analyzed to bootstrap learning data
- Persistence: tool stats, plan patterns, and failure log saved to data/learning/ as JSON
- REST endpoints: GET /learning (insights summary), GET /learning/tools (tool reliability), GET /learning/failures (failure patterns)
- 2 new learning tools: get_learning_insights, get_tool_reliability (Claude can query its own performance)
- 64 tools total (was 62): added 2 learning tools
- Calendar.app integration via AppleScript: read upcoming events, create events, list calendars, search events
- Mail.app integration via AppleScript: read inbox, get unread count, send email, search emails, read full email content
- No API keys or OAuth needed; uses native macOS apps with existing iCloud/Google/Exchange accounts
- New file: jarvis/tools/calendar_email.py (4 calendar tools + 5 email tools)
- REST endpoints: GET /calendar (today's events), GET /mail/unread (unread count)
- Send email safety: Claude is instructed to always confirm recipient and content before sending
- 73 tools total (was 64): added 4 calendar tools + 5 email tools
- Proactive suggestions engine: background heartbeat that monitors calendar, email, and time-of-day context
- ProactiveEngine class (jarvis/core/proactive.py): async heartbeat loop running every 60s with configurable check intervals per category
- Suggestion categories: calendar (meeting alerts at 15/5 min), email (unread notifications when >= 3), greeting (morning briefing with calendar + email summary), reminder
- Smart cooldowns: per-category cooldown periods prevent notification spam (e.g., 10 min between calendar alerts, 30 min between email notifications)
- Conversation-active suppression: proactive checks pause during active conversations, auto-resume after 2 min idle
- WebSocket suggestion delivery: broadcasts to all connected UI clients with category, message, priority, and spoken flag
- TTS integration: suggestions marked as spoken are voiced aloud via the shared speaker component
- REST endpoints: GET /proactive (engine status), POST /proactive/settings (enable/disable engine or categories)
- 2 new proactive tools: get_proactive_status, set_proactive_setting (Claude can query and control proactive settings)
- 75 tools total (was 73): added 2 proactive tools
- Multi-agent coordination: specialized agent profiles with routing and parallel execution
- AgentCoordinator class (jarvis/agent/coordinator.py): routes subtasks to best-fit agent, manages parallel execution groups
- 7 agent profiles: researcher (web search, info synthesis), coder (shell, files, Claude Code), browser (Chrome extension, Playwright), system (macOS control, apps, clipboard), communicator (email, calendar), analyst (reasoning, summarization), generalist (all tools, fallback)
- Each agent has a focused system prompt and curated tool subset for better performance
- Keyword-based subtask routing: analyzes subtask descriptions to assign the optimal agent
- Parallel execution: independent subtasks (no cross-dependencies) run concurrently via asyncio.gather with configurable max_parallel (default 3)
- Dependency-aware grouping: subtasks are organized into execution groups; within each group, tasks run in parallel; groups execute sequentially
- Per-agent performance tracking: task counts, success rates, average durations per agent type
- REST endpoints: GET /agents (coordinator status), GET /agents/active (running tasks), GET /agents/history (recent execution log)
- 2 new coordinator tools: get_agent_status, get_active_agents (Claude can inspect multi-agent state)
- 77 tools total (was 75): added 2 coordinator tools

**Remaining:**
- (none, Phase 5 complete)

### Phase 6: Polish & Production Readiness - IN PROGRESS

**Phase 6.1: Polish & Hardening (complete):**
- New hardening module: jarvis/core/hardening.py with five core subsystems
- Error classification: categorizes exceptions into 8 types (rate_limit, auth, timeout, network, invalid_input, tool_failure, api_error, resource) with user-friendly messages
- Retry with exponential backoff: configurable RetryPolicy with jitter for API calls; auto-retries rate limits, timeouts, and network errors up to 3 times
- Per-tool timeout guards: 40+ tools have custom timeouts (5s for simple queries, 120s for Claude Code); asyncio.wait_for prevents hung tool calls
- Input sanitization: user input trimmed and length-capped (10K chars), tool arguments validated (5K chars), file paths capped (500 chars)
- Dangerous command detection: warns on destructive shell patterns (rm -rf /, dd to devices, fork bombs) without blocking
- Circuit breakers: per-subsystem failure tracking; after 5 consecutive failures, the circuit opens and requests are rejected for 60s, then half-open recovery test; separate breakers for Claude API, Ollama, and per-tool
- All hardening wired into executor.py (tool timeouts, circuit breakers, input validation), llm.py (API retry, circuit breaker, input sanitization), brain.py (input sanitization for process and process_stream)
- Health report: GET /health now includes circuit breaker states, timeout config, and input limits
- 1 new tool: get_system_health (Claude can check system reliability)
- 78 tools total (was 77)

**Phase 6.2: Performance Tuning (complete):**
- New cache module: jarvis/core/cache.py with TTL-based LRU result caching for tool outputs
- Per-tool TTL configuration: 40+ tools with custom TTLs (5s for active_window, 300s for user_profile); uncacheable tools (mutations, side effects) explicitly excluded
- Cache invalidation map: mutating tools automatically invalidate related read caches (e.g., send_email invalidates unread_email_count)
- Deterministic cache keys: tool_name + sorted(args) hashed via SHA-256 for collision-free lookups
- Size-bounded with LRU eviction: max 200 entries, oldest evicted when full
- Cache metrics: hit/miss rates, per-tool breakdowns, eviction counts
- New perf module: jarvis/core/perf.py with latency profiling across all code paths
- LatencyBucket stats: count, avg, min, max, p90, rolling recent window for each named operation
- Automatic bottleneck detection: flags operations averaging > 3s with actionable suggestions
- Tier usage tracking: counts, avg latency, and downgrade frequency per model tier
- Token estimation: lightweight ~4 chars/token heuristic for cost-aware routing decisions
- Cost-aware tier routing: _select_tier() in brain.py now requires 2+ complexity signals before upgrading to Opus; high-cost-premium requests (> $0.10 extra) need 3+ signals
- Tier downgrade tracking: automatic logging and metrics when requests are downgraded from deep to brain tier
- Per-tool latency recording: every tool execution timed and recorded in perf_tracker
- LLM call timing: chat and agentic loop iterations tracked per tier
- End-to-end request timing: total request duration recorded with tier attribution
- REST endpoints: GET /perf (performance stats), GET /cache (cache stats), POST /cache/clear (flush cache)
- GET /health enriched with perf_summary and cache stats
- 3 new tools: get_perf_stats, get_cache_stats, clear_cache (Claude can inspect and manage performance)
- 81 tools total (was 78)

**Phase 6.3: Persistent Memory Improvements (complete):**
- New fact extraction engine: jarvis/memory/facts.py with 25+ regex patterns across 8 categories
- Fact categories: personal, work, location, preference, relationship, habit, explicit
- Confidence decay (2%/day), deduplication, reinforcement, consolidation (max 500 facts)
- New implicit preference tracker: jarvis/memory/preferences.py
- Tracks 11 topic categories, time-of-day patterns, detail preference, input verbosity
- Recency-weighted scoring with exponential decay
- Upgraded memory store (v2): composes vector store + fact store + preference tracker
- get_enriched_context(): combines all three systems for prompt injection
- process_exchange(): continuous learning after every response
- brain.py: enriched context for fast-tier chat, process_exchange wiring, memory save on shutdown
- 5 new tools: get_user_facts, search_user_facts, forget_fact, get_user_patterns, get_memory_stats
- 86 tools total (was 81)

**Phase 6.4: UI Enhancements (complete):**
- New ProactiveToast component: slide-in notifications for calendar, email, greeting, reminder suggestions
  - Auto-dismiss with countdown bar (8s/12s/18s by priority level)
  - Category-specific icons, accent colors, and glow effects
  - Max 3 visible toasts, glassmorphism styling, keyboard-accessible dismiss
  - Respects prefers-reduced-motion media query
- New PlanProgress component: floating panel showing plan execution in real-time
  - Animated subtask list with status icons (spinner, checkmark draw, X, skip)
  - Per-subtask agent type badges (planner, browser, coder, system)
  - Collapsible to minimal progress bar; auto-scroll to active subtask
  - Progress bar with glow effect; auto-clears 5s after plan completion
- New AgentBadge component: inline badges on chat messages showing handler
  - Agent types: planner, browser, coder, system, executor (color-coded with icons)
  - Tier fallback: fast (green), brain (cyan), deep (gold) when no agent type specified
  - Integrated into ChatView and DashboardView message lists
- Updated types.ts: ProactiveSuggestion, PlanState, PlanSubtask, PlanEventType interfaces
- Updated useJarvisWebSocket: handles proactive_suggestion and plan_progress WS messages
  - Plan state machine: plan_created, subtask_started/completed/failed/skipped, plan_completed
  - Suggestion queue with max 10 items, dismiss callback
- New CSS animations: draw-check (checkmark stroke), toast-progress (countdown bar)
- Files created: ProactiveToast.tsx, PlanProgress.tsx, AgentBadge.tsx
- Files modified: types.ts, useJarvisWebSocket.ts, page.tsx, ChatView.tsx, DashboardView.tsx, globals.css

**Phase 6.4b: Cinematic Particle Orb + Bug Fixes (complete):**
- Three-tier particle orb redesign with depth layering:
  - Core (800 particles, r=0.12-0.22): bright pinpoints clustered at nucleus
  - Mid-layer (1200 particles, r=0.30-0.50): main visible orbiting body
  - Outer (400 particles, r=0.55-0.85): sparse, dimmer, independently drifting
- Refined color system: cyan base with warm amber accents for speaking (not full gold takeover)
  - Speaking state: warm white-gold nucleus, particles stay cyan with subtle warm shift
  - Thinking: brighter cyan with white core
  - Idle: calm breathing pulse (0.45Hz), mostly smooth with faint heartbeat
  - Listening: inward compression (scale 0.93), cooler tighter cyan
- Shell-specific orbital speeds: core shimmers slowly, mid orbits normally, outer drifts independently
- Nucleus glow: layered billboard quads (1.1 and 1.8 units) with intensity multipliers 0.75/0.35
- Fragment shader: 2.2x color multiplier, tight exponential falloffs for crisp dot rendering
- Bug fix: orb now persists across tab switches (CSS display toggle instead of React unmount)
- Bug fix: fact extraction filter rejects casual speech ("not looking at it for" no longer stored as nickname)
- Bug fix: follow-up silence detection requires 150+ amplitude spike + 3 sustained frames
- New weather tool: Open-Meteo API integration (free, no key), geocoding, speech-friendly output
- Transcription hints: faster-whisper now receives location-based initial_prompt and hotwords from user profile
- Files created: jarvis/tools/weather.py
- Files modified: ArcReactorGL.tsx, CinematicView.tsx, page.tsx, listener.py, coordinator.py, tools_schema.py, settings.py, profile.py, profile.json

**Phase 6.5: Multi-Device Audio Routing Refinements (complete):**
- Client registration protocol: each WebSocket client sends device type (phone/tablet/desktop), name, and audio preferences on connect
- ClientInfo metadata class tracks device_type, device_name, wants_audio, connected_at, last_activity per client
- Per-device audio preferences: clients can toggle wants_audio on/off via WebSocket; server routes audio only to opt-in clients
- Smart audio routing: terminal-originated voice sends WAV/Opus only to clients with wants_audio=true, animation to all others
- Audio interruption: any client (or REST endpoint POST /audio/stop) can stop TTS on all devices instantly
  - Kills local afplay/say processes, broadcasts voice_stop to all browser clients
  - Browser immediately pauses playback, cancels envelope animation
- Connected devices endpoint: GET /devices returns all connected clients with device info and activity timestamps
- Chunked TTS streaming for Kokoro backend: audio is sent in ~0.8s chunks as generated, not after full response
  - Uses asyncio.Queue bridging Kokoro generator thread to async event loop
  - Browser queues chunks and plays them sequentially for seamless playback
  - First audio chunk arrives within ~1s of speech start (was 3-8s for full generation)
  - voice_audio_chunk WebSocket message with index, is_last, envelope, duration, format fields
- Opus audio compression: TTS_BROWSER_FORMAT=opus (default) encodes audio as Opus/WebM via ffmpeg
  - ~10x smaller payloads (5s WAV ~240KB -> Opus ~24KB)
  - Reduces WebSocket bandwidth, faster delivery especially over Cloudflare tunnel
  - Graceful fallback to WAV if ffmpeg Opus encoding fails
  - audio_format field in all audio payloads so browser uses correct MIME type for Blob
- Device detection: browser auto-detects iPhone/iPad/Android/Desktop from user agent
- Files modified: server.py, speaker.py, main.py, settings.py, useJarvisWebSocket.ts, types.ts

---

## 5. What Has Been Completed

### Browser Automation Foundation

**File:** `jarvis/tools/browser_agent.py`

- Playwright launches Chromium with a persistent profile at `data/browser-profile/`
- All sessions, cookies, and login state persist between JARVIS restarts
- Claude Computer Use API (beta `computer-use-2025-11-24`) with tool type `computer_20251124`
- Model: `claude-sonnet-4-6`
- Viewport: 1024x768, JPEG screenshots at 75% quality
- Max 30 steps per task with safety cutoff
- Downloads go to `~/Downloads/JARVIS/`
- Fixed: `execute_action()` duplicate argument bug (filtered `action` key from `tool_input` dict)

### Mobile Access via Cloudflare Tunnel

**File:** `start.sh`

- Detects `cloudflared` CLI and starts a Quick Tunnel after UI boots
- Tunnel points to `http://localhost:3000` (Next.js UI)
- Tunnel URL printed in a banner box on the console
- URL format: `https://<random>.trycloudflare.com`
- No Cloudflare account required for Quick Tunnel

**File:** `jarvis/ui/jarvis-ui/next.config.js`

- Two rewrite rules proxy traffic through the single tunnel URL:
  - `/jarvis-api/:path*` -> `http://127.0.0.1:8741/:path*` (REST API)
  - `/jarvis-ws` -> `http://127.0.0.1:8741/ws` (WebSocket)

**Files:** `useJarvisWebSocket.ts`, `useServerStatus.ts`, `useVoiceRecorder.ts`

- All three hooks have `isTunnelMode()` / `getApiBaseUrl()` functions
- Detection: if `window.location.port` is empty, 80, or 443, AND hostname is not localhost, then it is tunnel mode
- In tunnel mode, routes go through Next.js rewrites (`/jarvis-api/*`, `/jarvis-ws`)
- In local mode, routes go directly to `localhost:8741`

### TTS Audio Streaming (Server Side)

**File:** `jarvis/voice/speaker.py`

- After Kokoro generates audio, encodes the WAV as base64 using `io.BytesIO()` + `soundfile.write()` + `base64.b64encode()`
- Passes `audio_base64` as third argument to the `on_audio_ready` callback
- Audio still plays locally via `afplay` AND is intended to stream to browser clients

**File:** `jarvis/core/server.py`

- `broadcast_voice_state()` accepts `audio_base64: str | None` parameter
- When `speaking=True` and `audio_base64` is provided, includes `voice_audio` field in WebSocket payload
- The `on_audio_ready` callback in the WebSocket handler passes `audio_b64` through

**File:** `jarvis/ui/jarvis-ui/src/hooks/useJarvisWebSocket.ts`

- `playBase64Audio()` function: decodes base64 string, creates WAV Blob, creates object URL, plays via `new Audio(url)`
- Called in the `voice_speaking` handler when `data.voice_audio` is present

**File:** `jarvis/ui/jarvis-ui/src/lib/types.ts`

- `WSMessage` interface includes `voice_audio?: string` field

---

## 6. Current Difficulties and Unresolved Issues

### Issue 1: Phone Audio Playback - RESOLVED

**Fix:** Dual playback strategy in `useJarvisWebSocket.ts`. Uses a hidden `<audio>` element (primary, more reliable on iOS Safari) with Web Audio API fallback. Silent WAV primer played during user gesture to keep audio "warm." The `unlockAudio()` function is called from the mic button handler in CinematicView.

### Issue 2: Browser Sessions - RESOLVED

**Fix:** Chrome cookie sync via `pycookiecheat`. Auto-imports cookies from Chrome into Playwright on browser init, and per-URL sync before navigation. A `sync_browser_sessions` tool is available for manual refresh. Note: Playwright still runs its own Chromium (not the user's Chrome), but it now has the user's login cookies.

### Issue 3: Browser Page-Closed Recovery - RESOLVED

**Fix:** `_is_page_alive()` check at the top of each step in `_run_computer_use_loop()`. Aborts immediately with a friendly message if the browser window was closed mid-task.

### Issue 4: Device-Targeted Audio - RESOLVED

**Fix:** `broadcast_voice_state()` accepts a `target_ws` parameter. Browser-originated requests pass the requesting WebSocket, so only that client receives the heavy WAV audio payload. Other clients get animation data only. Mac speakers are silenced via `skip_local_playback=True`.

### Issue 5: Feedback Loop (Computer Mic Picks Up Phone Audio) - RESOLVED

**Fix:** `set_speaking()` in `listener.py` accepts `open_followup` parameter. Browser-originated responses pass `open_followup=False`, skipping the follow-up window so the computer mic doesn't pick up JARVIS's voice playing from the phone speaker.

---

## 7. What Remains To Be Done

### Low-Priority Items

1. **Named Cloudflare Tunnel** for a persistent URL. Requires: free Cloudflare account, a domain on Cloudflare DNS, then `cloudflared tunnel create jarvis` for a permanent subdomain.

2. **Whisper model upgrade.** The `small.en` model is fast but struggles with proper nouns. Setting `WHISPER_MODEL=medium.en` in .env gives ~30% better accuracy at the cost of slower transcription. Location hints (initial_prompt) are now enabled by default to help.

3. **Install pycookiecheat** on Mac (`pip install pycookiecheat`) for Playwright fallback cookie sync. Currently disabled since the package is not installed.

### Phase 5: Intelligence Upgrades

- (Complete. All Phase 5 features have been implemented.)

---

## 8. Key Files Reference

### Files You Will Modify Most

| File | Purpose |
|------|---------|
| `jarvis/tools/browser_agent.py` | Browser automation, Computer Use loop |
| `jarvis/voice/speaker.py` | TTS engine, audio encoding |
| `jarvis/core/server.py` | WebSocket handler, voice state broadcast, proactive delivery |
| `jarvis/core/proactive.py` | Proactive suggestions engine (heartbeat, context checks) |
| `jarvis/agent/coordinator.py` | Multi-agent coordinator (routing, parallel execution) |
| `jarvis/core/hardening.py` | Error handling, retry, timeouts, circuit breakers |
| `jarvis/core/cache.py` | TTL-based tool result caching with LRU eviction |
| `jarvis/core/perf.py` | Latency profiling, bottleneck detection, tier tracking |
| `jarvis/memory/facts.py` | Fact extraction engine with pattern matching |
| `jarvis/memory/preferences.py` | Implicit preference learning from behavior |
| `jarvis/ui/jarvis-ui/src/hooks/useJarvisWebSocket.ts` | WS client, audio playback, suggestions, plan state |
| `jarvis/ui/jarvis-ui/src/hooks/useVoiceRecorder.ts` | Browser mic input |
| `jarvis/ui/jarvis-ui/src/lib/types.ts` | Shared TypeScript types (includes plan/suggestion types) |
| `jarvis/ui/jarvis-ui/src/components/shared/ProactiveToast.tsx` | Proactive suggestion toast notifications |
| `jarvis/ui/jarvis-ui/src/components/shared/PlanProgress.tsx` | Plan execution progress overlay |
| `jarvis/ui/jarvis-ui/src/components/shared/AgentBadge.tsx` | Agent/tier badges for chat messages |
| `jarvis/tools/weather.py` | Dedicated weather API tool (Open-Meteo, no key needed) |
| `jarvis/ui/jarvis-ui/src/components/cinematic/ArcReactorGL.tsx` | Three-tier particle orb (Three.js + GLSL) |
| `jarvis/ui/jarvis-ui/src/components/cinematic/CinematicView.tsx` | Voice view wrapper (boot sequence, mic, transcript) |
| `start.sh` | Startup orchestration |

### Configuration Files

| File | Purpose |
|------|---------|
| `.env` | API keys, model settings, ports |
| `.env.example` | Template for .env |
| `jarvis/config/settings.py` | Python settings loader |
| `jarvis/ui/jarvis-ui/next.config.js` | Next.js rewrites for tunnel |

### Planning Documents

| File | Purpose |
|------|---------|
| `Project_JARVIS_Plan.docx` | Original project plan |
| `Project_JARVIS_Final_Plan.docx` | Finalized plan |
| `Project_JARVIS_Upgrade_Plan.docx` | Upgrade roadmap |
| `Project_JARVIS_Budget_Plan.docx` | Cost and budget planning |
| `RESEARCH_JARVIS_INSPIRATION.md` | Competitive analysis of 20+ projects |

---

## 9. Environment Setup

### Prerequisites

- macOS with Apple Silicon (M1/M2/M3)
- Python 3.11+
- Node.js 18+
- Homebrew
- Ollama (local LLM fallback)
- PortAudio (for microphone input)
- ffmpeg (for audio format conversion)
- cloudflared (optional, for mobile access)

### Installation

```bash
# Clone the project
cd Jarvis

# Run setup (installs Python venv, dependencies, Playwright Chromium)
./setup.sh

# Copy env template and add your API key
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY

# Install cloudflared for mobile access (optional)
brew install cloudflared
```

### Key Environment Variables

```bash
ANTHROPIC_API_KEY=sk-ant-...          # Required
CLAUDE_BRAIN_MODEL=claude-sonnet-4-6  # Default reasoning model
CLAUDE_FAST_MODEL=claude-haiku-4-5    # Quick tasks
CLAUDE_DEEP_MODEL=claude-opus-4-6     # Deep analysis
TTS_ENGINE=kokoro                     # Best local TTS
TTS_VOICE=af_heart                    # Kokoro voice
WHISPER_MODEL=base.en                 # STT model size
```

---

## 10. How to Run

```bash
# Full mode (recommended): voice + API server + UI + tunnel
./start.sh full

# Or just specific modes:
./start.sh text     # Terminal text chat only
./start.sh voice    # Voice interaction only (no UI)
./start.sh server   # API server + UI only (no terminal voice)
```

**What `./start.sh full` does:**

1. Activates Python virtual environment
2. Checks/installs python-multipart and Playwright
3. Creates browser profile directory
4. Starts Ollama if not running
5. Starts Next.js UI on port 3000
6. Starts Cloudflare Tunnel (if cloudflared installed)
7. Starts JARVIS Python backend (FastAPI on port 8741 + voice listener)

**Access points after startup:**

- Local UI: `http://localhost:3000`
- Mobile UI: The `https://<random>.trycloudflare.com` URL shown in the console
- API: `http://localhost:8741`
- Health check: `http://localhost:8741/health`

---

## 11. Technical Decisions and Tradeoffs

### Why Playwright instead of Chrome CDP

Chrome 115+ blocks `--remote-debugging-port` on the default profile directory on macOS. Four different workarounds were attempted (direct binary, symlink, open -a, user-data-dir), all failed. Playwright was chosen because it supports persistent contexts with reliable session preservation, at the cost of running a separate Chromium instance.

### Why Cloudflare Quick Tunnel instead of Tailscale

User preference for a free solution with no additional software installation on the phone. Cloudflare Quick Tunnel gives a random HTTPS URL instantly with no account. Downside: URL changes on every restart (Named Tunnel with a domain fixes this).

### Why base64 WAV over WebSocket instead of a streaming audio endpoint

Simplicity: the WAV is already generated by Kokoro, encoding to base64 is one line, and it rides the existing WebSocket connection. Downside: large payloads for longer responses. A dedicated `/voice/stream` HTTP endpoint with chunked transfer encoding would be more efficient for long audio.

### Why Next.js rewrites instead of a reverse proxy

Avoids adding nginx or another process. The Next.js dev server already handles WebSocket proxying through rewrites. In production, a proper reverse proxy (nginx, Caddy) would be more appropriate.

---

## 12. Known Bugs and Workarounds

### Bug: `execute_action() got multiple values for argument 'action'`

**Status:** FIXED

Claude Computer Use returns `tool_input = {"action": "left_click", "coordinate": [100, 200]}`. Unpacking `**tool_input` into `execute_action(action, **tool_input)` passes `action` twice. Fixed by filtering:

```python
action_params = {k: v for k, v in tool_input.items() if k != "action"}
await self.execute_action(action, **action_params)
```

### Bug: Cascading "page closed" errors in Computer Use loop

**Status:** FIXED

Added `_is_page_alive()` check at the top of each step in the Computer Use loop. Now aborts immediately with a summary of completed actions.

### Bug: Cross-origin warning in Next.js

**Status:** COSMETIC (not blocking)

```
Cross origin request detected from *.trycloudflare.com to /_next/* resource
```

Fix by adding `allowedDevOrigins` to `next.config.js`:

```javascript
const nextConfig = {
  allowedDevOrigins: ["*.trycloudflare.com"],
  // ... existing config
};
```

### Bug: Edge TTS and macOS `say` don't stream audio to browser

**Status:** FIXED

All three TTS backends (Kokoro, Edge TTS, macOS say) now generate base64 WAV audio, compute amplitude envelopes, and fire the `on_audio_ready` callback for browser streaming. Edge TTS and macOS say convert their output to 24kHz mono WAV via ffmpeg before encoding.

### Quirk: Ollama auto-start

`start.sh` starts Ollama in the background if it is not running. If Ollama is already running, it skips this step. Ollama is only used as a fallback when Claude API is unreachable.

---

*This handoff document was last updated on March 25, 2026. Phases 1-5 are complete. Phase 6 (Polish & Production Readiness) is complete: hardening, performance tuning, persistent memory, UI enhancements, cinematic orb, bug fixes, and multi-device audio routing all done. JARVIS has 86 tools across 9+ categories, multi-agent coordination, circuit breakers, retry with backoff, TTL-based result caching, latency profiling, cost-aware tier routing, fact extraction, implicit preference learning, proactive suggestion toasts, plan execution animations, agent badges, chunked TTS streaming, Opus audio compression, per-device audio preferences, audio interruption, and production-grade error handling.*
