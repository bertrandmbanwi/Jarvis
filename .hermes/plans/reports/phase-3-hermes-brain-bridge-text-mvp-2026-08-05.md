# Phase 3 Report — Hermes Brain Bridge Text MVP

วันที่: 2026-08-05
Repo: `/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi`
Phase: `3 — Hermes Brain Bridge Text MVP`
Status: `PASS`

## Goal

พิสูจน์ว่า MayAss สามารถเรียก Hermes/Maymint ได้จริงแบบ text-only โดยยังไม่แตะ `/chat` route, UI, voice, memory หรือ tool ownership

## Allowed scope

แตะเฉพาะ Phase 3:

```text
jarvis/core/mayass_bridge.py
tests/test_mayass_bridge.py
```

## Forbidden scope respected

ไม่ได้แตะใน Phase 3:

- `/chat` route
- UI
- voice
- dashboard
- tools ownership
- memory migration/quarantine

## TDD evidence

### RED

สร้าง test ก่อน:

```text
tests/test_mayass_bridge.py
```

รันก่อนสร้าง production module:

```bash
.venv/bin/python -m pytest tests/test_mayass_bridge.py -q
```

ผล RED:

```text
4 failed
ModuleNotFoundError: No module named 'jarvis.core.mayass_bridge'
```

แปลว่า test fail เพราะ bridge module ยังไม่มีจริง ถูกต้องตาม TDD

### GREEN

สร้าง:

```text
jarvis/core/mayass_bridge.py
```

เพิ่ม:

```text
MayAssBridgeRequest
MayAssBridgeResponse
MayAssBridge
build_prompt_envelope
Hermes subprocess runner
```

Targeted result:

```text
4 passed in 0.07s
```

## Implementation summary

Bridge request fields:

```text
text
source
mode
session_id
wants_voice
allow_tools
confirmation_policy
```

Safe defaults:

```text
source=mayass
mode=realtime
session_id=
wants_voice=False
allow_tools=False
confirmation_policy=safe-only
```

Bridge response fields:

```text
text
backend=hermes
mode
ok
error
```

Hermes command pattern:

```text
settings.MAYASS_HERMES_COMMAND + --profile settings.MAYASS_HERMES_PROFILE + -q <prompt>
```

Current default resolves to:

```text
hermes chat -Q --profile default -q <prompt>
```

## Prompt envelope guard

Envelope includes Maymint identity:

```text
Maymint
มาย
บอส
Maymint-Hermes
mode=realtime/work
allow_tools=False
confirmation_policy=safe-only
```

Guard confirmed no old persona leakage in bridge prompt:

```text
Becs
sir
Forney
JARVIS
```

## Verification

### 1. Phase 3 targeted tests

```bash
.venv/bin/python -m pytest tests/test_mayass_bridge.py -q
```

Result:

```text
4 passed in 0.07s
```

Status: `PASS`

### 2. Phase 1 + Phase 2 + Phase 3 targeted tests

```bash
.venv/bin/python -m pytest tests/test_mayass_settings.py tests/test_mayass_identity.py tests/test_mayass_bridge.py -q
```

Result:

```text
11 passed in 0.08s
```

Status: `PASS`

### 3. Python compile

```bash
.venv/bin/python -m py_compile jarvis/core/mayass_bridge.py tests/test_mayass_bridge.py
```

Result: exit code `0`

Status: `PASS`

### 4. Prompt contamination guard

```text
{'missing': [], 'present_forbidden': []}
```

Status: `PASS`

### 5. Hermes CLI availability

```bash
command -v hermes && hermes --version
```

Result:

```text
/Users/meuu/.local/bin/hermes
Hermes Agent v0.18.0
```

Status: `PASS`

### 6. Real Hermes smoke

Command:

```bash
MAYASS_ENABLED=true .venv/bin/python - <<'PY'
import asyncio
from jarvis.core.mayass_bridge import MayAssBridge, MayAssBridgeRequest

async def main():
    bridge = MayAssBridge(timeout=45)
    res = await bridge.process(MayAssBridgeRequest(text='ทักทายบอสสั้น ๆ ว่าเธอพร้อมแล้ว', mode='realtime'))
    print(f'ok={res.ok}')
    print(f'backend={res.backend}')
    print(f'mode={res.mode}')
    print('text=' + res.text[:300].replace('\n', ' '))
    if res.error:
        print('error=' + res.error[:500].replace('\n', ' '))
    raise SystemExit(0 if res.ok and res.text else 1)

asyncio.run(main())
PY
```

Result:

```text
ok=True
backend=hermes
mode=realtime
text=บอสสส มายพร้อมแล้วนะคะ 💖   เรียกใช้ได้เลยงับ ✨
```

Status: `PASS`

### 7. Full regression

```bash
.venv/bin/python -m pytest -q
```

Result:

```text
401 passed, 1 skipped in 7.12s
```

Status: `PASS`

### 8. Security scan

Scanned changed/untracked code files:

```text
jarvis/config/settings.py
jarvis/ui/jarvis-ui/src/components/chat/ChatView.tsx
jarvis/ui/jarvis-ui/src/components/shared/ChatInput.tsx
jarvis/core/mayass_bridge.py
jarvis/core/mayass_identity.py
tests/test_mayass_bridge.py
tests/test_mayass_identity.py
tests/test_mayass_settings.py
```

Result:

```text
security_findings: []
```

Status: `PASS`

### 9. Runtime safety

Backend health:

```text
{"status":"ok"}
```

Remote/tunnel:

```text
JARVIS_ENABLE_TUNNEL=false
cloudflared process absent
```

Status: `PASS`

## Known notes

- Phase 3 does not route UI `/chat` through MayAssBridge. That is Phase 4.
- Phase 3 does not alter voice. Voice remains Phase 8.
- Phase 3 does not migrate or quarantine old Jarvis memory/persona. That is Phase 5.
- Phase 3 real smoke uses Hermes CLI directly via subprocess and returned Maymint-style Thai output successfully.

## Rollback

Rollback Phase 3 by removing only:

```text
jarvis/core/mayass_bridge.py
tests/test_mayass_bridge.py
```

No existing route/UI/voice files are affected by Phase 3.

## Done criteria

- [x] unit tests pass
- [x] real smoke succeeds
- [x] bridge does not touch Jarvis memory/tools
- [x] bridge does not touch UI or `/chat` route
- [x] full regression pass
- [x] report written

## Final verdict

`Phase 3 — Hermes Brain Bridge Text MVP`: PASS

MayAss can call Hermes/Maymint text-only successfully. Ready for `Phase 4 — /chat Route Integration` after checkpoint/commit.
