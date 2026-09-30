# Changelog

## v1.0.0 (unreleased)

The first tagged release. Compared with the untagged `main` of September 2026:

### Models
- **OpenAI is the default provider** (Responses API): GPT-6 Luna for quick replies and GPT-6.1 Sol for conversation, tools and deep reasoning. Claude stays available (`LLM_PROVIDER=anthropic`).
- **Fully offline mode** (`OFFLINE_MODE=true`): tool calling on Ollama, MLX or LM Studio, quick replies on Apple's on-device Foundation Model, and no cloud model calls.
- Native tool search, structured outputs, prompt caching, and cost tracking that is accurate for both providers.

### Voice
- Silero voice activity detection, streamed local playback, and opt-in barge-in.
- **Live mode:** full-duplex conversation on OpenAI GPT-Live, with JARVIS doing the work behind it.

### Ecosystem
- **MCP both ways:** use tools from any MCP server, or run `python -m jarvis.mcp_server` to use JARVIS from Claude Code, Cursor or Codex.
- **Agent Skills** (`SKILL.md`), with `morning-briefing` and `meeting-prep` included.
- **Telegram channel** with approval buttons, and **scheduled routines**.
- The coding agent runs **Codex CLI** or Claude Code.

### Security and reliability
- Web pages can no longer drive the local API or WebSockets; only JARVIS's own origins are accepted.
- QA retries never repeat side-effect tools; per-request state is isolated; the voice loop no longer blocks the server; a cloud outage falls back temporarily instead of until restart.
- Third-party tool output and memory are labelled as data, not instructions.

### Project
- MIT `LICENSE`, contributing guide, code of conduct, security policy, and issue templates.
- `server.py` split into routers, a single request pipeline, pinned and hashed CI dependencies, React 19, ESLint 9, and Node 24 in CI.
