# MayAss Master Workplan — Phases, Work Breakdown, and Subagent Assignment

> **For Hermes:** ใช้แผนนี้เป็น master execution plan ระดับ “ทำงานจริง” สำหรับแปลง Jarvis ให้เป็น MayAss/Maymint-Hermes ทีละ phase ห้ามข้าม phase โดยไม่มี gate verification

**Goal:** ทำให้ Jarvis repo กลายเป็น MayAss/Maymint จริง โดย UI/UX/runtime ยังใช้ร่าง Jarvis แต่ backend brain, memory, tools, persona, safety และ work execution เป็น Hermes/Maymint

**Architecture:** ทำแบบ staged replacement: เริ่มจาก text brain bridge → identity → memory quarantine → confirmation policy → tools ownership → voice modes → overlay → optional remote → final hardening. ใช้ subagents แยก backend/frontend/QA-audit ต่อ phase เพื่อไม่ให้มั่วและไม่ให้ context ปนกัน

**Tech Stack:** Python 3.11, FastAPI, Next.js/React/TypeScript, WebSocket, Hermes CLI/Profile/Tools, macOS voice, optional Cloudflare Tunnel

---

## 0. ภาพรวม Master Plan

แผนนี้แบ่งเป็น 10 Phases ใหญ่ และ 45 Work Packages ย่อย

```text
Phase 0  Safety Freeze + Baseline
Phase 1  MayAss Product Definition + Config Foundation
Phase 2  Identity Replacement Layer
Phase 3  Hermes Brain Bridge MVP
Phase 4  Server Routing + Chat UI Real Integration
Phase 5  Memory Quarantine + Maymint Context Ownership
Phase 6  Confirmation / Permission / Policy System
Phase 7  Hermes Tool Ownership + Jarvis Tool Deactivation
Phase 8  Voice Modes + Audio Feedback Fix
Phase 9  Overlay / Dashboard / Cinematic Full MayAss UI
Phase 10 Remote Optional + Production Hardening + Runbook
```

หลักคิด:

- Phase 0-4 = ทำให้ “มายตอบในหน้า Jarvis ได้จริง”
- Phase 5-7 = ทำให้ “มายเป็นเจ้าของ memory/tools/safety จริง”
- Phase 8 = ทำให้ “เสียงเป็นมายและไม่ซ้ำ/ไม่วน”
- Phase 9 = ทำให้ “หน้าทั้งหมดเป็น MayAss/Maymint”
- Phase 10 = ทำให้ “ใช้จริงแบบเปิด/ปิด/ดูแลได้”

---

## 1. Roles / Subagent Structure

ใช้ subagents เป็นทีม “เพื่อน ๆ” แบบนี้

### A. Lead Orchestrator — มายหลัก

**หน้าที่:**

- ถือภาพรวมทั้งหมด
- ตัดสินใจลำดับ phase
- รวมผลจาก subagents
- ไม่แก้โค้ดมั่วพร้อมกันหลายจุด
- ตรวจว่า gate ผ่านจริงก่อนให้ไปต่อ

**สิ่งที่ต้องทำทุก phase:**

- ตั้ง scope ชัด
- ส่งงานให้ subagent เฉพาะทาง
- รวบรวม diff/test output
- สรุป blocker
- ตัดสินใจ proceed/rollback

### B. Backend Bridge Agent

**หน้าที่:**

- Python/FastAPI/backend
- `jarvis/core/server.py`
- `jarvis/core/mayass_bridge.py`
- route `/chat`, `/jobs`, `/routines`
- Hermes subprocess/API bridge
- settings flags

**ห้ามทำ:**

- ไม่แตะ frontend UI ยกเว้นจำเป็นมาก
- ไม่เปิด voice/full/remote เอง

### C. Frontend UX Agent

**หน้าที่:**

- Next.js/React/TypeScript UI
- ChatView, CinematicView, DashboardView, OverlayView
- ConfirmationModal
- mode selector realtime/work
- MayAss wording

**ห้ามทำ:**

