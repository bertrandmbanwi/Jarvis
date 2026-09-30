# JARVIS Roadmap (2026-Q4)

Source: the 2026-09-29 deep-dive review plus research on OpenAI DevDay 2026, Anthropic's releases and ecosystem trends.
Main direction: **move the LLM backend from Anthropic to OpenAI** (Responses API), keep Ollama as the offline fallback, fix the security and reliability defects the review found, and ship the ecosystem features (MCP, Skills, messaging, realtime voice) that drive adoption.

Each phase ships as its own PR with green CI. A phase is "done" only when its verification checks pass.

**Decisions (2026-09-29):**
- OpenAI is the default provider. Anthropic stays as an optional provider behind the same interface.
- The `deep` tier uses `gpt-6.1-sol` at high reasoning effort (not Astra).
- Coding delegation supports both Codex CLI and Claude Code CLI; the user picks one.
- One PR per phase, stacked on the previous one. The owner reviews once CI is green.

---

## Model plan (verified against developers.openai.com, 2026-09-29)

| JARVIS tier | Model | Reasoning effort | Price per 1M tokens (in / cached / out) | Used for |
|---|---|---|---|---|
| `fast` | `gpt-6-luna` | low | $0.10 / $0.01 / $0.50 | Quick answers, routing, complexity checks, QA verdicts, memory summarisation |
| `brain` | `gpt-6.1-sol` | medium | $2.00 / $0.10 / $10.00 | Conversation, tool use, planning |
| `deep` | `gpt-6.1-sol` | high (optionally `gpt-6-astra`) | same (Astra $10 / $50) | Multi-step plans, hard reasoning |
| voice (cloud mode) | `gpt-live-1` | – | $0.05 / min + backend usage | Full-duplex voice with delegation to JARVIS tools |
| STT (cloud fallback) | `gpt-live-transcribe` / `gpt-transcribe` | – | – | When local Moonshine/Whisper accuracy falls short |
| computer use | `gpt-6.1-sol` + Responses computer-use tool | – | – | Browser agent (replaces Anthropic `computer_20251124`) |
| offline | Ollama (`gpt-oss:20b` / `llama3.1:8b`) | – | free | Fallback when there is no network or budget |

Notes:
- `gpt-6-astra` has no custom `temperature`/`top_p` and requires the Responses API for tools. The whole integration therefore targets the **Responses API**, not Chat Completions.
- OpenAI's `usage.input_tokens` **includes** cached tokens (`input_tokens_details.cached_tokens`). The cost tracker must use this rule, not Anthropic's.

---

## Phase 0 — Security and correctness (ship first)

| # | Item | Verify |
|---|---|---|
| 0.1 | **WebSocket origin check.** Allow-list `Origin` on `/ws` and `/ws/extension` (UI origins, tunnel domain, `chrome-extension://`). Add a per-launch shared token for the extension socket. A loopback address alone never grants trust. | Tests: foreign origin rejected; UI origin, extension and origin-less native client accepted |
| 0.2 | Reject cross-site `no-cors` POSTs to the loopback API (covered by the HTTP origin guard from 0.1) | Test |
| 0.3 | Add an MIT `LICENSE` file (the README already claims MIT) | File present; GitHub detects it |
| 0.4 | ~~Sticky Ollama fallback~~ → moved to 1.13 (the provider rewrite replaces this code) | – |
| 0.5 | ~~Retry multiplication~~ → moved to 1.13 | – |
| 0.6 | QA retry must never re-run side-effect tools. Retry only when QA returned a real `passed=false` verdict, never on a timeout or parse error | Test |
| 0.7 | Clear `_last_plan` per request. Keep per-request state in a request context object instead of on the shared `Brain` | Test with concurrent requests |
| 0.8 | Subtask retry actually fires; a failed subtask is marked FAILED, not COMPLETED | Test |
| 0.9 | Local router: the bare word "incorrect" no longer swallows real requests. Planner complexity check uses a structured verdict | Tests |
| 0.10 | Voice I/O off the event loop: `stream.read()` and transcription run in `asyncio.to_thread` | Test / manual |
| 0.11 | `stop_speaking` kills only JARVIS's own playback process, not every `afplay` on the system | Test |
| 0.12 | `setup.sh` installs `requirements.txt`; `start.sh` kills only JARVIS processes | Manual |
| 0.13 | Privacy mode stops writing prompt previews to cost logs and audit logs | Test |
| 0.14 | ~~Career-Atlas `watch: started` trigger~~ kept: it deliberately refreshes the owner's portfolio on new stars and reads only public data | – |

## Phase 1 — Move the LLM backend to OpenAI

