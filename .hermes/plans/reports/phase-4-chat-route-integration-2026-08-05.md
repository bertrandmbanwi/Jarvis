# Phase 4 — `/chat` Route Integration Report

Date: 2026-08-05
Project: Jarvis → MayAss / Maymint adaptation

## Scope

Allowed:
- `jarvis/core/server.py`
- `tests/test_mayass_chat_route.py`

Effective implementation:
- Added `ChatRequest.mode` with default `realtime`.
- Added `process_user_request(text, source="chat", mode="realtime")` helper.
- `/chat` uses MayAssBridge when `MAYASS_ENABLED=true`.
- `/chat` preserves JarvisBrain fallback when `MAYASS_ENABLED=false`.
- WebSocket chat path (`/ws`, UI sends `{message: text}`) also uses MayAssBridge when enabled.
- WebSocket response remains streaming-compatible for existing UI (`token`, `done`, `full_response`).

Forbidden / not changed in this phase:
- No voice pipeline change.
- No memory ownership change.
- No remote tunnel enablement.
- No tool ownership expansion.
- No route outside `/chat` and chat WebSocket message path intentionally redesigned.

## TDD Evidence

Initial RED:

```text
pytest tests/test_mayass_chat_route.py -q
exit 1
```

Expected failure: `/chat` still routed to JarvisBrain when `MAYASS_ENABLED=true`.

GREEN:

```text
pytest tests/test_mayass_chat_route.py -q
3 passed in 1.12s
```

Backward MayAss phases:

```text
pytest tests/test_mayass_settings.py tests/test_mayass_identity.py tests/test_mayass_bridge.py tests/test_mayass_chat_route.py -q
14 passed in 0.79s
```

Compile + lint:

```text
py_compile jarvis/core/server.py tests/test_mayass_chat_route.py
ruff check jarvis/core/server.py tests/test_mayass_chat_route.py
All checks passed!
```

Full regression:

```text
pytest -q
404 passed, 1 skipped in 6.97s
```

## Real Smoke Evidence

Server launched local-only:

```text
MAYASS_ENABLED=true MAYASS_REMOTE_ENABLED=false JARVIS_PIN=042546 \
JARVIS_ENABLE_TUNNEL=false JARVIS_OPEN_DASHBOARD=false \
JARVIS_UI_MODE=dev UI_PORT=3001 API_PORT=8741 ./start.sh server
```

Runtime:

```text
/health/ping -> {"status":"ok"}
UI 3001: LISTEN
Backend 8741: LISTEN
cloudflared: not running
```

HTTP `/chat` smoke:

```text
curl -X POST http://127.0.0.1:8741/chat \
  -H 'Content-Type: application/json' \
  -H 'X-JARVIS-PIN: 042546' \
  -d '{"message":"มาย ตอบสั้น ๆ ว่าตอนนี้เธอใช้สมองอะไร","mode":"realtime"}'
```

Result:

```json
{
  "tier_used": "mayass",
  "backend": "hermes",
  "response": "ตอนนี้มายใช้สมอง Maymint-Hermes ค่ะบอส — แกนคือ Hermes Agent และโมเดลที่คุยอยู่ตอนนี้คือ GPT-5.5 ผ่าน OpenRouter น้า 💖"
}
```

Browser UI smoke:

- Opened `http://localhost:3001/`.
- Logged in with PIN `042546`.
- Opened Chat.
- Sent: `มาย ตอบสั้น ๆ ว่าตอนนี้เธอใช้สมองอะไร`.
- UI displayed Maymint response:

```text
ตอนนี้มายใช้สมอง Maymint-Hermes ผ่าน Hermes Agent ค่ะบอส 💖
```

Important bug found and fixed:
- The UI does not call HTTP `/chat`; it sends `{message: text}` through `/ws`.
- First real browser smoke exposed this: logs showed `brain.process_stream(...)` and old Jarvis routing.
- Fixed by integrating MayAss into the WebSocket chat message path too.

## Security / Scope Review

Scan findings requiring review:
- `asyncio.create_subprocess_exec` in existing ffmpeg route.
- `asyncio.create_subprocess_exec` in MayAss Hermes bridge.

Reviewed result:
- Both use argument-vector subprocess execution.
- No `shell=True`.
- No hardcoded secrets.
- No `eval`, `exec`, `pickle.loads`, or `os.system` introduced.

Phase 4 checks:

```text
has_chat_route: True
has_ws_mayass_branch: True
no_shell_true: True
```

## Verdict

```text
Phase 4 PASS
/chat HTTP integration PASS
Chat UI WebSocket integration PASS
Fallback preserved PASS
Full regression PASS
```
