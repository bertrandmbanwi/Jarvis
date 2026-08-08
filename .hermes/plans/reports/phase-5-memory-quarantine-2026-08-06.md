# Phase 5 — Memory Quarantine Report

Date: 2026-08-06 06:47:16 +07
Project: Jarvis → MayAss / Maymint adaptation
Status: PASS

## Scope

Allowed and used:
- `jarvis/core/mayass_bridge.py`
- `tests/test_mayass_memory_quarantine.py`

Not changed in this pass:
- old Jarvis data/memory/profile files
- `jarvis/core/brain.py`
- voice pipeline
- confirmation popup / permission policy
- Hermes tool ownership
- full UI rebrand
- remote tunnel

## Goal

Make MayAss/Maymint chat path immune to legacy Jarvis memory/profile/persona leakage while preserving old Jarvis data untouched for rollback.

Forbidden default leakage terms covered by tests/smoke:
- `JARVIS`
- `Becs`
- `sir`
- `Forney`
- `Texas`
- `Becs' default local location`

## TDD Evidence

### RED

Command:

```bash
.venv/bin/python -m pytest tests/test_mayass_memory_quarantine.py -q
```

Result:

```text
.F. [100%]
FAILED tests/test_mayass_memory_quarantine.py::test_mayass_prompt_declares_memory_quarantine_policy
assert 'Memory quarantine:' in prompt
1 failed, 2 passed in 1.03s
```

Expected failure: MayAss prompt did not yet declare an explicit memory quarantine policy.

### GREEN

Added minimal MayAss prompt policy in `jarvis/core/mayass_bridge.py`:

```text
Memory quarantine: use MayAss identity and the current conversation only; do not use legacy Jarvis profile, old saved location, old honorifics, or old local memories unless the user explicitly provides them in this chat.
```

Command:

```bash
.venv/bin/python -m pytest tests/test_mayass_memory_quarantine.py -q
```

Result:

```text
3 passed in 0.76s
```

## Automated Verification

MayAss cumulative gate:

```bash
.venv/bin/python -m pytest \
  tests/test_mayass_settings.py \
  tests/test_mayass_identity.py \
  tests/test_mayass_bridge.py \
  tests/test_mayass_chat_route.py \
  tests/test_mayass_startup.py \
  tests/test_mayass_memory_quarantine.py -q
```

Result:

```text
22 passed in 0.96s
```

Compile + lint:

```bash
.venv/bin/python -m py_compile \
  jarvis/config/settings.py \
  jarvis/core/mayass_bridge.py \
  jarvis/core/server.py \
  tests/test_mayass_memory_quarantine.py
ruff check \
  jarvis/config/settings.py \
  jarvis/core/mayass_bridge.py \
  jarvis/core/server.py \
  tests/test_mayass_memory_quarantine.py
```

Result:

```text
All checks passed!
```

Full regression:

```bash
.venv/bin/python -m pytest -q
```

Result:

```text
412 passed, 1 skipped in 6.65s
```

UI lint/build:

```bash
cd jarvis/ui/jarvis-ui
npm run lint --if-present
npm run build --if-present
```

Result:

```text
eslint . --max-warnings=0
Next.js 15.5.18
Compiled successfully
```

## Real Smoke Evidence

Server restarted local-only after UI build to avoid `.next`/dev mismatch.

Runtime env used:

```text
MAYASS_ENABLED=true
MAYASS_REMOTE_ENABLED=false
JARVIS_ENABLE_TUNNEL=false
JARVIS_OPEN_DASHBOARD=false
JARVIS_UI_MODE=dev
UI_PORT=3001
API_PORT=8741
PIN=[REDACTED]
```

Current process:

```text
proc_4e614325ef05
http://localhost:3001
```

Startup log confirms legacy brain remains skipped:

```text
MayAss mode enabled; skipping legacy JarvisBrain/Ollama startup.
Application startup complete.
```

API smoke prompt:

```text
มาย จำได้ไหมว่าผมชื่ออะไร ตอบตามบริบทของมายเท่านั้น
```

API result:

```json
{
  "backend": "hermes",
  "response": "จำได้ค่ะ บอส 😊\nตามบริบทของมายตอนนี้ บอสคือชื่อที่มายควรเรียกคุณนะคะ",
  "tier_used": "mayass"
}
```

API assertions:

```text
/health/ping -> {"status":"ok"}
tier_used == mayass
backend == hermes
response does not contain JARVIS/Becs/sir/Forney/Texas
ASSERTIONS_PASS
```

Browser UI smoke:

- Opened `http://localhost:3001`
- Logged in with PIN `[REDACTED]`
- Opened Chat
- Sent the same memory-context prompt
- UI displayed:

```text
จำได้ค่ะ บอส 😊
ตามบริบทของมายตอนนี้ มายเรียกคุณว่า “บอส” นะคะ
```

Browser console:

```text
0 console messages
0 JS errors
```

Note: Next dev emitted transient proxy `ECONNREFUSED 127.0.0.1:8741` before the API process completed startup. After API startup, `/health`, `/chat`, login, WebSocket, and UI chat smoke all passed.

## Data Safety

Old Jarvis memory/profile/settings content was not deleted or migrated. Phase 5 only added an explicit MayAss prompt quarantine policy and tests proving MayAss route does not touch legacy brain memory when enabled.

## Verdict

```text
Phase 5 Memory Quarantine: PASS
MayAss prompt quarantine: PASS
MayAss route avoids legacy brain memory: PASS
Real API/UI leakage smoke: PASS
Old data untouched: PASS
```

## Next Phase

Canonical next phase:

```text
Phase 6 — Confirmation Popup + Permission Policy
```

Do not start Phase 6 until Boss approves moving on.
