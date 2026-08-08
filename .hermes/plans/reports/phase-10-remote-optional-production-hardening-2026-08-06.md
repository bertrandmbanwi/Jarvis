# Phase 10 Report — Remote Optional + Production Hardening

Date: 2026-08-06
Project: /Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi
Canonical plan: .hermes/plans/2026-08-05_0710-mayass-master-workplan-phase-isolated-v2.md

## Phase scope

Purpose: make MayAss runnable with clear local launch profiles and keep remote/tunnel access off by default.

Allowed scope used:
- `.hermes/runbooks/mayass-launch-modes.md`
- `tests/test_mayass_runbook.py`

Forbidden scope respected:
- Did not enable remote by default.
- Did not hardcode a persistent PIN in source/config.
- Did not change provider/auth behavior.
- Did not open a tunnel.

## User-visible result

Boss now has an operator runbook with four launch profiles:
- `mayass-server-safe`
- `mayass-voice-browser`
- `mayass-work`
- `mayass-remote`

The runbook also covers:
- how to open MayAss
- how to stop MayAss
- browser voice / push-to-talk usage
- remote access rules
- duplicate audio troubleshooting

Runbook path:
`.hermes/runbooks/mayass-launch-modes.md`

## TDD evidence

### RED
Added an operator-readiness assertion to `tests/test_mayass_runbook.py`.
Initial targeted run failed because the runbook did not yet include operator guide sections:

```text
1 failed, 1 passed
AssertionError: assert 'how to open' in text
```

### GREEN
Updated `.hermes/runbooks/mayass-launch-modes.md` with the missing launch/operator sections.

Targeted verification:
```text
pytest tests/test_mayass_runbook.py -q
2 passed
```

## Regression evidence

Full backend/test regression:
```text
pytest -q
432 passed, 1 skipped
```

Frontend build after UI-related prior phase changes:
```text
npm run build --if-present
Compiled successfully
Linting and checking validity of types ... passed
Static generation passed
```

## Runtime smoke evidence

Server restarted after frontend build with local work-mode flags:

```text
MAYASS_ENABLED=true
MAYASS_REMOTE_ENABLED=false
JARVIS_ENABLE_TUNNEL=false
JARVIS_OPEN_DASHBOARD=false
MAYASS_DEFAULT_MODE=work
JARVIS_UI_MODE=dev
UI_PORT=3001
API_PORT=8741
./start.sh server
```

Process evidence:
```text
Cloudflare Tunnel: cloudflared found (...)
  Tunnel is disabled by default. Set JARVIS_ENABLE_TUNNEL=true for phone access.
Starting JARVIS UI on http://0.0.0.0:3001 (dev) ...
Local: http://localhost:3001
Starting API SERVER on http://localhost:8741
MayAss mode enabled; skipping legacy JarvisBrain/Ollama startup.
Application startup complete.
Uvicorn running on http://127.0.0.1:8741
```

Browser smoke:
- Opened `http://localhost:3001`.
- Login screen title showed `MayAss`.
- Entered the live launch PIN via the split PIN inputs.
- Main shell showed `MayAss`, `Online`, tabs `Voice`, `Chat`, `System`, `Flows`.
- Chat tab opened and showed the Maymint chat empty state.
- Typed a local UI smoke message into the chat input without submitting, because direct `/chat` POST smoke had previously been blocked by the safety harness.
- System tab opened and showed MayAss activity copy.
- Flows tab opened and showed workflow builder plus App Lifecycle section with:
  - Mode: `server`
  - Runtime: `running`
  - API: `:8741`
  - UI: `:3001`

Console evidence:
- No JavaScript errors.
- WebSocket connected/registered.
- Warnings observed: deprecated `THREE.Clock` warning only; inherited/non-blocking.

Server log evidence:
- `/auth/login` returned 200 after PIN entry.
- `/auth/status`, `/costs`, `/workflows/overview`, `/team`, `/calendar/connections`, `/product/overview`, `/public-data/status` returned 200 during browser smoke.

## Final remote-off/API smoke evidence

After Boss explicitly granted permission to run the previously blocked terminal smoke, the remote-off/API check was rerun successfully.

Command evidence:
```text
pgrep -fl cloudflared || true
```
Result: no `cloudflared` process output.

API smoke:
```text
GET http://127.0.0.1:8741/health
healthy: true

GET http://127.0.0.1:8741/auth/status
authenticated: true
local: true
auth_required: true

GET http://127.0.0.1:8741/app/lifecycle/status
status: online
runtime.status: running
runtime.mode: server
ports.api: 8741
ports.ui: 3001
processes.tunnel.pid: null
processes.tunnel.running: false
processes.ollama.pid: null
processes.ollama.running: false
```

Process log also confirms:
```text
Tunnel is disabled by default. Set JARVIS_ENABLE_TUNNEL=true for phone access.
MayAss mode enabled; skipping legacy JarvisBrain/Ollama startup.
Application startup complete.
```

## Bugs found / fixed

- Current-phase issue: runbook was missing canonical launch profile names and operator guide sections.
- Fixed by adding tested runbook coverage.
- Browser smoke transient: one snapshot returned an empty page after first Chat click; refresh + relogin + repeated Chat click produced the expected Chat surface with no console JS errors. Classified as transient browser snapshot/dev-session issue, not confirmed product regression.

## Known inherited issues / caveats

- `start.sh` still prints legacy JARVIS ASCII/banner in terminal output. This is not user-facing browser UI, but it is operator-visible and may deserve a future cleanup pass if Boss wants terminal launch branding fully MayAss too.
- Console logs still say `[JARVIS WS]`; internal naming remains from the old app and was outside Phase 10 scope.
- Direct submit/chat API smoke was not repeated in this phase because the harness previously blocked that class of action.

## GO / NO-GO

GO for Phase 10 scope as implemented: launch runbook, remote-off default policy, local startup, UI lifecycle, regression tests, and browser read/UI smoke.

GO for fresh `pgrep` remote-off check and local API/lifecycle smoke after Boss granted permission. Phase 10 is now fully verified for the planned local/remote-optional scope.

## Manual Boss checklist

1. Open `.hermes/runbooks/mayass-launch-modes.md`.
2. Start local work mode:
   ```bash
   MAYASS_ENABLED=true MAYASS_REMOTE_ENABLED=false JARVIS_ENABLE_TUNNEL=false MAYASS_DEFAULT_MODE=work ./start.sh server
   ```
3. Open `http://localhost:3001`.
4. Confirm the UI says MayAss and shows Online.
5. Open Chat, System, and Flows.
6. Confirm App Lifecycle shows `server`, API `:8741`, UI `:3001`.
7. Only use `mayass-remote` when Boss explicitly wants phone/remote access.
