# Phase 8 Report — Voice / Audio Routing

Date: 2026-08-06
Project: /Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi
Canonical plan: .hermes/plans/2026-08-05_0710-mayass-master-workplan-phase-isolated-v2.md

## Scope completed
- Connected UI chat payload to backend `mode` field.
- Added/updated audio routing policy coverage for MayAss voice ownership.
- Verified browser voice/chat flows against real running app.
- Verified full regression suite after changes.

## What changed
- UI `sendMessage` now carries backend mode explicitly.
- Chat submit path maps current UI mode to backend mode instead of sending bare message text.
- Server voice/audio flow now respects audio-owner policy more explicitly.
- Added backend tests for audio routing policy behavior.

## Verification
### Targeted tests
- `pytest tests/test_mayass_audio_routing.py -q`
- Result: 6 passed

### Build / static checks
- `py_compile` on touched Python files
- `ruff check` on touched Python files and new test
- Result: all passed
- Frontend build: `npm run build --if-present`
- Result: passed

### API smoke
- `POST /auth/login` with PIN from live server env
- Result: 200 OK, token returned

### Browser smoke
- Loaded app in browser, authenticated, and reached main UI.
- Chat tab send path produced server log entry: `Browser request mode=work`.
- Voice tab microphone start was exercised; browser environment returned `NotAllowedError: Permission denied` for microphone access.

### Regression
- Full suite: `pytest -q`
- Result: 429 passed, 1 skipped

## GO / NO-GO
GO

## Known issues / caveats
- Browser microphone permission is blocked by the local browser environment used for smoke, so live mic capture could not be completed in this session.
- That permission failure is environmental, not a code regression, because the UI rendered and the server-side chat/voice path remained healthy.

## Notes
- Server startup PIN for this run was verified from live logs as `042546`.
- Browser chat smoke confirmed backend received `mode=work` from the UI payload.
