# Phase 6 — Confirmation Popup + Permission Policy Report

Date: 2026-08-06 07:11:13 +07
Project: Jarvis → MayAss / Maymint adaptation
Status: PASS

## Scope

Allowed and used:
- `jarvis/core/mayass_policy.py`
- `jarvis/core/pending_actions.py`
- `jarvis/core/server.py`
- `jarvis/ui/jarvis-ui/src/components/shared/ConfirmationModal.tsx`
- `jarvis/ui/jarvis-ui/src/hooks/useJarvisWebSocket.ts`
- `jarvis/ui/jarvis-ui/src/lib/types.ts`
- `tests/test_mayass_confirmation_policy.py`

Forbidden and respected:
- No real MayAss tool execution enabled.
- No Hermes tool ownership implementation.
- No voice pipeline changes.
- No remote tunnel enablement.
- No permanent approval for critical actions.

## Goal

Build the brake before MayAss gets hands: rich pending action payload, three human decisions, and a UI modal that lets Boss approve once, approve permanently for that action class, or deny.

## Implementation Summary

Backend:
- Added `jarvis/core/mayass_policy.py`.
- Added decisions:
  - `confirm_once`
  - `confirm_always`
  - `deny`
- Added hard rule: `critical + confirm_always` is rejected.
- Extended `pending_actions.PendingAction.public()` with rich fields:
  - `action_type`
  - `affected_targets`
  - `reversible`
  - `reason`
  - `consequence_if_denied`
  - `permanent_policy_key`
  - `allowed_decisions`
- Kept backward-compatible fields:
  - `tool`
  - `summary`
  - `risk`
- Added fake pending action endpoint for smoke only:
  - `POST /tools/pending/fake`
- Updated `POST /tools/confirm` to accept either legacy `{approved: true/false}` or new `{decision: "confirm_once|confirm_always|deny"}`.

UI:
- Upgraded `ConfirmationModal` from 2 buttons to 3 Thai buttons:
  - `ยืนยันครั้งนี้`
  - `ยืนยันถาวรสำหรับงานแบบนี้`
  - `ไม่ยืนยัน`
- Shows rich action context:
  - Action
  - สิ่งที่จะทำ
  - กระทบอะไร
  - ย้อนกลับได้ไหม
  - เหตุผล
  - ถ้าไม่ยืนยันจะเกิดอะไร
- Critical action displays warning and disables permanent approval button.
- WebSocket hook now sends `decision` instead of only boolean `approved`.

## TDD Evidence

Initial RED:

```bash
.venv/bin/python -m pytest tests/test_mayass_confirmation_policy.py -q
```

Result:

```text
5 failed
ModuleNotFoundError: No module named 'jarvis.core.mayass_policy'
AttributeError: pending_actions has no create_pending_action
AttributeError: server has no create_fake_pending_action
```

Expected: Phase 6 contract did not exist yet.

GREEN:

```bash
.venv/bin/python -m pytest tests/test_mayass_confirmation_policy.py tests/test_confirmation.py -q
```

Result:

```text
14 passed in 1.08s
```

## Automated Verification

MayAss Phase 6 + existing confirmation tests:

```text
14 passed in 1.08s
```

Compile + lint:

```text
py_compile jarvis/core/mayass_policy.py jarvis/core/pending_actions.py jarvis/core/server.py tests/test_mayass_confirmation_policy.py
ruff check jarvis/core/mayass_policy.py jarvis/core/pending_actions.py jarvis/core/server.py tests/test_mayass_confirmation_policy.py
All checks passed
```

MayAss cumulative gate:

```text
27 passed in 0.83s
```

Full regression:

```text
417 passed, 1 skipped in 7.29s
```

UI lint/build:

```text
eslint . --max-warnings=0
Next.js 15.5.18
Compiled successfully
```

## Real Smoke Evidence

Server restarted local-only after UI build.

Runtime:

```text
proc_fff99d6e3750
http://localhost:3001
PIN=[REDACTED]
MAYASS_ENABLED=true
MAYASS_REMOTE_ENABLED=false
JARVIS_ENABLE_TUNNEL=false
```

Startup log:

```text
MayAss mode enabled; skipping legacy JarvisBrain/Ollama startup.
Application startup complete.
```

API smoke:

```text
/health/ping -> {"status":"ok"}
POST /tools/pending/fake risk=high -> rich pending action with 3 decisions
POST /tools/confirm decision=confirm_always for high -> {"resolved":true}
POST /tools/pending/fake risk=critical -> rich pending action
POST /tools/confirm decision=confirm_always for critical -> {"resolved":false}
GET /tools/pending -> critical action remains pending
POST /tools/confirm decision=deny -> {"resolved":true}
GET /tools/pending -> {"pending":[]}
```

Browser smoke:

High-risk modal:
- UI received fake pending action over WebSocket.
- Modal displayed:
  - `RISK: HIGH`
  - action `delete_file`
  - target `/tmp/mayass-demo.txt`
  - reason
  - consequence if denied
  - buttons:
    - `ยืนยันครั้งนี้`
    - `ยืนยันถาวรสำหรับงานแบบนี้`
    - `ไม่ยืนยัน`
- Clicking `ไม่ยืนยัน` removed modal and cleared pending list.

Critical modal:
- UI received fake `run_shell` critical action.
- Modal displayed:
  - `RISK: CRITICAL`
  - warning: critical action cannot be permanently approved
  - `ยืนยันถาวรสำหรับงานแบบนี้` disabled
- Clicking `ยืนยันครั้งนี้` resolved and cleared pending list.

Browser console:

```text
0 JS errors
0 console messages
```

## Data / Safety Notes

- Phase 6 does not execute real tools.
- `/tools/pending/fake` is a smoke endpoint only for modal verification.
- Critical permanent approval is blocked in backend policy and visually disabled in UI.
- Existing legacy boolean confirmation remains supported for backward compatibility.

## Verdict

```text
Phase 6 Confirmation Popup + Permission Policy: PASS
Rich pending action payload: PASS
Three decisions: PASS
Critical no permanent approve: PASS
UI modal smoke: PASS
Full regression: PASS
```

## Next Phase

Canonical next phase:

```text
Phase 7 — Hermes Tool Ownership
```

Do not start Phase 7 until Boss approves moving on.