**Status:** shipped in the Phase 1 PR, except where a row says deferred. Every OpenAI path is tested against a mocked Responses client; there has been no live call yet (no API key in the dev environment).

| # | Item | Verify |
|---|---|---|
| 1.1 | `openai` SDK dependency; `OPENAI_API_KEY` stored in the Keychain; settings UI and API accept it | Settings tests |
| 1.2 | Provider layer (`jarvis/core/providers/`): `OpenAIProvider` (Responses API) and `OllamaProvider`, behind one interface covering chat, stream, tool loop, structured output and vision. `llm.py` keeps its public API so callers don't change | Existing LLM tests ported and passing |
| 1.3 | Tool loop on Responses `function` tools, parallel tool calls run with `asyncio.gather`, errors returned as tool output. Follow-up (shipped): token streaming during tool use for the chat UI, and opt-in strict tool schemas (`OPENAI_STRICT_TOOLS`) | Tests with a mocked Responses client |
| 1.4 | Structured outputs (`text.format: json_schema, strict`) for the planner, QA verdict, complexity check and decomposition, replacing regex and fence parsing | Planner, QA and coordinator tests |
| 1.5 | Prompt caching: stable prefix (static instructions + deterministic tool list); per-turn context goes after the cached prefix. `prompt_cache_key` is not needed: OpenAI routes caches automatically on GPT-5.6+ | Cache read/write tokens tracked per call |
| 1.6 | Tool selection: history-aware selection with word-boundary matching; a deterministic tool order keeps the cache valid (use hosted tool search if the Responses API offers it) | Tests: "yes, send it" after a draft offers `send_email` |
| 1.7 | Cost tracker: OpenAI pricing table and OpenAI usage rules; budget limits enforced; blocking file reads moved off the loop | Cost-tracker tests |
| 1.8 | Vision (`screen.py`) and browser agent on the OpenAI computer-use tool; keep only the last N screenshots, as JPEG | Tests with mocked client |
| 1.9 | Batch API endpoints (`/batches`) on the active provider. Follow-up (shipped): `BATCH_FOR_BACKGROUND=true` runs scheduled workflow prompts through Batch (half price, no tools) | Test |
| 1.10 | Coding delegation: `codex exec` (OpenAI Codex CLI) alongside Claude Code CLI; the user picks one | Tool contract test |
| 1.11 | Settings take effect without a restart (model and key changes rebuild the client) | Test |
| 1.12 | Docs, README, `.env.example`, evals and CI switched to OpenAI | CI green |
| 1.13 | Provider fallback is temporary (cloud re-probed after a cooldown, never switched permanently); SDK `max_retries=0` under the custom retry layer; circuit breaker checked on every call path | Tests |

## Phase 2 — Architecture cleanup

**Status:** shipped in the Phase 2 PR.

| # | Item | Verify |
|---|---|---|
| 2.1 | Split `server.py` (2,781 → 1,757 lines): security helpers, runtime state, API models, job runners, and workflow/calendar `APIRouter`s moved out | Route table identical before/after; every route rejects unauthenticated remote clients (test) |
| 2.2 | Merge `process` and `process_stream` into one pipeline with a streaming sink | Tests |
| 2.3 | Removed the A/B testing, template evolution and evolution pipeline code (~1.1k lines that recorded rows but changed nothing); README only claims what works | Tests; README |
| 2.4 | Memory: one write per exchange, exact-repeat dedupe, UUID ids, and recall for agent requests (not just chat); recalled text is wrapped and marked as data, not instructions | Memory tests |
| 2.5 | Tool-schema drift check: every schema has an implementation and vice versa; cache and selector lists validated | Contract test in CI |
| 2.6 | CI installs a pinned, hashed `requirements-ci.lock` (compiled with `uv`) | Suite passes on the locked set |

## Phase 3 — Voice

**Status:** shipped in the Phase 3 PR. GPT-Live and cloud STT are tested against mocked OpenAI endpoints only; they need a live check with an OpenAI key.

| # | Item | Verify |
|---|---|---|
| 3.1 | Silero VAD instead of the amplitude threshold; `vad_filter` for faster-whisper | Unit tests on sample audio |
| 3.2 | Barge-in: stop playback when the user talks over JARVIS. Opt-in (`BARGE_IN_ENABLED`) because the local mic has no echo cancellation; native in the GPT-Live mode | Unit test; manual with headphones |
| 3.3 | Local Kokoro chunk playback as chunks arrive (streamed locally, not only to the browser) | Manual |
| 3.4 | **Cloud voice mode on `gpt-live-1`** ("Live" button): browser mic → JARVIS server → GPT-Live; delegations run through the brain (tools, memory, approval prompts). The key stays on the server | Tests with a mocked Live socket; manual with key |
| 3.5 | Opt-in cloud STT fallback (`gpt-transcribe`) when local transcription is unavailable or empty | Test |

