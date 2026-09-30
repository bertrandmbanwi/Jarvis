# Launch kit

Drafts for the v1.0.0 launch. Everything here needs the owner to post or run; nothing is published automatically.

## 1. Repository settings (run once)

```bash
gh repo edit bertrandmbanwi/Jarvis \
  --description "The open-source JARVIS for your Mac: voice, 106 tools, MCP, Agent Skills, Telegram. OpenAI, Claude, or fully offline (Ollama + Apple on-device)." \
  --homepage "https://github.com/bertrandmbanwi/Jarvis#readme" \
  --enable-discussions \
  --add-topic mcp --add-topic openai --add-topic ai-agent --add-topic local-llm \
  --add-topic voice-assistant --add-topic macos --add-topic ollama --add-topic agent-skills
```

In the browser:
- **Settings → General → Social preview:** upload `docs/screenshots/social-preview.png`.
- **Settings → Code security:** enable **private vulnerability reporting** (SECURITY.md links to it).
- File the six issues in `docs/good-first-issues.md` with the `good first issue` label.

## 2. Release

```bash
bash scripts/package_macos_app.sh            # builds the .app and DMG
git tag -a v1.0.0 -m "JARVIS v1.0.0" && git push origin v1.0.0
gh release create v1.0.0 dist/*.dmg --title "JARVIS v1.0.0" --notes-file CHANGELOG.md
```

The DMG isn't notarized unless you sign it with your Developer ID. Without notarization, macOS asks users to right-click and choose Open on first launch; mention that in the release notes.

## 3. Demo video (the biggest single lever)

A 60–90 second screen recording with voice:
1. "Hey JARVIS, what's my day look like?" (morning-briefing skill: calendar, weather, email)
2. "Open the Next.js docs and find the caching section" (browser control)
3. A risky action ("send Sam an email saying I'm running late") showing the approval prompt
4. Turn Wi-Fi off, set `OFFLINE_MODE=true`, and ask again (local models plus Apple on-device)
5. Press **Live** and have a back-and-forth, interrupting mid-sentence

Upload it to YouTube and link it under the GIF in the README.

## 4. Posts

### Show HN

**Title:** Show HN: JARVIS – an open-source voice assistant that runs your Mac (offline capable)

> I built JARVIS, an Iron Man-style assistant that lives on macOS. You talk to it ("Hey JARVIS"), and it acts through 106 tools: apps, files, Chrome, email, calendar, notes, the shell, and a browser agent with computer use. Anything risky waits for your approval.
>
> Things that might interest HN:
> - It runs on OpenAI or Claude, or **fully offline**: tool calling on Ollama/MLX, with quick replies on Apple's on-device Foundation Model through a small Swift helper.
> - **MCP both ways:** it can use any MCP server, and `python -m jarvis.mcp_server` exposes its tools to Claude Code or Cursor.
> - Agent Skills (`SKILL.md`), Telegram with approval buttons, and scheduled routines.
> - A "Live" mode on OpenAI GPT-Live for full-duplex voice, while the actual work runs through JARVIS's own tools and permission gate.
>
> Python/FastAPI, Next.js + Three.js for the UI, Swift for the overlay. MIT licensed. I'd love feedback on the permission model and the offline setup.

### r/LocalLLaMA

**Title:** Fully offline JARVIS for macOS: tool calling on Ollama/MLX and Apple's on-device model for quick replies

> Open-source voice assistant with an `OFFLINE_MODE` that makes no cloud model calls: 106 tools with function calling through any OpenAI-compatible local server (Ollama, `mlx_lm.server`, LM Studio), plus Apple's Foundation Model (macOS 26+) for quick replies. Local STT (Moonshine/Whisper with Silero VAD) and TTS (Kokoro). Tested with llama3.1:8b; qwen3 and gpt-oss:20b are recommended for tool use. Feedback on model picks welcome.

### r/macapps

**Title:** JARVIS: an open-source, voice-controlled assistant for macOS (free, MIT)

> A floating arc-reactor overlay, "Hey JARVIS" wake word, and control of apps, files, Chrome, Notes, Calendar and Mail. It can run on your own API key or fully offline. There's a DMG in the release.

### X / Threads

> I built an open-source JARVIS for the Mac. 🎙️ Voice, 106 tools, MCP both ways, Agent Skills, Telegram. OpenAI, Claude, or fully offline with Ollama + Apple's on-device model. Risky actions wait for your OK. MIT. github.com/bertrandmbanwi/Jarvis [attach the demo GIF]

### Product Hunt

- **Tagline:** The open-source JARVIS for your Mac
- **Description:** Talk to your Mac and it acts: apps, files, browser, email, calendar, code. Runs on OpenAI or Claude, or fully offline. MCP, Agent Skills, and Telegram built in.

## 5. Curated lists (open a PR to each)

| List | Section | One-liner |
|------|---------|-----------|
| punkpeye/awesome-mcp-servers | Aggregators / OS automation | JARVIS: macOS assistant exposing public-data, and opt-in local, tools over MCP |
| awesome-selfhosted/awesome-selfhosted | Personal dashboards / assistants | Voice AI assistant for macOS, offline capable |
| janhq/awesome-local-ai | Assistants | Offline voice assistant: Ollama/MLX tools + Apple on-device model |
| serhii-londar/open-source-mac-os-apps | Productivity | Voice-controlled AI assistant with desktop overlay |

Also register the MCP server in the official MCP Registry once v1.0.0 is tagged.

## 6. Cadence
Ship a tagged release every 2–4 weeks with a CHANGELOG entry: each release notifies watchers and resurfaces the repo. Make the next big features (e.g., iMessage, Linux support) separate launch moments.
