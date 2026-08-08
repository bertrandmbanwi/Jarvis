# Phase 2 UI Deep Test — Chat Identity Surface

วันที่: 2026-08-05
Repo: `/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi`
Phase: `2 — MayAss Identity Layer`
Status: `PASS after one UI inconsistency fix`

## Purpose

เทสหน้า UI จริงอย่างละเอียด เพื่อหา:

- บัค
- ความไม่สอดคล้องของ wording
- visible regression
- console error
- build/runtime mismatch
- remote/tunnel side effect

## Fresh verification commands

### Backend targeted tests

```bash
.venv/bin/python -m pytest tests/test_mayass_settings.py tests/test_mayass_identity.py -q
```

Result:

```text
7 passed in 0.05s
```

### Full regression

```bash
.venv/bin/python -m pytest -q
```

Result:

```text
397 passed, 1 skipped in 6.61s
```

### Frontend production build

```bash
cd jarvis/ui/jarvis-ui && npm run build
```

Result:

```text
✓ Compiled successfully
✓ Generating static pages (5/5)
```

### Static UI string guard

Checked:

Required strings:

```text
คุยกับมาย
Maymint
บอส
มายกำลังคิด...
ถามมายได้เลย...
```

Forbidden strings in Chat surface:

```text
Start a conversation with JARVIS
Becs
Ask JARVIS anything...
Thinking...
Processing...
```

Result:

```text
{'missing': [], 'present_forbidden': []}
```

## Real browser UI test

Opened local UI:

```text
http://127.0.0.1:3001/
```

Restarted server-only after build to avoid Next dev `.next` artifact mismatch.

Server command:

```bash
JARVIS_ENABLE_TUNNEL=false JARVIS_OPEN_DASHBOARD=false JARVIS_UI_MODE=dev UI_PORT=3001 API_PORT=8741 ./start.sh server
```

Logged into the local UI with generated runtime PIN. PIN is intentionally not recorded in this report.

Clicked Chat.

Observed in accessibility/browser snapshot:

```text
CONVERSATION
คุยกับมาย
Type below or switch to Voice mode
Message input
```

Observed input placeholder via browser inspection:

```text
ถามมายได้เลย...
```

Interaction check:

- typed into Message input
- Send button became enabled
- did not submit message
- no chat route / brain call was intentionally triggered

## Console / visual check

Console:

```text
js_errors: []
```

Warnings observed:

```text
THREE.THREE.Clock: This module has been deprecated. Please use THREE.Timer instead.
```

Classification:

```text
Inherited Three.js warning, not caused by Phase 2 ChatView/ChatInput wording change.
```

Visual:

- no white screen
- no Next error overlay
- Chat page renders
- top header still says J.A.R.V.I.S. by design for Phase 2

## Bug found and fixed

### P2-UI-001 — Chat input placeholder still said JARVIS

Evidence from real browser screenshot:

```text
Ask JARVIS anything...
```

Root cause:

`ChatView.tsx` had been updated, but the placeholder belongs to shared component:

```text
jarvis/ui/jarvis-ui/src/components/shared/ChatInput.tsx
```

Scope analysis:

Search showed `ChatInput` is imported only by:

```text
jarvis/ui/jarvis-ui/src/components/chat/ChatView.tsx
```

So changing this placeholder affects only Chat UI, not dashboard/cinematic.

Fix:

```text
Ask JARVIS anything... -> ถามมายได้เลย...
```

Reverification after fix:

- targeted backend tests pass
- full pytest pass
- frontend build pass
- static UI string guard pass
- browser visual check pass

## Known visible non-bugs / future phase items

These remain visible but are out of Phase 2 scope:

```text
J.A.R.V.I.S. top header
J.A.R.V.I.S. login title
VOICE / SYSTEM / FLOWS nav labels
Good afternoon, sir. proactive notification
Type below or switch to Voice mode
```

Reason:

- Full UI rebrand is Phase 9
- Memory/persona/proactive quarantine is Phase 5
- Voice mode changes are Phase 8
- Phase 2 only covers minimal Chat identity surface

## Runtime safety

Checked:

```text
/health/ping -> {"status":"ok"}
UI port 3001 LISTEN
Backend port 8741 LISTEN
cloudflared process absent
```

Remote remains disabled by env:

```text
JARVIS_ENABLE_TUNNEL=false
```

## Final verdict

Phase 2 UI deep test: `PASS`

One real UI inconsistency was found and fixed:

```text
ChatInput placeholder now says ถามมายได้เลย...
```
