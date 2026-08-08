# MayAss / Maymint-Hermes over Jarvis Detailed Implementation Plan

> **For Hermes:** ใช้แผนนี้เป็น source-of-truth สำหรับทำ implementation ทีละ gate ห้ามกระโดดไป full voice/remote ก่อน gate ก่อนหน้าผ่านจริง

**Goal:** เปลี่ยน repo Jarvis เดิมให้กลายเป็น `MayAss / Maymint` โดยคง UI/UX/runtime แบบ Jarvis แต่ให้สมอง ความจำ persona และ tools เป็น Hermes/Maymint จริง

**Architecture:** Jarvis จะถูกลดบทบาทเป็น `UI Shell + Voice/Overlay Runtime + WebSocket Renderer` ส่วน Hermes/Maymint เป็น `Brain + Memory + Tools + Safety Authority` ผ่าน MayAss bridge layer ภายใน repo เดิม ไม่สร้างเว็บแยกและไม่ทำ mockup แทนของจริง

**Tech Stack:** Python 3.11, FastAPI, Next.js/React/TypeScript, WebSocket, Hermes CLI/API bridge, macOS voice/overlay, Cloudflare Tunnel optional/off-by-default

---

## 1. Executive Summary / สรุปแบบตัดสินใจ

บอสยืนยันแล้วว่าไม่ได้ต้องการ “Jarvis ที่เปลี่ยนธีม” แต่ต้องการ “มายที่ใช้ร่าง Jarvis”

ดังนั้นแผนใหม่ต้องไม่เริ่มจากเปลี่ยนคำว่า JARVIS เป็น MayAss อย่างเดียว เพราะนั่นเป็น rebrand ผิวหน้า แก่นจริงคือ:

```text
Old:
UI → Jarvis server → JarvisBrain → Jarvis memory/tools/LLM → UI/voice

Target:
UI → Jarvis shell/server → MayAss Bridge → Hermes/Maymint brain/session/tools/memory → UI/voice
```

สิ่งที่ต้องรักษาจาก Jarvis:

- cinematic HUD
- chat page
- dashboard/status layout
- overlay page
- WebSocket events
- local backend endpoints
- voice capture/playback shell
- confirmation modal foundation
- optional tunnel capability

สิ่งที่ต้องแทนด้วย Maymint/Hermes:

- system identity
- greeting/persona/ชื่อผู้ใช้/คำเรียก
- brain decision maker
- memory/facts/preferences
- tool execution ownership
- long-running work mode
- confirmation policy
- voice style / response style

แผนเดิมถูกต้องในทิศทาง แต่ยังไม่ละเอียดพอสำหรับ implementation เพราะยังขาด:

1. file-by-file migration map
2. exact bridge contract
3. TDD gate order
4. fallback/rollback strategy
5. mode matrix realtime/work
6. audio owner design
7. confirmation “ยืนยันถาวร” policy model
8. remote off-by-default controls
9. Jarvis memory quarantine
10. Hermes tool ownership boundary
11. verification commands ต่อ gate

แผนนี้เติมช่องว่างเหล่านั้น

---

## 2. Current Source Reality / สภาพโค้ดจริงที่ตรวจพบ

### 2.1 Core backend files

- `jarvis/core/server.py`
  - FastAPI app
  - auth routes `/auth/login`, `/auth/status`, `/auth/logout`, `/auth/set-pin`
  - chat route `/chat` currently calls `brain.process(request.message)`
  - jobs/routines/workflows also call `brain.process(...)`
  - pending confirmation endpoints exist:
    - `GET /tools/pending`
    - `POST /tools/confirm`

- `jarvis/core/brain.py`
  - class `JarvisBrain`
  - initializes Jarvis LLM, memory, agent, planner, proactive, coordinator
  - `process()` is current central decision path
  - hard-coded Jarvis identity and memory writes exist, e.g. `JARVIS: {response}`
  - contains shutdown handling and proactive follow-up text with `sir`

- `jarvis/config/settings.py`
  - contains static system prompt identifying as JARVIS
  - contains user name/location defaults: `Becs`, `Forney`, `Texas`
  - contains env settings for Anthropic/Ollama/local-first/memory/auth
  - this is one of the highest-risk identity-contamination files

- `jarvis/voice/speaker.py`
  - macOS `say` TTS is active
  - caused duplicate audio when browser audio also played

- `jarvis/voice/listener.py`
  - wake word / follow-up / mic capture
  - caused feedback loop when assistant speech was picked up as follow-up

### 2.2 Frontend files

- `jarvis/ui/jarvis-ui/src/components/chat/ChatView.tsx`
  - visible strings: `Start a conversation with JARVIS`, assistant avatar `J`, assistant name `JARVIS`, user name `Becs`