- ไม่เปลี่ยน backend logic
- ไม่ทำ fake status ที่ backend ยังไม่ส่ง

### D. Voice Runtime Agent

**หน้าที่:**

- voice listener/speaker
- audio owner policy
- mic pause during playback
- push-to-talk/realtime/work mode voice
- duplicate audio fix

**ห้ามทำ:**

- ไม่เปิด wake word/full mode จน text bridge และ audio tests ผ่าน

### E. Safety + Permission Agent

**หน้าที่:**

- confirmation policy
- popup payload
- permanent approval logic
- risk levels
- remote safety
- tool permission boundary

**ห้ามทำ:**

- ไม่ลด safety เพื่อให้ demo ผ่านเร็ว

### F. QA / Verification Agent

**หน้าที่:**

- tests
- smoke checks
- browser console
- endpoint probes
- grep for leaked Jarvis identity
- regression report

**ห้ามทำ:**

- ไม่แก้ production code ยกเว้น test harness เล็กน้อยถ้าได้รับมอบหมาย

### G. Documentation / Runbook Agent

**หน้าที่:**

- update master plan/checklist
- launch commands
- troubleshooting
- operator guide for Boss
- record known risks

---

## 2. Parallelization Rules / แบ่งงานยังไงไม่ให้ชนกัน

### 2.1 ทำพร้อมกันได้

- Backend Bridge Agent ทำ settings/bridge tests
- Frontend UX Agent ทำ static UI copy map ใน branch/scratch plan
- QA Agent ทำ baseline inventory/read-only checks
- Documentation Agent ทำ runbook draft

### 2.2 ต้องทำตามลำดับเท่านั้น

- Server route switch ต้องรอ bridge module ผ่าน test
- Voice integration ต้องรอ chat route Hermes bridge ผ่านจริง
- Tool ownership ต้องรอ confirmation policy skeleton
- Remote ต้องรอ auth/safety และ user บอกเปิด
- Full voice/wake word ต้องรอ audio owner fix

### 2.3 ห้ามทำพร้อมกันในไฟล์เดียว

ไฟล์ที่ต้อง serialize:

- `jarvis/core/server.py`
- `jarvis/config/settings.py`
- `jarvis/ui/jarvis-ui/src/app/page.tsx`
- `jarvis/ui/jarvis-ui/src/lib/types.ts`
- `jarvis/voice/listener.py`
- `jarvis/voice/speaker.py`

---

## 3. Phase 0 — Safety Freeze + Baseline

**Goal:** หยุดความเสี่ยงและรู้ baseline ก่อนแก้ code

**Owner:** Lead + QA Agent

**Subagents:**

- QA Agent: process/port/test baseline
- Documentation Agent: baseline record

### Work Package 0.1 — Kill remote tunnel

**Tasks:**

- ตรวจ `cloudflared`
- kill ถ้ามี
- ยืนยันว่า remote ปิด

**Commands:**

```bash
pgrep -fl cloudflared || true
pkill -f 'cloudflared tunnel --url http://localhost:3001' || true
pgrep -fl cloudflared || true
```

**Done when:** ไม่มี cloudflared process

### Work Package 0.2 — Inspect local runtime

**Tasks:**

- ตรวจ ports 3001/8741
- ระบุ PID
- ตัดสินใจว่าจะ kill full mode หรือคง server mode

```bash
lsof -nP -iTCP:3001 -sTCP:LISTEN || true
lsof -nP -iTCP:8741 -sTCP:LISTEN || true
```

**Done when:** รู้ว่าอะไรเปิดอยู่และไม่เปิด remote

### Work Package 0.3 — Git and test baseline

**Tasks:**

- ตรวจ git status
- รัน targeted tests ที่เกี่ยวกับ auth/confirmation
- บันทึก failures ถ้ามี

```bash
cd '/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi'
git status --short || true
.venv/bin/python -m pytest tests/test_auth.py tests/test_confirmation.py -q
```

**Done when:** มี baseline result ก่อนแก้

### Phase 0 Gate

