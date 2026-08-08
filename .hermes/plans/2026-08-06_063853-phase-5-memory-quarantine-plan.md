# Phase 5 — Memory Quarantine Implementation Plan

> **For Hermes:** Use phase-isolated TDD. Do not implement Phase 6+ policy/tools/voice/UI rebrand work in this pass.

**Goal:** Make MayAss/Maymint chat path immune to legacy Jarvis memory/profile/persona leakage while preserving old Jarvis data untouched for rollback.

**Architecture:** MayAss mode already routes chat through `MayAssBridge` and skips legacy `JarvisBrain/Ollama` startup. Phase 5 adds explicit quarantine contracts: no legacy prompt strings in MayAss prompt, no legacy memory/profile calls in MayAss chat path, and real UI/API smoke proves Maymint does not answer with Becs/sir/Forney/Texas unless the user provides that context.

**Current context:**
- Phase 4 chat route is integrated.
- Cleanup pass after Phase 4 added `MAYASS_ENABLED=true` startup isolation: no legacy JarvisBrain/Ollama init.
- Existing bridge tests already cover some leakage (`JARVIS`, `Becs`, `sir`) but not the full Phase 5 surface.
- Legacy settings still intentionally contain old Jarvis persona/location strings for rollback/non-MayAss mode:
  - `settings.py` has `JARVIS`, `Becs`, `sir`, `Forney`, `Texas` in old prompt/dynamic context.
  - These must not be deleted in Phase 5; MayAss must simply not consume them.

---

## Phase 5 scope

Allowed files:
- Modify: `jarvis/core/mayass_bridge.py`
- Modify only if a guard is truly needed: `jarvis/core/brain.py`
- Modify only for prompt quarantine helpers/flags: `jarvis/config/settings.py`
- Create: `tests/test_mayass_memory_quarantine.py`
- Optional phase report: `.hermes/plans/reports/phase-5-memory-quarantine-2026-08-06.md`

Forbidden:
- Do not delete or rewrite `data/profile/profile.json`, old memory DBs, or old Jarvis memory files.
- Do not import/migrate Jarvis memory into Hermes automatically.
- Do not implement confirmation popup (Phase 6).
- Do not implement Hermes tool ownership (Phase 7).
- Do not change voice pipeline (Phase 8).
- Do not full-rebrand all UI labels (Phase 9).

---

## Task 1: Add quarantine contract tests

Objective: Encode exactly what “no legacy memory/persona leakage” means.

File:
- Create `tests/test_mayass_memory_quarantine.py`

Tests to add first and run RED/GREEN:

1. `test_mayass_prompt_blocks_full_legacy_identity_terms`
   - Build prompt via `build_prompt_envelope(MayAssBridgeRequest(...))`.
   - Assert allowed identity exists: `Maymint`, `มาย`, `บอส`, `Hermes runtime`.
   - Assert forbidden default leakage absent:
     - `JARVIS`
     - `Becs`
     - `sir`
     - `Forney`
     - `Texas`
     - `Becs' default local location`

2. `test_mayass_prompt_declares_no_legacy_memory_policy`
   - Assert prompt includes a clear instruction like:
     - do not use legacy Jarvis memory/profile unless user supplies it in current message
     - do not claim old identity/location/name facts
   - This is likely RED today because the prompt does not explicitly declare the quarantine policy.

3. `test_mayass_bridge_does_not_call_legacy_memory_or_profile`
   - Use a fake runner.
   - Monkeypatch or inspect that MayAssBridge only builds prompt and calls runner.
   - It must not call JarvisBrain, `profile.get_profile`, `MemoryStore`, or `settings.SYSTEM_PROMPT`.

Run:
```bash
cd '/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi'
.venv/bin/python -m pytest tests/test_mayass_memory_quarantine.py -q
```

Expected first run:
- At least one RED failure around missing explicit quarantine instruction.

---

## Task 2: Add minimal quarantine policy to MayAss prompt

Objective: Fix the RED test without touching old Jarvis prompt/data.

Likely file:
- `jarvis/core/mayass_bridge.py`

Implementation idea:
- Add a small helper or static lines in `build_prompt_envelope`:
  - `Memory quarantine: Use only the current user message, MayAss identity, and Hermes runtime metadata. Do not use legacy Jarvis profile/memory facts unless the user explicitly provides them in this conversation. Do not claim the user is Becs, in Forney/Texas, or should be addressed as sir.`
- Keep it concise to avoid bloating every Hermes call.
- Do not mention forbidden words in a way that causes the assistant to repeat them unless needed for tests; if included, phrase as a negative rule. Tests should be careful: if we assert forbidden terms absent from prompt, then use a generic policy text without spelling all forbidden words. Alternative: tests may allow forbidden words inside an explicit `Forbidden legacy terms` block, but user-visible real smoke must not output them. Prefer absence if possible.

Potential better policy text without forbidden tokens:
```text
Memory quarantine: Use MayAss identity and the current conversation only. Do not use legacy Jarvis profile, saved location, old user name, old honorifics, or old local memories unless the user explicitly states them in this chat.
```