## Phase 4 — Ecosystem (the star drivers)

**Status:** 4.1–4.5 shipped in the Phase 4 PR. 4.6 is deferred: the Decisions API is in limited preview with no public reference yet.

| # | Item | Verify |
|---|---|---|
| 4.1 | **MCP client**: stdio and streamable-HTTP servers from `~/.jarvis/mcp.json`; their tools join the registry under the permission catalog (unknown tools default to confirm-required) | Test against a stub MCP server |
| 4.2 | **JARVIS as an MCP server**: `jarvis mcp serve` exposes selected tools, with the same permission gate | MCP inspector / client test |
| 4.3 | **Agent Skills**: load `SKILL.md` folders from `~/.jarvis/skills` and the repo `skills/`; progressive disclosure into the prompt | Tests |
| 4.4 | **Telegram channel**: bot bridge to the brain with a user allow-list, confirmations through inline buttons | Tests with mocked Bot API |
| 4.5 | **Proactive routines**: morning briefing (calendar, email, weather, news) and scheduled check-ins on the existing scheduler | Tests |
| 4.6 | *Deferred:* Decisions API intent router, once the API is out of preview and documented | – |

## Phase 5 — Offline and Apple

**Status:** shipped in the Phase 5 PR, and verified on this Mac against a running Ollama (llama3.1:8b tool call) and Apple's on-device model (replies, streaming).

| # | Item | Verify |
|---|---|---|
| 5.1 | `OFFLINE_MODE`: a local provider with tool calling over any OpenAI-compatible server (Ollama, MLX, LM Studio); no cloud model calls; Live voice and cloud STT off; Codex runs with `--oss` | Unit tests + live Ollama tool call |
| 5.2 | Apple Foundation Model (macOS 26+) for fast-tier replies via a Swift helper built on first use; structured decisions stay on the local server model (the on-device model misclassified simple requests in testing) | Live test on macOS 27 |

## Phase 6 — Frontend and infrastructure

**Status:** shipped in the Phase 6 PR. The UI has no unit-test runner; these changes are covered by type checks, lint, build and the Playwright smoke test.

| # | Item | Verify |
|---|---|---|
| 6.1 | Fix the WebSocket reconnect race (StrictMode, token change, CONNECTING guard, backoff with jitter, retry on online/visibilitychange) | Unit tests |
| 6.2 | Confirmation prompts restored when the approval request fails; messages queued while disconnected | Tests |
| 6.3 | React 19 and matching types, eslint 9 flat config, dev dependencies moved to `devDependencies` | `npm run build` + lint |
| 6.4 | Split `ProductView.tsx` (2,303 → 1,388 lines) into types, defaults, formatters, parts and builder-field modules. Every icon-only button already has an aria-label (the other buttons have visible text). *Next:* break the main component body into section components | Build + Playwright smoke |
| 6.5 | CI on Node 24 LTS and current action versions (v7) | CI |

## Phase 7 — Growth and release

**Status:** everything that can be done in the repository is in the community-files PR and the launch PR. Posting, repository settings, signing and recording are steps for the owner, listed in `docs/launch/LAUNCH_KIT.md`.

| # | Item | Needs owner |
|---|---|---|
| 7.1 | README hero rewrite around one hook, a comparison table and quick start | – |
| 7.2 | CONTRIBUTING, CODE_OF_CONDUCT, issue and PR templates, SECURITY.md | – |
| 7.3 | 5–10 "good first issue" drafts | Owner files them |
| 7.4 | Demo GIF of the boot sequence and live orb (recorded from the real UI) at the top of the README; social preview image | Owner records the voice demo video |
| 7.5 | v1.0.0 release: changelog, DMG from `scripts/package_macos_app.sh` | Owner signs and publishes |
| 7.6 | Repo metadata: description (fix 104 vs 109 tools), topics (`mcp`, `openai`, `local-llm`, `ai-agent`), Discussions, social preview | Owner approves |
| 7.7 | Launch kit: Show HN, r/LocalLLaMA, r/macapps and Product Hunt drafts; PRs to awesome-lists | Owner posts |

---

## What needs the owner
- An **OpenAI API key** (in the Keychain or `.env`) for live end-to-end tests. Until then, every OpenAI path is verified with a mocked client.
- Any outward-facing step: pushing branches and opening PRs, repo settings, releases, posts.
- Recording the voice demo and signing the DMG.