ผ่านเมื่อ:

- remote off
- baseline recorded
- ไม่มี full voice risky process ที่ไม่ตั้งใจ

---

## 4. Phase 1 — Product Definition + Config Foundation

**Goal:** สร้าง flags และ product contract ให้ MayAss เปิด/ปิดได้ rollback-safe

**Owner:** Backend Bridge Agent

**Support:** QA Agent

### Work Package 1.1 — Add settings flags

**Files:**

- `jarvis/config/settings.py`
- `tests/test_mayass_settings.py`

**Flags:**

```python
MAYASS_ENABLED
MAYASS_DISPLAY_NAME
MAYASS_CODENAME
MAYASS_REMOTE_ENABLED
MAYASS_DEFAULT_MODE
MAYASS_AUDIO_OWNER
MAYASS_HERMES_COMMAND
MAYASS_HERMES_PROFILE
MAYASS_CONFIRMATION_POLICY_PATH
```

**Default policy:**

```text
MAYASS_ENABLED=false
MAYASS_REMOTE_ENABLED=false
MAYASS_DEFAULT_MODE=realtime
MAYASS_AUDIO_OWNER=browser
```

**Done when:** tests prove defaults safe

### Work Package 1.2 — Add MayAss product constants

**Files:**

- `jarvis/core/mayass_identity.py`
- `tests/test_mayass_identity.py`

**Includes:**

- display name
- codename
- assistant short name `มาย`
- user display `บอส`
- greeting
- shutdown line

**Done when:** identity module does not import heavy runtime and tests pass

### Work Package 1.3 — Add run mode matrix doc in code comments

**Files:**

- `jarvis/core/mayass_bridge.py` later or `mayass_identity.py`

**Modes:**

- realtime
- work

**Done when:** tests validate mode names

### Phase 1 Gate

ผ่านเมื่อ:

```bash
.venv/bin/python -m pytest tests/test_mayass_settings.py tests/test_mayass_identity.py -q
```

---

## 5. Phase 2 — Identity Replacement Layer

**Goal:** ลบ Jarvis persona จาก user-facing path โดยไม่ rename internal modules จนพัง

**Owner:** Frontend UX Agent + Backend Bridge Agent

**Support:** QA Agent

### Work Package 2.1 — Backend prompt quarantine

**Files:**

- `jarvis/config/settings.py`
- possible `jarvis/core/mayass_prompt.py`
- `tests/test_mayass_prompt.py`

**Tasks:**

- อย่าใช้ `_SYSTEM_PROMPT_STATIC` Jarvis prompt เมื่อ MayAss enabled
- สร้าง MayAss prompt builder แยก
- ห้ามมี Becs/sir/Forney default ใน MayAss prompt

**Done when:** test grep prompt แล้วไม่มี JARVIS/Becs/sir/Forney

### Work Package 2.2 — Frontend minimal identity pass

**Files:**

- `src/components/chat/ChatView.tsx`
- `src/components/auth/LoginScreen.tsx`
- `src/app/layout.tsx`

**Tasks:**

- JARVIS visible → Maymint/MayAss
- Becs → บอส
- assistant avatar J → M
- Processing → มายกำลังคิด

**Done when:** build passes and chat screen no visible Jarvis

### Work Package 2.3 — Full identity inventory

**Owner:** QA Agent

**Tasks:**

- grep visible strings
- classify internal vs user-facing

```bash
cd '/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi'
python3 - <<'PY'
from pathlib import Path
roots=[Path('jarvis'), Path('desktop-overlay')]
needles=['JARVIS','J.A.R.V.I.S.','Just A Rather','Becs','sir','Forney']
for root in roots:
    for p in root.rglob('*'):
        if p.is_file() and p.suffix in {'.py','.tsx','.ts','.html','.md','.json'}:
            s=p.read_text(errors='ignore')
            hits=[n for n in needles if n in s]
            if hits:
                print(p, hits)
PY
```

**Done when:** list exists and user-facing items have follow-up tasks

### Phase 2 Gate

