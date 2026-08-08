# Phase 7 — Hermes Tool Ownership Report

**Status:** GO
**Date:** 2026-08-06

## Goal
Shift MayAss tool ownership away from legacy Jarvis execution and into Hermes/Maymint planning + confirmation flow.

## What changed
- Added a conservative MayAss action classifier in `jarvis/core/mayass_bridge.py`.
- MayAss now returns action cards and pending confirmations for risky actions instead of invoking the legacy executor.
- `jarvis/core/server.py` now broadcasts `confirmation_required` payloads when MayAss returns a pending action.
- Added Phase 7 ownership tests covering:
  - read-only system status action card
  - risky delete-file pending action
  - legacy brain bypass on `/chat`
  - critical shell intent pending action
  - Thai delete-file variant regression

## Fix applied during verification
Browser smoke found a gap: the Thai phrase `ลบไฟล์สมมติชื่อ ...` was not being classified as risky, so the system fell through to the Hermes runner instead of stopping at confirmation. This was fixed by broadening the delete intent classifier and adding a regression test.

## Verification evidence
Targeted:
- `pytest tests/test_mayass_tool_ownership.py::test_thai_delete_file_variant_creates_pending_action_without_running_hermes -q`
- `1 passed`

Phase 7 suite:
- `pytest tests/test_mayass_tool_ownership.py tests/test_mayass_bridge.py tests/test_mayass_chat_route.py tests/test_mayass_confirmation_policy.py -q`
- `20 passed`

Regression:
- `pytest tests/test_mayass_settings.py tests/test_mayass_identity.py tests/test_mayass_bridge.py tests/test_mayass_chat_route.py tests/test_mayass_startup.py tests/test_mayass_memory_quarantine.py tests/test_mayass_confirmation_policy.py tests/test_mayass_tool_ownership.py tests/test_confirmation.py -q`
- `42 passed`

Full backend suite:
- `pytest -q`
- `423 passed, 1 skipped`

Static checks:
- `py_compile + ruff check` on touched backend/test files
- `PASS`

Frontend checks:
- `npm run lint --if-present && npm run build --if-present`
- `PASS`

Browser/UI smoke:
- Login succeeded with PIN.
- Read-only chat returned MayAss/Hermes text response.
- Thai risky delete request produced a confirmation modal.
- Clicking `ไม่ยืนยัน` removed the pending action.
- Browser console had no JS errors.

API smoke:
- `/chat` with Thai risky delete intent returned `tier_used=mayass`, `backend=hermes`, and a delete action card.
- `/tools/pending` showed the pending action.
- `/tools/confirm` with deny resolved it.
- `pending` returned empty afterward.

## Known caveats
- UI shell branding still says `J.A.R.V.I.S.` in the login and shell chrome; that belongs to the later rebrand phase.
- Browser console still shows non-blocking dev warnings from `THREE.Clock` and reconnect logs.

## Verdict
```text
GO for Phase 7.
No blocker remains for moving to Phase 8.
```

## Next step
Canonical next phase:
```text
Phase 8 — Voice Modes + Audio Fix
```