- `jarvis/ui/jarvis-ui/src/components/shared/ConfirmationModal.tsx`
  - already has modal foundation
  - currently only `Approve` / `Deny`
  - needs Thai Maymint wording and `confirm_once`, `confirm_always`, `deny`

- `jarvis/ui/jarvis-ui/src/lib/types.ts`
  - `PendingConfirmation` currently:
    ```ts
    id, tool, summary, risk, created_at
    ```
  - needs richer fields: action_type, affected_targets, reversible, reason, consequence, permanent_policy_key

- Other relevant UI files:
  - `src/app/page.tsx`
  - `src/components/cinematic/CinematicView.tsx`
  - `src/components/cinematic/BootScreen.tsx`
  - `src/components/dashboard/DashboardView.tsx`
  - `src/components/overlay/OverlayView.tsx`
  - `src/components/shared/StatusBar.tsx`
  - `src/components/shared/ChatInput.tsx`
  - `src/components/settings/SettingsPanel.tsx`

### 2.3 Existing tests

- `tests/test_auth.py`
- `tests/test_confirmation.py`
- `tests/test_voice_confirm.py`
- `tests/test_voice_activation.py`
- `tests/test_permissions.py`
- `tests/test_tool_contracts.py`
- `tests/e2e/test_ui_smoke.py`

These should be reused and extended, not bypassed.

### 2.4 Important live-state warning

At analysis time, local UI/backend were still listening:

- `*:3001` node / Next UI
- `127.0.0.1:8741` Python backend

Remote tunnel was killed and should remain off unless explicitly re-enabled.

---

## 3. Product Definition / สิ่งที่ระบบสุดท้ายต้องเป็น

### 3.1 Name and identity

User-facing name: `MayAss` if Boss confirms final spelling, otherwise display name should default to `Maymint`

Recommended naming convention to avoid future ambiguity:

```text
Product display name: Maymint
System codename: MayAss
Internal bridge module: mayass
```

But if Boss insists `MayAss` is final display name, use exactly that.

### 3.2 What “เป็นมาย 100%” means in code

A response is “Maymint-owned” only if all of these are true:

1. input is routed to Hermes/Maymint brain path
2. persona/system prompt is Maymint, not Jarvis
3. memory used is Hermes/Maymint memory, not Jarvis memory
4. tools/actions are executed by Hermes or require Hermes-side approval
5. UI renders assistant as Maymint/MayAss
6. voice output uses Maymint tone/style
7. confirmation popup speaks in Maymint wording
8. no user-facing `JARVIS`, `sir`, `Becs`, `Forney` appears unless Boss intentionally says those words

### 3.3 What Jarvis is allowed to remain

Jarvis internal module names may remain temporarily if renaming them would cause high breakage:

- `jarvis/core/server.py`
- `JarvisBrain` class as compatibility wrapper
- import paths under `jarvis.*`
- CSS class names like `jarvis-cyan` until UI refactor is safe

But these must not leak to user-facing UI, voice, or prompts.

---

## 4. Target Architecture in Detail

### 4.1 Layer diagram

```text
┌─────────────────────────────────────────────────────────────┐
│                    Jarvis UI Shell                           │
│ Next.js cinematic/chat/dashboard/overlay                     │
│ - MayAss labels                                               │
│ - chat input                                                  │
│ - voice controls                                              │
│ - work/realtime mode selector                                 │
│ - confirmation popup                                          │
└─────────────────────────────┬───────────────────────────────┘
                              │ HTTP/WebSocket
┌─────────────────────────────▼───────────────────────────────┐
│                    Jarvis Server Shell                        │
│ FastAPI routes, auth, websocket, status, jobs                 │
│ - keeps /chat contract                                        │
│ - keeps /jobs if useful                                       │
│ - keeps /tools/pending /tools/confirm                         │
└─────────────────────────────┬───────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│                      MayAss Bridge                            │
│ New adapter layer inside repo                                 │
│ - mode routing: realtime/work                                 │
│ - Hermes session mapping                                      │
│ - prompt/context envelope                                     │
│ - action confirmation handoff                                 │
│ - audio owner policy                                          │
│ - Jarvis memory quarantine                                    │
└─────────────────────────────┬───────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│                    Hermes / Maymint Brain                     │
│ Existing Hermes profile                                       │
│ - Maymint persona/memory                                      │
│ - Hermes tools                                                │
│ - skills/oracle/session history                               │
│ - terminal/file/browser/etc.                                  │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Bridge modes

#### Realtime mode

Purpose: คุยเร็ว ตอบเร็ว แต่ไม่มั่ว

Rules:

- short prompt envelope
- prefer fast Hermes query or configured fast model
- no long-running tool chains unless user explicitly asks
- if information needs verification, say briefly that it needs check and offer work mode
- TTS short response
- no remote by default

#### Work mode

Purpose: งานจริง คิดนาน ทำจริง มีสถานะชัดเจน

Rules:

- use normal Hermes workflow
- allow tools
- show progress timeline in UI
- long response okay
- risky actions produce confirmation popup
- TTS may summarize final result only

---

## 5. Core Contract Design

### 5.1 MayAss bridge request

Create a Python dataclass or Pydantic model in:

`jarvis/core/mayass_bridge.py`

```python
from pydantic import BaseModel, Field
from typing import Literal