ผ่านเมื่อ:

- MayAss enabled prompt clean
- minimal UI clean
- internal leftovers classified

---

## 6. Phase 3 — Hermes Brain Bridge MVP

**Goal:** ทำ bridge จริงให้ Jarvis เรียก Hermes/Maymint ได้แบบ text-only

**Owner:** Backend Bridge Agent

**Support:** QA Agent

### Work Package 3.1 — Bridge request/response models

**Files:**

- `jarvis/core/mayass_bridge.py`
- `tests/test_mayass_bridge.py`

**Classes:**

```python
MayAssBridgeRequest
MayAssBridgeResponse
MayAssBridge
```

**Done when:** model validation passes

### Work Package 3.2 — Fake runner for tests

**Tasks:**

- bridge accepts injected runner function
- fake runner returns deterministic text
- no real Hermes call in unit tests

**Done when:** tests run offline

### Work Package 3.3 — Real subprocess runner

**Command shape:**

```bash
hermes chat -Q --profile default -q '<prompt>'
```

**Rules:**

- timeout
- capture stdout/stderr
- no secret logging
- mode-specific prompt envelope

**Done when:** manual smoke can call Hermes and get text

### Work Package 3.4 — Mode prompt envelopes

**Realtime prompt:** short, Thai, grounded, no heavy tools unless needed

**Work prompt:** full Hermes work, tools allowed via Hermes, risky actions summarized for confirmation

**Done when:** tests assert prompt contains Maymint identity and not Jarvis

### Phase 3 Gate

ผ่านเมื่อ:

```bash
.venv/bin/python -m pytest tests/test_mayass_bridge.py -q
```

และ manual command:

```bash
MAYASS_ENABLED=true .venv/bin/python - <<'PY'
# import bridge and call with simple fake or real if safe
PY
```

---

## 7. Phase 4 — Server Routing + Chat UI Real Integration

**Goal:** `/chat` ใน Jarvis UI ใช้ Hermes bridge จริงเมื่อ MayAss enabled

**Owner:** Backend Bridge Agent + Frontend UX Agent

**Support:** QA Agent

### Work Package 4.1 — Shared process helper

**Files:**

- `jarvis/core/server.py`

**Function:**

```python
async def process_mayass_or_jarvis(text: str, source: str, mode: str):
    ...
```

**Done when:** `/chat` can use helper

### Work Package 4.2 — `/chat` route switch

**Current:**

```python
response = await brain.process(request.message)
```

**Target:** MayAss mode calls bridge, else fallback

**Done when:** tests show both paths

### Work Package 4.3 — Extend ChatRequest mode

**Files:**

- `jarvis/core/server.py`
- frontend API call site in `src/app/page.tsx` or related hook

**Fields:**

```python
message: str
tier: str = ""
mode: str = "realtime"
```

**Done when:** UI can send realtime/work mode later

### Work Package 4.4 — Browser text smoke

**Tasks:**

- start server in MayAss enabled server mode
- open UI
- send text
- verify response says Maymint and backend hermes

**Done when:** browser smoke passes

### Phase 4 Gate

ผ่านเมื่อ:

- `/chat` text flow is Hermes-owned
- JarvisBrain is fallback only
- UI displays response without console errors

---

## 8. Phase 5 — Memory Quarantine + Maymint Context Ownership

**Goal:** ป้องกัน Jarvis memory/profile เก่าปนกับมาย

**Owner:** Backend Bridge Agent + Safety Agent

**Support:** QA Agent

### Work Package 5.1 — Quarantine old Jarvis facts

**Files:**

- `jarvis/core/brain.py`
- `jarvis/config/settings.py`
- `jarvis/core/mayass_bridge.py`

**Tasks:**

- MayAss path must not call Jarvis memory add/process_exchange
- MayAss prompt must not include old dynamic location context
- old data remains archived, not deleted

**Done when:** tests confirm no Jarvis memory write in MayAss path

### Work Package 5.2 — Hermes session mapping

**Tasks:**

