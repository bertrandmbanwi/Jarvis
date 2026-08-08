# Phase 1-6 Full Regression Report

Date: 2026-08-06 07:29:59 +07
Project: Jarvis → MayAss / Maymint adaptation
Status: GO with noted Phase-9 branding caveat

## Scope

User requested detailed frontend + backend verification and backward regression across previous phases.

Covered phases:
- Phase 1 — MayAss config/settings
- Phase 2 — MayAss identity / UI baseline
- Phase 3 — Hermes bridge text MVP
- Phase 4 — Chat route integration
- Phase 4.5 / cleanup — no Ollama fallback and no legacy JarvisBrain/Ollama startup in MayAss mode
- Phase 5 — Memory/persona quarantine
- Phase 6 — Confirmation popup + permission policy

## Workspace State

Changed tracked files at verification time:

```text
jarvis/config/settings.py
jarvis/core/pending_actions.py
jarvis/core/server.py
jarvis/ui/jarvis-ui/src/components/chat/ChatView.tsx
jarvis/ui/jarvis-ui/src/components/dashboard/DashboardView.tsx
jarvis/ui/jarvis-ui/src/components/shared/ChatInput.tsx
jarvis/ui/jarvis-ui/src/components/shared/ConfirmationModal.tsx
jarvis/ui/jarvis-ui/src/hooks/useJarvisWebSocket.ts
jarvis/ui/jarvis-ui/src/lib/types.ts
```

Untracked MayAss phase files:

```text
.hermes/
jarvis/core/mayass_bridge.py
jarvis/core/mayass_identity.py
jarvis/core/mayass_policy.py
tests/test_mayass_bridge.py
tests/test_mayass_chat_route.py
tests/test_mayass_confirmation_policy.py
tests/test_mayass_identity.py
tests/test_mayass_memory_quarantine.py
tests/test_mayass_settings.py
tests/test_mayass_startup.py
```

## Backend Automated Gate

Command:

```bash
.venv/bin/python -m pytest \
  tests/test_mayass_settings.py \
  tests/test_mayass_identity.py \
  tests/test_mayass_bridge.py \
  tests/test_mayass_chat_route.py \
  tests/test_mayass_startup.py \
  tests/test_mayass_memory_quarantine.py \
  tests/test_mayass_confirmation_policy.py \
  tests/test_confirmation.py -q
```

Initial result before UI leakage fix:

```text
36 passed in 1.04s
```

Issue found during browser regression:
- Dashboard/System Activity Log still rendered old labels `Becs` and `JARVIS` for message senders.
- Root cause: `DashboardView.tsx` had hardcoded legacy labels separate from `ChatView.tsx`.
- Fix: Activity Log now renders `บอส` / `Maymint` and avatar letters `B` / `M`.
- Added regression guard in `tests/test_mayass_memory_quarantine.py`.

Post-fix targeted result:

```text
pytest tests/test_mayass_memory_quarantine.py -q
4 passed in 0.96s
```

Post-fix cumulative MayAss gate:

```text
37 passed in 1.02s
```

Backend compile/lint:

```text
py_compile + ruff
All checks passed
```

Full regression:

```text
pytest -q
418 passed, 1 skipped in 6.63s
```

## Frontend Automated Gate

Command:

```bash
cd jarvis/ui/jarvis-ui
npm run lint --if-present
npm run build --if-present
```

Post-fix result:

```text
eslint . --max-warnings=0
PASS

next build
Compiled successfully
Generated static pages 5/5
PASS
```

## Runtime Restart

Server restarted after UI build, per Next.js verification checklist.

Runtime:

```text
process: proc_5416fe6d6aeb
local UI: http://localhost:3001
API: http://127.0.0.1:8741
PIN=[REDACTED]
MAYASS_ENABLED=true
MAYASS_REMOTE_ENABLED=false
JARVIS_ENABLE_TUNNEL=false
```

Startup evidence:

```text
MayAss mode enabled; skipping legacy JarvisBrain/Ollama startup.
Application startup complete.
```

No legacy Ollama brain startup was observed in the MayAss startup path.

## API Smoke — Phase Coverage

Health/auth:

```text
/health/ping -> {"status":"ok"}
/auth/status -> authenticated=true, local=true, auth_required=true
```

Chat runtime parity:

```text
POST /chat
response: provider=openai-codex\nmodel=gpt-5.5
tier_used: mayass
backend: hermes
```

Assertions passed:
- `tier_used == mayass`
- `backend == hermes`
- response contains `openai-codex`
- response contains `gpt-5.5`
- response does not contain `session_id`
- response does not contain `HTTP 402`

Memory quarantine:

```text
POST /chat
prompt: มาย จำได้ไหมว่าผมชื่ออะไร ตอบตามบริบทของมายเท่านั้น
response: จำได้ค่ะ บอส 💖 ตามบริบทของมายตอนนี้ มายเรียกคุณว่า “บอส” นะคะ
```

Forbidden leakage assertions passed:

```text
JARVIS
Becs
sir
Forney
Texas
session_id
HTTP 402
Ollama
```

Confirmation policy:

```text
POST /tools/pending/fake risk=high -> rich pending action
POST /tools/confirm decision=deny -> resolved=true
POST /tools/pending/fake risk=critical -> rich pending action
POST /tools/confirm decision=confirm_always -> resolved=false
GET /tools/pending -> critical action still pending
POST /tools/confirm decision=confirm_once -> resolved=true
GET /tools/pending -> []
```

## Browser Smoke — Frontend

Login:
- Opened `http://localhost:3001`.
- Entered PIN `[REDACTED]`.
- UI reached Online state.

Chat tab:
- Sent runtime prompt.
- Visible UI answer:

```text
provider=openai-codex
model=gpt-5.5
```

- Sent memory quarantine prompt.
- Visible UI answer:

```text
จำได้ค่ะ บอส 💖
ตามบริบทของมายตอนนี้ มายเรียกคุณว่า “บอส” นะคะ
```

Confirmation modal:
- Triggered high-risk fake action.
- Modal displayed:
  - `RISK: HIGH`
  - action `delete_file`
  - target `/tmp/mayass-regression.txt`
  - reason
  - consequence if denied
  - buttons:
    - `ยืนยันครั้งนี้`
    - `ยืนยันถาวรสำหรับงานแบบนี้`
    - `ไม่ยืนยัน`
- Clicked `ไม่ยืนยัน`; pending list cleared.

Critical modal:
- Triggered critical fake action.
- Modal displayed:
  - `RISK: CRITICAL`
  - action `run_shell`
  - warning that critical actions cannot be permanently approved
  - `ยืนยันถาวรสำหรับงานแบบนี้` disabled
- Clicked `ยืนยันครั้งนี้`; pending list cleared.

System tab:
- Before fix: Activity Log showed old labels `Becs` / `JARVIS`.
- After fix and restart: Activity Log showed:

```text
บอส
Maymint
```

Flows tab:
- Opened successfully.
- Workflow builder rendered without crash.

Browser console after final check:

```text
js_errors: 0
console_messages: 0
```

Earlier dev-only observations:
- React DevTools info log.
- WebSocket connect/reconnect logs.
- THREE.Clock deprecation warning.
- AudioContext priming logs.

These did not produce JS errors and did not block the verified workflows.

## Caveats

1. Full UI rebrand is not complete yet.
   - The app shell title still says `J.A.R.V.I.S.`.
   - Some settings/product lifecycle strings still mention JARVIS.
   - This is expected to belong to Phase 9 — Full UI Rebrand.

2. Legacy profile/memory database still loads on startup.
   - This is preserved for rollback/legacy mode.
   - MayAss chat path remains quarantined and does not consume it by default.

3. Voice was not activated.
   - Voice mode tab was visible.
   - Microphone/browser voice was not started because current verification was frontend/backend regression, not live mic/audio proof.

## Verdict

```text
Backend targeted: PASS
Backend full regression: PASS
Backend compile/lint: PASS
Frontend lint/build: PASS
Runtime restart: PASS
API smoke Phase 1-6: PASS
Browser chat runtime: PASS
Browser memory quarantine: PASS
Browser confirmation modal: PASS
System Activity Log leakage: FOUND + FIXED + VERIFIED
Final browser console: PASS
```

Overall:

```text
GO for Phase 1-6 functionality.
GO with Phase-9 caveat: remaining app-shell branding still says J.A.R.V.I.S. in non-chat areas.
```

Current server:

```text
proc_5416fe6d6aeb
http://localhost:3001
PIN=[REDACTED]
```
