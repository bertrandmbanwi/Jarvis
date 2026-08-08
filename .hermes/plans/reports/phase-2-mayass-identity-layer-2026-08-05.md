# Phase 2 Report — MayAss Identity Layer

วันที่: 2026-08-05
Repo: `/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi`
Phase: `2 — MayAss Identity Layer`
Status: `PASS`

## Goal

สร้าง user-facing identity layer ของ MayAss/Maymint และเปลี่ยน ChatView label ขั้นต่ำให้บอสเห็นผลใน UI โดยไม่แตะ backend chat routing, voice, dashboard, cinematic, tools หรือ memory

## Allowed scope

แตะเฉพาะ:

```text
jarvis/core/mayass_identity.py
tests/test_mayass_identity.py
jarvis/ui/jarvis-ui/src/components/chat/ChatView.tsx
```

## Forbidden scope respected

ไม่ได้แตะ:

- backend chat routing
- voice
- dashboard full rebrand
- cinematic full rebrand
- tools ownership
- memory quarantine
- remote tunnel

## TDD evidence

### RED

สร้าง test ก่อนใน:

```text
tests/test_mayass_identity.py
```

รันก่อนสร้าง production module:

```bash
.venv/bin/python -m pytest tests/test_mayass_identity.py -q
```

ผล RED:

```text
3 failed
ModuleNotFoundError: No module named 'jarvis.core.mayass_identity'
```

แปลว่า test fail เพราะ identity module ยังไม่มีจริง ถูกต้องตาม TDD

### GREEN

สร้าง:

```text
jarvis/core/mayass_identity.py
```

เพิ่ม identity constants:

```text
display_name = MayAss
codename = Maymint-Hermes
assistant_name = Maymint
assistant_short_name = มาย
user_display_name = บอส
greeting = มายพร้อมแล้วค่ะบอส
shutdown_line = มายพักระบบให้แล้วค่ะบอส
```

เพิ่ม chat labels:

```text
empty_state = คุยกับมาย
assistant_label = Maymint
assistant_avatar = M
user_label = บอส
user_avatar = B
streaming_placeholder = มายกำลังคิด...
processing_status = มายกำลังคิด...
```

Targeted result:

```text
3 passed in 0.01s
```

## UI changes

แก้เฉพาะ `ChatView.tsx`:

```text
Start a conversation with JARVIS -> คุยกับมาย
J avatar -> M
Becs -> บอส
JARVIS -> Maymint
Thinking... -> มายกำลังคิด...
Processing... -> มายกำลังคิด...
```

ไม่ได้เปลี่ยน LoginScreen / StatusBar / Dashboard / Cinematic เพราะอยู่นอก Phase 2 scope

## Verification

### 1. Backend identity tests

```bash
.venv/bin/python -m pytest tests/test_mayass_identity.py -q
```

Result:

```text
3 passed in 0.01s
```

Status: `PASS`

### 2. Phase 1 + Phase 2 targeted tests

```bash
.venv/bin/python -m pytest tests/test_mayass_settings.py tests/test_mayass_identity.py -q
```

Result:

```text
7 passed in 0.07s
```

Status: `PASS`

### 3. Python compile

```bash
.venv/bin/python -m py_compile jarvis/core/mayass_identity.py tests/test_mayass_identity.py
```

Result: exit code `0`

Status: `PASS`

### 4. Static ChatView string check

Checked required strings:

```text
คุยกับมาย
Maymint
บอส
มายกำลังคิด...
```

Checked forbidden old strings in ChatView:

```text
Start a conversation with JARVIS
Becs
Thinking...
Processing...
```

Result:

```text
required_present=True
forbidden_absent=True
```

Status: `PASS`

### 5. Frontend build

```bash
cd 'jarvis/ui/jarvis-ui'
npm run build
```

Result:

```text
Compiled successfully
Route (app) / 39.2 kB, First Load JS 142 kB
Route (app) /overlay 195 kB, First Load JS 298 kB
```

Status: `PASS`

### 6. Full regression

```bash
.venv/bin/python -m pytest -q
```

Result:

```text
397 passed, 1 skipped in 7.11s
```

Status: `PASS`

### 7. Browser visual check

Opened:

```text
http://127.0.0.1:3001/
```

Logged into local UI using the generated local PIN from server log. PIN value is intentionally not repeated in this report.

Clicked Chat.

Observed ChatView text:

```text
คุยกับมาย
Type below or switch to Voice mode
```

Status: `PASS`

## Bugs / blockers found during Phase 2

### B1. Next dev server showed empty/500 after `npm run build` while dev server was running

Evidence from process log:

```text
TypeError: __webpack_modules__[moduleId] is not a function
Could not find the module ... segment-explorer-node.js#SegmentViewNode
GET / 500
```

Classification:

```text
cross-blocking verification/runtime artifact issue
```

Root cause:

`npm run build` wrote/changed `.next` artifacts while the Next dev server was already running, causing a dev manifest mismatch. The production build itself passed.

Fix applied:

Restarted server-only local process:

```text
killed old proc_767b1b16bf6a
started new proc_a164d96933b4 with JARVIS_ENABLE_TUNNEL=false, server mode only
```

Result:

- backend healthy
- UI accessible again
- visual check completed

No production code fix was needed.

## Known inherited / future-phase observations

These are visible but not Phase 2 bugs:

1. Header/Login/Status still show `J.A.R.V.I.S.`
   - Phase 2 only allows ChatView minimal labels
   - Full UI surface is Phase 9

2. Chat still does not route to Hermes/Maymint
   - Phase 4 handles `/chat` route integration

3. Jarvis prompt/memory still contains old persona facts
   - Phase 5 handles memory quarantine

4. Voice still not Maymint voice and duplicate audio is not fixed
   - Phase 8 handles voice modes/audio fix

## Runtime safety

- Remote tunnel remains off
- No cloudflared process observed
- Server is local-only
- Full voice / wake word was not started

## Rollback

Rollback Phase 2 by reverting only:

```text
jarvis/core/mayass_identity.py
tests/test_mayass_identity.py
jarvis/ui/jarvis-ui/src/components/chat/ChatView.tsx
```

## Done criteria

- [x] identity tests pass
- [x] frontend build pass
- [x] visible ChatView identity changed
- [x] full pytest pass
- [x] remote remains off
- [x] phase report written

## Final verdict

`Phase 2 — MayAss Identity Layer`: PASS

พร้อมไป `Phase 3 — Hermes Brain Bridge Text MVP` เมื่อบอสอนุมัติ