- decide how MayAss UI session maps to Hermes session
- initial version can use stable Hermes profile default
- future version can support per-browser session ids

**Done when:** documented and no fake claims

### Work Package 5.3 — Memory import review plan

**Tasks:**

- list Jarvis memory facts
- classify safe/unsafe/stale
- do not import without Boss approval

**Done when:** import is separate explicit action

### Phase 5 Gate

ผ่านเมื่อ:

- no new `JARVIS:` memory from MayAss requests
- response no longer references Becs/sir/Forney unless user said it

---

## 9. Phase 6 — Confirmation / Permission / Policy System

**Goal:** สิทธิ์เต็ม แต่ action สำคัญต้องมี popup มีข้อมูลประกอบและปุ่ม 3 แบบ

**Owner:** Safety Agent + Frontend UX Agent

**Support:** Backend Bridge Agent + QA Agent

### Work Package 6.1 — Policy data model

**Files:**

- `jarvis/core/mayass_policy.py`
- `tests/test_mayass_confirmation_policy.py`
- `data/mayass/confirmation_policy.json` generated at runtime

**Decisions:**

```text
confirm_once
confirm_always
deny
```

**Risk levels:**

```text
low, medium, high, critical
```

**Rule:** critical irreversible actions cannot be permanent-approved in v1

### Work Package 6.2 — Backend endpoint update

**Files:**

- `jarvis/core/server.py`
- `jarvis/core/pending_actions.py`

**Tasks:**

- support old approved boolean for compatibility
- add decision string
- store permanent approvals

### Work Package 6.3 — Frontend modal v2

**Files:**

- `src/components/shared/ConfirmationModal.tsx`
- `src/lib/types.ts`

**UI:**

- `ยืนยันครั้งนี้`
- `ยืนยันถาวรสำหรับงานแบบนี้`
- `ไม่ยืนยัน`

**Display:**

- action summary
- affected targets
- risk level
- reversible
- reason
- consequence if denied

### Work Package 6.4 — Confirmation smoke

**Tasks:**

- create fake pending action
- UI popup appears
- each button calls backend correctly

### Phase 6 Gate

ผ่านเมื่อ:

- modal works
- policy persists
- critical cannot be permanently approved

---

## 10. Phase 7 — Hermes Tool Ownership + Jarvis Tool Deactivation

**Goal:** เครื่องมือทั้งหมดเป็นของ Hermes/Maymint ไม่ใช่ JarvisBrain เดิม

**Owner:** Backend Bridge Agent + Safety Agent

**Support:** QA Agent

### Work Package 7.1 — Tool ownership map

**Tasks:**

Map Jarvis tools to Hermes equivalents:

```text
jarvis/tools/filesystem.py     → Hermes file tools
jarvis/tools/shell.py          → Hermes terminal tool
jarvis/tools/browser_agent.py  → Hermes browser tool or later bridge
jarvis/tools/mac_control.py    → Hermes/macOS skill or controlled bridge
jarvis/tools/notes_access.py   → Hermes Apple Notes skill if available
jarvis/tools/calendar_email.py → Hermes/Google/Apple skills if configured
```

### Work Package 7.2 — Disable old autonomous executor in MayAss path

**Files:**

- `jarvis/core/server.py`
- `jarvis/core/brain.py`
- `jarvis/agent/executor.py` tests only if needed

**Rule:** MayAss request should not call `AgentExecutor.execute`

### Work Package 7.3 — Action result cards

**Frontend:** show Hermes action results in Jarvis UI cards later

**Backend:** MayAssBridgeResponse supports `action_cards`

### Phase 7 Gate

ผ่านเมื่อ:

- MayAss chat/work request does not route through Jarvis agent executor
- risky action requires confirmation or Hermes-side approval

---

## 11. Phase 8 — Voice Modes + Audio Feedback Fix

**Goal:** เสียงเป็นมาย มี 2 mode และไม่เล่นซ้ำ/ไม่วนไมค์

**Owner:** Voice Runtime Agent