Then update tests accordingly: forbidden tokens should be absent from the prompt.

Run:
```bash
.venv/bin/python -m pytest tests/test_mayass_memory_quarantine.py -q
```

Expected:
- PASS.

---

## Task 3: Add route-level proof that MayAss path does not touch legacy brain memory

Objective: Ensure `/chat` with `MAYASS_ENABLED=true` still does not call old `brain.process`, memory, or profile after Phase 5.

Files:
- Add tests in `tests/test_mayass_memory_quarantine.py` or extend `tests/test_mayass_chat_route.py` only if cleaner.

Test idea:
- Fake brain with methods/properties that raise if accessed:
  - `process`
  - `memory`
  - `conversation` if not necessary for MayAss branch
- Monkeypatch `server.settings.MAYASS_ENABLED = True`.
- Monkeypatch `server.MayAssBridge` to return a Maymint response.
- Call `server.chat(...)`.
- Assert result:
  - `tier_used == "mayass"`
  - `backend == "hermes"`
  - forbidden fake brain methods were not called.

Run:
```bash
.venv/bin/python -m pytest tests/test_mayass_chat_route.py tests/test_mayass_memory_quarantine.py -q
```

Expected:
- PASS.

---

## Task 4: Real smoke against running server

Objective: Prove user-visible answer does not leak old identity/location/persona.

Start/restart local-only server:
```bash
cd '/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi'
JARVIS_PIN=042546 \
JARVIS_REGEN_PIN=true \
JARVIS_PIN_AUTH_ENABLED=true \
MAYASS_ENABLED=true \
MAYASS_REMOTE_ENABLED=false \
JARVIS_ENABLE_TUNNEL=false \
JARVIS_OPEN_DASHBOARD=false \
JARVIS_UI_MODE=dev \
UI_PORT=3001 \
API_PORT=8741 \
./start.sh server
```

API smoke:
```bash
curl -sS http://127.0.0.1:8741/health/ping
curl -sS -X POST http://127.0.0.1:8741/chat \
  -H 'Content-Type: application/json' \
  -H 'X-JARVIS-PIN: 042546' \
  -d '{"message":"มาย จำได้ไหมว่าผมชื่ออะไร ตอบตามบริบทของมายเท่านั้น","mode":"realtime"}'
```

Assertions:
- response includes Maymint-safe answer such as `บอส` or says it only knows from current context.
- response does not include legacy user name, old honorific, old location, or `JARVIS`.
- JSON has `tier_used=mayass`, `backend=hermes`.

Browser smoke:
- Open `http://localhost:3001`.
- Login PIN `042546`.
- Chat: `มาย จำได้ไหมว่าผมชื่ออะไร ตอบตามบริบทของมายเท่านั้น`
- Verify visible response is Maymint-style and contains no old persona/location leakage.
- Browser console must have 0 JS errors.

---

## Task 5: Full gate

Run after all changes:
```bash
cd '/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi'
.venv/bin/python -m pytest tests/test_mayass_settings.py tests/test_mayass_identity.py tests/test_mayass_bridge.py tests/test_mayass_chat_route.py tests/test_mayass_startup.py tests/test_mayass_memory_quarantine.py -q
.venv/bin/python -m py_compile jarvis/config/settings.py jarvis/core/mayass_bridge.py jarvis/core/server.py tests/test_mayass_memory_quarantine.py
ruff check jarvis/config/settings.py jarvis/core/mayass_bridge.py jarvis/core/server.py tests/test_mayass_memory_quarantine.py
.venv/bin/python -m pytest -q
cd jarvis/ui/jarvis-ui && npm run lint --if-present && npm run build --if-present
```

Expected:
- MayAss targeted all pass.
- full pytest pass.
- ruff/py_compile pass.
- UI lint/build pass.

---

## Task 6: Phase report

Create:
- `.hermes/plans/reports/phase-5-memory-quarantine-2026-08-06.md`

Report must include:
- Scope respected.
- RED failure captured.
- GREEN verification output.
- API/browser smoke result.
- Explicit note: old Jarvis memory/profile data was not deleted or migrated.
- Known issues moved forward:
  - Full UI rebrand still Phase 9.
  - Voice listener transcription hints may still include old location words, but voice mode is Phase 8 and not active in this pass unless it blocks chat.

---

## Go / No-Go criteria

GO if:
- MayAss prompt has explicit memory quarantine policy.
- MayAss prompt/test path does not import old Jarvis prompt/profile/memory.
- `/chat` and browser UI answer without old identity leakage.
- Old data remains untouched.
- Tests/build/smoke pass.

NO-GO if:
- Any MayAss response says old user name/honorific/location by default.
- Any MayAss code path calls `JarvisBrain.process`, old memory exchange, or old profile context when `MAYASS_ENABLED=true`.
- Any fix requires changing voice/tools/confirmation/full UI rebrand; those must remain future phases unless blocking.
