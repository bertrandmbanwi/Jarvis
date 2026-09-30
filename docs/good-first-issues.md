# Good first issues (drafts)

Small, well-scoped tasks for new contributors. Each one is ready to paste into a GitHub issue with the `good first issue` label.

---

### 1. Read the API port from configuration in the web UI

`jarvis/ui/jarvis-ui/src/lib/apiBase.ts` hard-codes port `8741` in three places, while `next.config.js` already reads `JARVIS_API_PORT`. Anyone who changes `API_PORT` gets a UI that can't reach the server.

**Done when:** the UI uses `NEXT_PUBLIC_JARVIS_API_PORT` (default `8741`) everywhere, and HOW-TO.md mentions it.

---

### 2. Close the SQLite connection when saving a turn fails

`save_turn()` in `jarvis/memory/conversation_store.py` only closes its connection on success. If the insert raises, the connection leaks.

**Done when:** the connection is closed in a `finally` block (or a context manager), with a test that makes the insert fail.

---

### 3. Invalidate the tool cache when a tool returns a list

In `AgentExecutor._execute_tool` (`jarvis/agent/executor.py`), tools that return a list (screenshots, browser state) return early, before `invalidate_on_mutation(tool_name)` runs. A mutating tool with a list result leaves stale cache entries behind.

**Done when:** invalidation runs for every successful call, with a test.

---

### 4. Remove the unused `JARVIS_SYSTEM_PROMPT` constant

`jarvis/config/settings.py` builds `JARVIS_SYSTEM_PROMPT` at import time, freezing the date into it, and nothing reads it (the LLM layer calls `get_system_prompt()` / `get_system_prompt_parts()`).

**Done when:** the constant is gone and `grep -r JARVIS_SYSTEM_PROMPT` finds nothing.

---

### 5. Unit tests for spoken-text normalisation

`jarvis/voice/speaker.py` rewrites text before text-to-speech (the pronunciation map, markdown stripping), but none of it is tested.

**Done when:** `tests/test_speaker_text.py` covers the pronunciation map and the markdown cleanup, with no audio libraries needed.

---

### 6. Document pinning the Chrome extension

`JARVIS_EXTENSION_ID` limits the `/ws/extension` socket to your own install of the extension, but only `.env.example` mentions it.

**Done when:** `docs/CHROME_EXTENSION_ARCHITECTURE.md` explains how to find the extension ID in `chrome://extensions` and set the variable.