**Support:** Backend Bridge Agent + Frontend UX Agent + QA Agent

### Work Package 8.1 — Audio owner policy

**Files:**

- `jarvis/voice/speaker.py`
- `jarvis/core/server.py`
- frontend WS audio handler

**Policy:**

```text
MAYASS_AUDIO_OWNER=browser
MAYASS_AUDIO_OWNER=macos_say
MAYASS_AUDIO_OWNER=none
```

**Default:** browser

### Work Package 8.2 — Pause mic during playback

**Files:**

- `jarvis/voice/listener.py`
- `jarvis/voice/speaker.py`

**Rules:**

- while speaking, listener paused
- no follow-up window until playback done
- no assistant speech captured as user command

### Work Package 8.3 — Realtime/work voice modes

**Tasks:**

- voice transcript sends `mode`
- realtime uses fast short response
- work mode can show thinking/progress

### Work Package 8.4 — Browser push-to-talk first

**Rule:** Do not enable wake word until push-to-talk passes

### Work Package 8.5 — Wake word optional later

**Rules:**

- off default for MayAss until stable
- manual opt-in

### Phase 8 Gate

ผ่านเมื่อ:

- one response = one audio output
- no duplicate macOS say + browser audio
- mic does not capture its own TTS
- browser PTT smoke passes

---

## 12. Phase 9 — Overlay / Dashboard / Cinematic Full MayAss UI

**Goal:** ทุก surface ที่บอสเห็นเป็น MayAss/Maymint แต่ layout Jarvis ยังอยู่

**Owner:** Frontend UX Agent

**Support:** QA Agent + Documentation Agent

### Work Package 9.1 — Cinematic surface

**Files:**

- `CinematicView.tsx`
- `BootScreen.tsx`
- arc reactor naming if visible

**Done when:** no visible JARVIS in cinematic

### Work Package 9.2 — Dashboard surface

**Files:**

- `DashboardView.tsx`
- `StatusBar.tsx`

**New status:**

- backend: Hermes
- mode: realtime/work
- remote: off/on
- audio owner
- memory: Maymint

### Work Package 9.3 — Overlay surface

**Files:**

- `OverlayView.tsx`
- `desktop-overlay/overlay.html`
- `desktop-overlay/JarvisOverlay.swift` visible strings only if safe

### Work Package 9.4 — UI identity regression test

**Task:** grep built/source for user-facing forbidden strings

Forbidden visible strings:

```text
J.A.R.V.I.S.
Just A Rather Very Intelligent System
Start a conversation with JARVIS
Becs
sir
Forney
```

Internal import path exceptions allowed with allowlist.

### Phase 9 Gate

ผ่านเมื่อ:

- browser smoke all views
- no visible Jarvis persona
- console 0 errors

---

## 13. Phase 10 — Remote Optional + Production Hardening + Runbook

**Goal:** ใช้จริงได้ และ remote เปิดได้เมื่อบอสสั่งเท่านั้น

**Owner:** Documentation Agent + Safety Agent + QA Agent

### Work Package 10.1 — Remote off default enforced

**Files:**

- `start.sh`
- `jarvis/main.py`
- `settings.py`

**Done when:** full mode with MayAss does not start tunnel unless `MAYASS_REMOTE_ENABLED=true`

### Work Package 10.2 — Named tunnel plan

**Tasks:**

- document quick tunnel limitation
- recommend named tunnel for fixed URL
- PIN/session required

### Work Package 10.3 — Launch profiles

Define 4 launch modes:

```text
mayass-server-safe      UI + backend + chat, no voice, no remote
mayass-voice-browser    UI + backend + browser PTT, no remote
mayass-work             UI + backend + Hermes tools + confirmations, no remote
mayass-remote           explicit remote tunnel + PIN, only when Boss asks
```

### Work Package 10.4 — Boss operator guide

Include:

- how to start
- how to stop
- what URL to open
- how to switch realtime/work
- what confirmation popup means
- how to disable remote
- how to diagnose duplicate voice

### Work Package 10.5 — Final regression

Run:

```bash
.venv/bin/python -m pytest -q
cd jarvis/ui/jarvis-ui && npm run build
```

Browser smoke:

- chat
- cinematic
- dashboard
- confirmation
- optional voice PTT

### Phase 10 Gate

ผ่านเมื่อ:

- safe runbook exists
- remote off default verified
- final smoke passes

---

## 14. Phase Dependency Graph

```text
Phase 0
  ↓
Phase 1
  ↓
Phase 2 ─────┐
  ↓          │
Phase 3      │
  ↓          │
Phase 4 ◄────┘
  ↓
Phase 5
  ↓
Phase 6
  ↓
Phase 7
  ↓
Phase 8
  ↓
Phase 9
  ↓
Phase 10
```

ห้ามทำ Phase 8 ก่อน Phase 4 เพราะ voice จะไม่มี Hermes brain จริง

ห้ามทำ Phase 7 ก่อน Phase 6 เพราะ tool actions ต้องมี confirmation ก่อน

ห้ามทำ Phase 10 remote ก่อน Phase 6/7 เพราะ remote + tools without safety เสี่ยงเกิน

---

## 15. Subagent Assignment by Phase

| Phase | Lead | Supporting Agents | Parallel? |
|---|---|---|---|
| 0 Baseline | QA | Lead, Docs | yes |
| 1 Config | Backend | QA | partial |
| 2 Identity | Frontend | Backend, QA | partial |
| 3 Bridge | Backend | QA | no for core file |
| 4 Route/UI integration | Backend | Frontend, QA | limited |
| 5 Memory quarantine | Backend | Safety, QA | no |
| 6 Confirmation | Safety | Frontend, Backend, QA | partial |
| 7 Tools ownership | Backend | Safety, QA | no |
| 8 Voice | Voice | Backend, Frontend, QA | no for runtime |
| 9 Full UI | Frontend | QA, Docs | yes by surface |
| 10 Hardening | QA | Safety, Docs, Lead | partial |

---

## 16. Sprint Breakdown

### Sprint 1 — Real text brain replacement

Includes:

- Phase 0
- Phase 1
- Phase 2 minimal
- Phase 3
- Phase 4

Outcome:

```text
Jarvis UI chat → Hermes/Maymint response
```

### Sprint 2 — Memory + confirmation + tools boundary

Includes:

- Phase 5
- Phase 6
- Phase 7 skeleton

Outcome:

```text
MayAss is not contaminated by Jarvis memory and risky actions ask Boss
```

### Sprint 3 — Voice stabilization

Includes:

- Phase 8

Outcome:

```text
MayAss voice works without duplicate audio or feedback loop
```

### Sprint 4 — Full UI transformation

Includes:

- Phase 9

Outcome:

```text
Every visible Jarvis surface becomes MayAss/Maymint
```

### Sprint 5 — Production runbook + remote optional

Includes:

- Phase 10

Outcome:

```text
Boss can start/stop/use MayAss safely and optionally enable remote
```

---

## 17. Acceptance Criteria by Sprint

### Sprint 1 Done

- MayAss flags exist
- identity module exists
- Hermes bridge exists
- `/chat` routes to Hermes when enabled
- UI minimal chat labels say Maymint
- no remote tunnel
- tests pass for new bridge/settings/identity/chat route

### Sprint 2 Done

- MayAss path does not write Jarvis memory
- old Jarvis profile facts do not leak
- confirmation popup v2 exists
- permanent policy exists but blocks critical permanent approval
- old Jarvis tool executor bypassed for MayAss request path

### Sprint 3 Done

- browser PTT voice sends transcript to Hermes bridge
- exactly one audio output owner
- mic paused during playback
- wake word remains off unless explicitly enabled

### Sprint 4 Done

- Cinematic, Chat, Dashboard, Overlay user-facing surfaces say MayAss/Maymint
- no visible JARVIS/Becs/sir/Forney
- build passes
- browser console clean

### Sprint 5 Done

- remote off default verified
- named/quick tunnel docs exist
- launch commands documented
- final regression/smoke report exists