class MayAssBridgeRequest(BaseModel):
    text: str
    source: Literal["chat", "voice", "overlay", "job", "routine"] = "chat"
    mode: Literal["realtime", "work"] = "realtime"
    session_id: str = "default"
    wants_voice: bool = False
    allow_tools: bool = True
    confirmation_policy: Literal["ask_risky", "ask_all", "deny_risky"] = "ask_risky"
```

### 5.2 MayAss bridge response

```python
class MayAssBridgeResponse(BaseModel):
    text: str
    mode: str
    backend: str = "hermes"
    status: Literal["ok", "needs_confirmation", "error"] = "ok"
    elapsed_ms: float = 0
    action_cards: list[dict] = Field(default_factory=list)
    pending_confirmation: dict | None = None
    raw_error: str = ""
```

### 5.3 Server compatibility

`POST /chat` must keep old response shape so UI does not break:

```python
return ChatResponse(
    response=response.text,
    elapsed_ms=round(elapsed, 1),
    tier_used=response.mode,
    backend=response.backend,
    local_savings=savings_tracker.get_summary(),
)
```

The difference is that source becomes Hermes instead of JarvisBrain when `MAYASS_ENABLED=true`.

---

## 6. Implementation Gates

## Gate 0 — Stop unsafe runtime and baseline

**Objective:** Freeze current live process state before edits.

**Files:** none

**Steps:**

1. Stop full voice mode if running:

```bash
# Prefer Hermes process kill if process session is known, otherwise inspect first
lsof -nP -iTCP:3001 -sTCP:LISTEN || true
lsof -nP -iTCP:8741 -sTCP:LISTEN || true
pgrep -fl cloudflared || true
```

2. Keep remote tunnel off:

```bash
pkill -f 'cloudflared tunnel --url http://localhost:3001' || true
```

3. Record baseline:

```bash
cd '/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi'
git status --short || true
.venv/bin/python -m pytest tests/test_auth.py tests/test_confirmation.py -q
```

**Expected:** no cloudflared; tests either pass or failures documented before edits.

**Risk:** repo may have pre-existing test failures. Do not fix unrelated failures in this gate.

---

## Gate 1 — Configuration flags for MayAss mode

**Objective:** Add explicit feature flags so Jarvis behavior remains rollback-safe.

**Files:**

- Modify: `jarvis/config/settings.py`
- Test: create `tests/test_mayass_settings.py`

**New environment flags:**

```python
MAYASS_ENABLED = os.getenv("MAYASS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
MAYASS_DISPLAY_NAME = os.getenv("MAYASS_DISPLAY_NAME", "Maymint")
MAYASS_CODENAME = os.getenv("MAYASS_CODENAME", "MayAss")
MAYASS_REMOTE_ENABLED = os.getenv("MAYASS_REMOTE_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
MAYASS_DEFAULT_MODE = os.getenv("MAYASS_DEFAULT_MODE", "realtime").strip().lower()
MAYASS_AUDIO_OWNER = os.getenv("MAYASS_AUDIO_OWNER", "browser").strip().lower()
MAYASS_HERMES_COMMAND = os.getenv("MAYASS_HERMES_COMMAND", "hermes")
MAYASS_HERMES_PROFILE = os.getenv("MAYASS_HERMES_PROFILE", "default")
```

**Test cases:**

- default `MAYASS_ENABLED` is false
- `MAYASS_REMOTE_ENABLED` default false
- invalid default mode falls back to `realtime`
- audio owner only allows `browser`, `macos_say`, `none`

**Verification:**

```bash
cd '/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi'
.venv/bin/python -m pytest tests/test_mayass_settings.py -q
```

---

## Gate 2 — Identity pack, no UI/backend behavior change yet

**Objective:** Centralize MayAss/Maymint wording instead of scattering replacements.

**Files:**

- Create: `jarvis/core/mayass_identity.py`
- Test: `tests/test_mayass_identity.py`

**Implementation shape:**

```python
from dataclasses import dataclass
from jarvis.config import settings

@dataclass(frozen=True)
class MayAssIdentity:
    display_name: str
    codename: str
    user_name: str
    assistant_short_name: str
    greeting: str
    shutdown_line: str


def get_identity() -> MayAssIdentity:
    return MayAssIdentity(
        display_name=settings.MAYASS_DISPLAY_NAME,
        codename=settings.MAYASS_CODENAME,
        user_name="บอส",
        assistant_short_name="มาย",
        greeting="มายพร้อมแล้วค่ะบอส จะให้ช่วยอะไรดีคะ",
        shutdown_line="มายพักระบบให้แล้วค่ะบอส",
    )
```

**Important:** This gate does not rewrite every string yet. It creates the single source.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_mayass_identity.py -q
```

---

## Gate 3 — Hermes subprocess bridge, text-only

**Objective:** Create a real Hermes bridge but do not route production traffic yet.

**Files:**

- Create: `jarvis/core/mayass_bridge.py`
- Test: `tests/test_mayass_bridge.py`

**Contract:**

- `MayAssBridge.process(request)` returns `MayAssBridgeResponse`
- supports fake command injection for tests
- never logs full secret/env output
- handles timeout
- strips Hermes banners if `-Q` is used

**Subprocess command v1:**

```bash
hermes chat -Q --profile default -q '<prompt>'
```

**Prompt envelope for realtime:**

```text
คุณคือมาย/Maymint ในระบบ MayAss ที่รันผ่าน Jarvis UI shell.
ตอบไทยสั้น กระชับ อ่อนโยน ไม่อ้างว่าเป็น Jarvis.
ถ้าคำสั่งต้องใช้เครื่องมือหนักหรือเสี่ยง ให้บอกว่าควรใช้ work mode.
ข้อความจากบอส: ...
```

**Prompt envelope for work:**

```text
คุณคือ Maymint/Hermes brain สำหรับ MayAss.
ทำงานจริงผ่าน Hermes tools เท่านั้น ไม่ใช้ Jarvis tools โดยตรง.
ถ้าเป็น action เสี่ยง ให้สรุป risk และขอ confirmation แทนการทำทันทีถ้า policy ต้องถาม.
ข้อความจากบอส: ...
```

**Tests:**

- fake Hermes command returns text
- timeout returns status error
- empty input returns Thai clarification
- mode preserved
- backend is `hermes`

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_mayass_bridge.py -q
```

---

## Gate 4 — Server route switch for `/chat`

**Objective:** Route chat to Hermes bridge when `MAYASS_ENABLED=true` while preserving old route when false.

**Files:**

- Modify: `jarvis/core/server.py`
- Test: `tests/test_mayass_chat_route.py`

**Implementation point:**

Current:

```python
response = await brain.process(request.message)
```

Target:

```python
if settings.MAYASS_ENABLED:
    bridge_response = await mayass_bridge.process(MayAssBridgeRequest(...))
    response = bridge_response.text
    tier_used = bridge_response.mode
    backend = bridge_response.backend
else:
    response = await brain.process(request.message)
```

**Do not:**

- remove JarvisBrain yet
- route jobs/routines yet
- touch voice yet

**Tests:**

- with `MAYASS_ENABLED=false`, route calls `brain.process`
- with `MAYASS_ENABLED=true`, route calls MayAss bridge
- response shape remains compatible
- message length validation still works

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_mayass_chat_route.py tests/test_auth.py -q
```

---

## Gate 5 — Frontend identity pass

**Objective:** Make user-facing UI display MayAss/Maymint while preserving layout.

**Files likely to modify:**

- `jarvis/ui/jarvis-ui/src/components/chat/ChatView.tsx`
- `jarvis/ui/jarvis-ui/src/components/cinematic/CinematicView.tsx`
- `jarvis/ui/jarvis-ui/src/components/cinematic/BootScreen.tsx`
- `jarvis/ui/jarvis-ui/src/components/dashboard/DashboardView.tsx`
- `jarvis/ui/jarvis-ui/src/components/overlay/OverlayView.tsx`
- `jarvis/ui/jarvis-ui/src/components/shared/StatusBar.tsx`
- `jarvis/ui/jarvis-ui/src/components/auth/LoginScreen.tsx`
- `jarvis/ui/jarvis-ui/src/app/layout.tsx`

**Specific replacements:**

```text
J.A.R.V.I.S. → MayAss or Maymint
JARVIS → Maymint / มาย
Just A Rather Very Intelligent System → Maymint Assistant System
Becs → บอส
sir → บอส
Start a conversation with JARVIS → คุยกับมาย
Processing... → มายกำลังคิด...
Approve → ยืนยันครั้งนี้
Deny → ยกเลิก
```

**Important:** CSS class names can remain `jarvis-*` in this gate.

**Tests:**

- Add frontend static string check script/test if practical
- at minimum run build/lint if package supports it

**Verification:**

```bash
cd '/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi/jarvis/ui/jarvis-ui'
npm run lint || true
npm run build
```

Then browser smoke:

```bash
cd '/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi'
MAYASS_ENABLED=true JARVIS_OPEN_DASHBOARD=false JARVIS_UI_MODE=dev UI_PORT=3001 API_PORT=8741 ./start.sh server
```

Open:

```text
http://127.0.0.1:3001
```

Expected:

- visible UI says Maymint/MayAss
- no visible JARVIS/J.A.R.V.I.S.
- no browser console errors

---

## Gate 6 — Jarvis memory quarantine

**Objective:** Prevent old Jarvis persona/facts from contaminating Maymint.

**Files:**

- Modify: `jarvis/core/brain.py` only if MayAss fallback still touches memory
- Create/modify: `jarvis/core/mayass_bridge.py`
- Optional: `data/mayass/` new quarantine metadata folder
- Test: `tests/test_mayass_memory_quarantine.py`

**Rules:**

When `MAYASS_ENABLED=true`:

- do not call Jarvis `self.memory.add` for MayAss chat
- do not add `JARVIS: ...` memories
- do not include Jarvis conversation history in Hermes prompt unless explicitly mapped
- do not include `Becs`, `Forney`, `sir` from settings dynamic context

**Allowed:**

- archive old Jarvis memory files untouched
- expose import review later as a separate gate

**Verification:**

- test asserts MayAss path does not write to Jarvis memory
- manual grep after one chat should not create new `JARVIS:` memory entries for MayAss mode

---

## Gate 7 — Confirmation modal v2

**Objective:** Implement Boss’s confirmation model: ยืนยันครั้งนี้ / ยืนยันถาวร / ไม่ยืนยัน พร้อมข้อมูลประกอบการตัดสินใจ

**Files:**

- Modify: `jarvis/ui/jarvis-ui/src/lib/types.ts`
- Modify: `jarvis/ui/jarvis-ui/src/components/shared/ConfirmationModal.tsx`
- Modify: `jarvis/core/server.py`
- Modify/create: `jarvis/core/pending_actions.py` or new `jarvis/core/mayass_policy.py`
- Test: `tests/test_mayass_confirmation_policy.py`

**New type fields:**

```ts
export interface PendingConfirmation {
  id: string;
  tool: string;
  summary: string;
  risk: "low" | "medium" | "high" | "critical";
  created_at: number;
  action_type?: string;
  affected_targets?: string[];
  reversible?: boolean;
  reason?: string;
  consequence_if_denied?: string;
  permanent_policy_key?: string;
}
```

**UI buttons:**

- `ยืนยันครั้งนี้`
- `ยืนยันถาวรสำหรับงานแบบนี้`
- `ไม่ยืนยัน`

**Backend endpoint change:**

Current:

```python
class ConfirmActionRequest(BaseModel):
    action_id: str
    approved: bool
```

Target:

```python
class ConfirmActionRequest(BaseModel):
    action_id: str
    decision: Literal["confirm_once", "confirm_always", "deny"]
```

Keep compatibility with old `approved` for existing tests if needed.

**Policy persistence:**

Create:

`data/mayass/confirmation_policy.json`

Shape:

```json
{
  "allowed_always": {
    "open_browser_readonly": {
      "approved_at": 0,
      "label": "เปิดเว็บแบบอ่านอย่างเดียว"
    }
  }
}
```

**Critical rule:** never allow permanent approval for critical destructive actions in first version.

---

## Gate 8 — Audio owner and voice feedback fix

**Objective:** Fix duplicate audio before wiring Maymint voice.

**Files:**

- `jarvis/core/server.py`
- `jarvis/voice/speaker.py`
- `jarvis/voice/listener.py`
- frontend WS client handling in `src/app/page.tsx` or related hooks
- Test: `tests/test_mayass_audio_routing.py`

**Problem observed:**

- backend speaks with macOS `say`
- browser receives `voice_audio`
- 2 websocket clients may set `wants_audio=true`
- mic captures assistant speech as follow-up

**Policy:**

```text
MAYASS_AUDIO_OWNER=browser     → no macOS say for UI-originated turns
MAYASS_AUDIO_OWNER=macos_say   → no browser voice_audio payload
MAYASS_AUDIO_OWNER=none        → text only
```

**Runtime rules:**

- pause listener while speaker is speaking
- close follow-up window while playback active
- only requesting browser client receives audio
- non-target clients receive animation/status only

**Verification:**

- test terminal-originated voice does not broadcast to all clients in MayAss browser mode
- test browser-originated voice targets one client only
- manual log should not show both `Speaking (macos_say)` and `voice_audio` for same response

---

## Gate 9 — Voice modes UI and backend contract

**Objective:** Add two modes: realtime talk and work mode.

**Files:**

- Frontend mode selector component, likely in:
  - `src/components/shared/ChatInput.tsx`
  - `src/components/chat/ChatView.tsx`
  - maybe `src/app/page.tsx`
- Backend:
  - `ChatRequest` in `jarvis/core/server.py`
  - `MayAssBridgeRequest`

**ChatRequest target:**

```python
class ChatRequest(BaseModel):
    message: str
    tier: str = ""
    mode: str = "realtime"
```

**UI labels:**

- `คุยเร็ว`
- `ทำงานจริง`

**Mode behavior:**

- realtime: concise, fast, limited tools
- work: Hermes full tools, progress timeline, confirmation popup

**Verification:**

- `/chat` accepts mode
- UI sends mode
- bridge receives mode
- response includes `tier_used=realtime|work`

---

## Gate 10 — Jobs/routines/workflows MayAss routing

**Objective:** Ensure background jobs/routines do not call Jarvis brain when MayAss mode is enabled.

**Files:**

- `jarvis/core/server.py`
- possibly `jarvis/core/workflow_scheduler.py`
- tests around jobs/routines

**Current risk:**

Found code paths:

- `_run_chat_job`: `brain.process(message)`
- routine run: `brain.process(prompt)`
- workflow scheduler: `runner=brain.process`

**Target:**

Create helper:

```python
async def process_user_request(text: str, source: str, mode: str = "work") -> ProcessResult:
    if settings.MAYASS_ENABLED:
        return await mayass_bridge.process(...)
    return await jarvis_brain_process(...)
```

Then route all user-facing processing through helper.

**Verification:**

- chat job in MayAss mode hits bridge
- routine run in MayAss mode hits bridge
- scheduler remains disabled unless explicitly enabled

---

## Gate 11 — Tool ownership boundary

**Objective:** Make it impossible for Jarvis tools to execute as the primary agent path in MayAss mode unless explicitly bridged through Hermes.

**Files:**

- `jarvis/core/brain.py`
- `jarvis/agent/executor.py`
- `jarvis/agent/tools_schema.py`
- `jarvis/tools/*` only if needed
- `jarvis/core/mayass_bridge.py`

**Policy:**

In MayAss mode:

- Jarvis server may render tool result cards
- Jarvis may run low-level UI/voice actions
- Hermes decides tool use
- Jarvis tools are not exposed to the old Jarvis LLM planner/executor as autonomous decision maker

**Practical first step:**

- Disable old `AgentExecutor` route by bypassing `JarvisBrain.process` for chat/jobs/voice
- Do not delete Jarvis tools yet
- Later convert useful Jarvis tools into Hermes skills/MCP/plugin only if truly needed

**Verification:**

- a MayAss chat request does not call `AgentExecutor.execute`
- shell/file/browser actions require Hermes-side handling or confirmation

---

## Gate 12 — Remote access optional/off-by-default

**Objective:** Keep remote capability but prevent accidental exposure.

**Files:**

- `start.sh`
- `jarvis/main.py`
- `jarvis/config/settings.py`
- docs/runbook

**Target behavior:**

- default: no Cloudflare tunnel
- if `MAYASS_REMOTE_ENABLED=false`, start scripts must not start cloudflared even in full mode
- if enabled, PIN/login required
- quick tunnel warning shown
- named tunnel recommended for persistent URL

**Verification:**

```bash
MAYASS_ENABLED=true MAYASS_REMOTE_ENABLED=false ./start.sh full
pgrep -fl cloudflared || true
```

Expected: no cloudflared.

---

## Gate 13 — Full local smoke

**Objective:** Verify MayAss works locally before remote/full voice.

**Command:**

```bash
cd '/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi'
MAYASS_ENABLED=true \
MAYASS_REMOTE_ENABLED=false \
MAYASS_AUDIO_OWNER=browser \
JARVIS_PIN_AUTH_ENABLED=true \
JARVIS_OPEN_DASHBOARD=false \
JARVIS_UI_MODE=dev \
UI_PORT=3001 API_PORT=8741 \
./start.sh server
```

**Smoke steps:**

1. open `http://127.0.0.1:3001`
2. login if needed
3. verify UI says MayAss/Maymint
4. send text: `มาย สรุปตัวเองสั้น ๆ ว่าตอนนี้เธอคือระบบอะไร`
5. verify response says Maymint/MayAss, not Jarvis
6. verify backend response `backend=hermes`
7. verify no cloudflared
8. verify browser console 0 errors

---

## Gate 14 — Voice smoke without wake word

**Objective:** Test voice only after chat works.

**Mode:** push-to-talk/browser mic first, not always-listening.

**Rules:**

- no wake word in first MayAss voice smoke
- no follow-up auto capture until audio owner fixed
- browser-only audio owner
- user manually consents mic

**Smoke:**

1. click mic in UI
2. say short Thai request
3. transcript appears
4. transcript routes to Hermes bridge
5. response displayed
6. one audio output only
7. mic does not capture its own speech

---

## Gate 15 — Work mode with real tool confirmation

**Objective:** Demonstrate one real useful action safely.

Recommended first action:

- read-only file/status query
- then one sandbox write under `data/mayass/actions/`

Do not start with deleting files, sending messages, or remote account actions.

**Confirmation required:**

- popup shows action details
- Boss chooses `ยืนยันครั้งนี้`
- action executes
- result card displays artifact path

---

## 7. File-by-file migration map

| Area | File | Action |
|---|---|---|
| Settings | `jarvis/config/settings.py` | add MayAss flags; quarantine Jarvis prompt under non-MayAss mode |
| Identity | `jarvis/core/mayass_identity.py` | new identity single source |
| Bridge | `jarvis/core/mayass_bridge.py` | new Hermes bridge |
| Server chat | `jarvis/core/server.py` | route `/chat` through bridge if enabled |
| Server jobs | `jarvis/core/server.py` | route jobs/routines through shared process helper |
| Old brain | `jarvis/core/brain.py` | keep fallback; prevent MayAss memory writes if bypassed |
| Confirmation backend | `jarvis/core/pending_actions.py` / `mayass_policy.py` | add confirm_once/always/deny |
| UI chat | `src/components/chat/ChatView.tsx` | MayAss labels, mode display |
| UI modal | `src/components/shared/ConfirmationModal.tsx` | Thai three-choice confirmation |
| UI types | `src/lib/types.ts` | richer confirmation model, mode fields |
| UI status | `src/components/shared/StatusBar.tsx` | MayAss backend/status wording |
| Cinematic | `CinematicView.tsx`, `BootScreen.tsx` | replace visible Jarvis identity |
| Dashboard | `DashboardView.tsx` | replace visible Jarvis identity; show Hermes backend |
| Overlay | `OverlayView.tsx` | MayAss overlay wording |
| Voice speaker | `jarvis/voice/speaker.py` | obey audio owner |
| Voice listener | `jarvis/voice/listener.py` | pause during playback, disable follow-up while speaking |
| Start scripts | `start.sh`, `jarvis/main.py` | remote off default; MayAss flags |
| Tests | `tests/test_mayass_*.py` | add gates |

---

## 8. Detailed risk analysis

### Risk 1: “เปลี่ยนชื่อแล้วคิดว่าเสร็จ”

Severity: high

Mitigation:

- definition of done requires Hermes backend response
- test must assert `/chat` path calls bridge

### Risk 2: Jarvis memory contaminates Maymint

Severity: high

Evidence:

- settings has `Becs`, `Forney`, `Texas`
- runtime log showed old location fact surfaced

Mitigation:

- no Jarvis memory in MayAss path
- explicit profile quarantine
- import only after Boss approval

### Risk 3: Duplicate audio and feedback loop

Severity: high

Evidence:

- macOS say + browser audio both emitted
- mic captured assistant speech

Mitigation:

- audio owner flag
- pause mic while speaking
- no follow-up while playback active

### Risk 4: Hermes subprocess latency

Severity: medium

Mitigation:

- realtime mode uses concise query
- work mode accepts latency
- later replace subprocess with persistent Hermes service/session bridge

### Risk 5: Remote exposure

Severity: critical

Mitigation:

- remote off by default
- named tunnel later
- PIN/session/audit required

### Risk 6: Tool authority confusion

Severity: critical

Mitigation:

- Hermes is only decision maker
- Jarvis tools not autonomous in MayAss mode
- confirmation popup for risky actions

### Risk 7: Tests fail due repo pre-existing Python/version issues

Severity: medium

Mitigation:

- use `.venv/bin/python` Python 3.11
- document baseline failures before edits
- run targeted tests first

---

## 9. Verification Matrix

| Gate | Unit tests | Integration | Browser | Voice | Remote |
|---|---|---|---|---|---|
| 0 baseline | selected existing | health curl | optional | no | off |
| 1 settings | yes | no | no | no | off |
| 2 identity | yes | no | no | no | off |
| 3 bridge | yes fake subprocess | optional hermes command | no | no | off |
| 4 chat route | yes | `/chat` curl | no | no | off |
| 5 UI identity | optional static | build | yes | no | off |
| 6 memory quarantine | yes | chat smoke | yes | no | off |
| 7 confirmation | yes | pending/confirm API | modal smoke | no | off |
| 8 audio owner | yes | websocket smoke | yes | yes fake | off |
| 9 modes | yes | `/chat mode` | yes | no | off |
| 10 jobs/routines | yes | jobs API | optional | no | off |
| 11 tools boundary | yes | controlled action | yes | no | off |
| 12 remote optional | yes | process check | no | no | optional test |
| 13 full local smoke | no | server run | yes | no | off |
| 14 voice smoke | no | server run | yes | yes real opt-in | off |
| 15 real action | yes | action popup | yes | optional | off |

---

## 10. Suggested first coding sprint

Do not attempt all gates in one run. First sprint should produce a minimal but real MayAss core:

### Sprint 1 scope

- Gate 0 baseline
- Gate 1 settings
- Gate 2 identity
- Gate 3 Hermes bridge
- Gate 4 `/chat` route switch
- tiny UI label pass in ChatView only

### Sprint 1 success demo

Browser chat at `http://127.0.0.1:3001` says Maymint and response is generated by Hermes bridge.

### Sprint 1 not included

- voice
- remote
- full tool action
- all UI strings
- memory import
- overlay polish

This is intentional. Once text bridge is real, everything else can attach to it.

---

## 11. Exact first implementation task list

### Task 1: Baseline snapshot

**Objective:** Know what is running and what tests pass before edits.

**Commands:**

```bash
cd '/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi'
git status --short || true
pgrep -fl cloudflared || true
lsof -nP -iTCP:3001 -sTCP:LISTEN || true
lsof -nP -iTCP:8741 -sTCP:LISTEN || true
.venv/bin/python -m pytest tests/test_auth.py tests/test_confirmation.py -q
```

### Task 2: Add MayAss settings tests

**Create:** `tests/test_mayass_settings.py`

Test defaults and env parsing.

### Task 3: Add settings flags

**Modify:** `jarvis/config/settings.py`

Add `MAYASS_ENABLED`, `MAYASS_REMOTE_ENABLED`, `MAYASS_AUDIO_OWNER`, etc.

### Task 4: Add identity tests

**Create:** `tests/test_mayass_identity.py`

Assert display name, user name, greeting.

### Task 5: Add identity module

**Create:** `jarvis/core/mayass_identity.py`

### Task 6: Add bridge tests with fake runner

**Create:** `tests/test_mayass_bridge.py`

### Task 7: Add bridge module

**Create:** `jarvis/core/mayass_bridge.py`

### Task 8: Add chat route tests

**Create:** `tests/test_mayass_chat_route.py`

### Task 9: Route `/chat` to MayAss bridge when enabled

**Modify:** `jarvis/core/server.py`

### Task 10: Minimal ChatView identity pass

**Modify:** `src/components/chat/ChatView.tsx`

Change only obvious visible strings:

- `JARVIS` → `Maymint`
- `J` → `M`
- `Becs` → `บอส`
- `Start a conversation with JARVIS` → `คุยกับมาย`
- `Processing...` → `มายกำลังคิด...`

### Task 11: Sprint 1 verification

```bash
cd '/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi'
.venv/bin/python -m pytest tests/test_mayass_settings.py tests/test_mayass_identity.py tests/test_mayass_bridge.py tests/test_mayass_chat_route.py -q
cd jarvis/ui/jarvis-ui && npm run build
```

Then run server with MayAss enabled and smoke UI.

---

## 12. Open questions before full implementation

Only these need Boss decisions later; they do not block Sprint 1:

1. Final display name: `MayAss` or `Maymint`?
2. Realtime Hermes provider: current Hermes default, local fast model, or specific provider?
3. Work mode: current Hermes default profile okay?
4. Permanent confirmation storage: repo `data/mayass/confirmation_policy.json` okay?
5. Should old Jarvis memory be archived only, or reviewed for import later?
6. Voice output owner default: browser-only or macOS say-only?

Recommended defaults if Boss does not decide:

- display: `Maymint`
- codename: `MayAss`
- realtime/work: Hermes default initially
- confirmation policy file: `data/mayass/confirmation_policy.json`
- old Jarvis memory: archive only
- audio owner: browser-only

---

## 13. Final acceptance criteria

MayAss counts as real replacement only when:

1. `/chat` response comes from Hermes/Maymint bridge
2. UI visible identity is MayAss/Maymint
3. no visible Jarvis persona in chat/cinematic/dashboard/overlay
4. JarvisBrain is fallback only, not primary
5. Jarvis memory no longer feeds MayAss identity
6. tool authority is Hermes-owned
7. confirmation popup v2 works
8. voice has exactly one audio owner
9. remote tunnel remains off unless explicitly enabled
10. local smoke passes with actual UI/backend
11. plan/runbook documents exact launch commands

---

## 14. Recommended next action

Start with Sprint 1 only.

Why:

- It gives a real proof that Jarvis UI can speak to Hermes/Maymint
- It avoids voice/remote chaos
- It keeps rollback easy
- It proves this is not just a UI rebrand

Command style for implementation must quote Thai path:

```bash
cd '/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi' && <command>
```

Do not open Cloudflare Tunnel during implementation unless Boss explicitly says to enable remote again.