---

## 18. Master Checklist

### Foundation

- [ ] Remote tunnel off
- [ ] Runtime baseline recorded
- [ ] Git status recorded
- [ ] Python 3.11 tests baseline recorded

### Config/Identity

- [ ] `MAYASS_ENABLED`
- [ ] `MAYASS_REMOTE_ENABLED=false` default
- [ ] `MAYASS_AUDIO_OWNER`
- [ ] MayAss identity module
- [ ] MayAss prompt builder

### Brain

- [ ] Bridge request/response models
- [ ] Hermes subprocess runner
- [ ] realtime prompt envelope
- [ ] work prompt envelope
- [ ] `/chat` route switch
- [ ] UI chat smoke via Hermes

### Memory

- [ ] Jarvis memory quarantine
- [ ] no `JARVIS:` MayAss writes
- [ ] no Becs/sir/Forney leakage
- [ ] old memory import review deferred

### Safety

- [ ] confirmation payload v2
- [ ] Thai modal labels
- [ ] confirm_once
- [ ] confirm_always
- [ ] deny
- [ ] critical permanent denial rule

### Tools

- [ ] Hermes tool ownership map
- [ ] Jarvis agent executor bypassed in MayAss path
- [ ] action cards planned
- [ ] risky action confirmation

### Voice

- [ ] audio owner single source
- [ ] browser only default
- [ ] mic pause during playback
- [ ] no follow-up while speaking
- [ ] browser PTT smoke
- [ ] wake word optional later

### UI

- [ ] ChatView MayAss
- [ ] Cinematic MayAss
- [ ] Dashboard MayAss
- [ ] Overlay MayAss
- [ ] StatusBar MayAss
- [ ] Login MayAss

### Remote/Runbook

- [ ] remote off default
- [ ] remote explicit enable only
- [ ] PIN/session docs
- [ ] start/stop commands
- [ ] troubleshooting duplicate audio
- [ ] final smoke report

---

## 19. Recommended Execution Protocol

ทุก phase ใช้รอบนี้:

```text
1. Lead defines exact work package
2. Assign one main subagent
3. Subagent writes/updates tests first
4. Run expected RED if code behavior missing
5. Implement minimal change
6. Run GREEN targeted tests
7. QA Agent verifies with independent command/smoke
8. Lead updates checklist
9. Proceed to next work package
```

ถ้า test fail:

```text
- stop phase
- document failure
- fix only related scope
- do not continue to next phase
```

ถ้าพบ security/remote/voice loop issue:

```text
- kill risky process first
- record logs
- continue only in server/text mode
```

---

## 20. First Command Set for Sprint 1

```bash
cd '/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi'

# baseline
git status --short || true
pgrep -fl cloudflared || true
lsof -nP -iTCP:3001 -sTCP:LISTEN || true
lsof -nP -iTCP:8741 -sTCP:LISTEN || true
.venv/bin/python -m pytest tests/test_auth.py tests/test_confirmation.py -q

# after implementation
.venv/bin/python -m pytest \
  tests/test_mayass_settings.py \
  tests/test_mayass_identity.py \
  tests/test_mayass_bridge.py \
  tests/test_mayass_chat_route.py \
  -q

cd jarvis/ui/jarvis-ui
npm run build
```

---

## 21. Final Note

แผนนี้ตั้งใจให้ “ทำครบ phase แล้วจบงานเป็นระบบจริง” ไม่ใช่ทำ demo กระจัดกระจาย

จุดจบที่ต้องเห็นจริงคือ:

```text
บอสเปิด UI เดิมสไตล์ Jarvis
แต่ทุกอย่างที่คุย เห็น จำ ทำงาน ใช้เครื่องมือ และพูดตอบ คือมาย/Maymint/Hermes ทั้งหมด
```

ถ้าทำครบทุก phase ตาม gate นี้ ระบบ Jarvis เดิมจะถูกแทนด้วย MayAss อย่างมีหลักฐานและ rollback ได้
