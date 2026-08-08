# MayAss Master Workplan V2 — Phase-Isolated, Bug-Fixable, Demo-Visible Plan

> **For Hermes:** แผนนี้แทนแผน phase/subagent เดิมในระดับ execution control เพราะเพิ่มกฎ “แต่ละ Phase ต้องแยกขอบเขต แก้บัคใน Phase นั้นได้ทันที และมีผลลัพธ์ที่บอสเห็น/เทสจริงได้”

**Goal:** แปลง Jarvis repo ให้กลายเป็น MayAss/Maymint-Hermes แบบทำจริงทีละ Phase โดยทุก Phase ต้องมีผลลัพธ์ที่เห็นได้ เทสได้ และถ้าเจอบัคในขอบเขต Phase นั้นต้องแก้ให้จบก่อนข้าม Phase

**Architecture:** Phase-isolated staged replacement. แต่ละ Phase มี sandbox scope, allowed files, bugfix boundary, demo artifact, real-system smoke test, rollback rule และ completion gate ของตัวเอง

**Tech Stack:** Python 3.11, FastAPI, Next.js/React/TypeScript, WebSocket, Hermes CLI/Profile/Tools, macOS voice, optional Cloudflare Tunnel

---

## 0. กฎใหม่ที่บอสขอเพิ่ม

### 0.1 แต่ละ Phase ต้องแยกจากกัน

ทุก Phase ต้องมี:

- ขอบเขตชัดเจนว่าแตะไฟล์ไหนได้
- ห้ามแก้ไฟล์นอก Phase ยกเว้นจำเป็นและต้องบันทึกเหตุผล
- มี test ของ Phase เอง
- มี demo/smoke ของ Phase เอง
- มี rollback point ของ Phase เอง
- มี bugfix loop ของ Phase เอง

### 0.2 ถ้าเจอบัคใน Phase ไหน ให้แก้ใน Phase นั้นทันที

ถ้าบัคเกิดจากงาน Phase ปัจจุบัน:

```text
เจอบัค → หยุดเพิ่มฟีเจอร์ → เขียน/เพิ่ม test จับบัค → แก้เฉพาะ scope phase → run test → smoke → ค่อยไปต่อ
```

ห้ามพูดว่า “ไปแก้ Phase หน้า” ถ้าบัคนั้นทำให้ผลลัพธ์ Phase นี้ใช้ไม่ได้

### 0.3 ถ้าบัคเกี่ยวกับ Phase อื่น

ให้แยกเป็น 3 ประเภท:

1. **Blocking cross-phase bug**
   - ทำให้ Phase ปัจจุบัน test/demo ไม่ได้
   - ต้องสร้าง hotfix ภายใน Phase ปัจจุบัน แต่แยก commit/notes เป็น `phase-X-cross-hotfix`

2. **Non-blocking inherited bug**
   - มีอยู่ก่อนแล้ว แต่ไม่ทำให้ Phase นี้พัง
   - บันทึกใน Known Issues ห้ามเอาไปปนกับ Done

3. **Future-phase bug**
   - เกี่ยวกับ feature ที่ยังไม่ถึง Phase
   - บันทึกไว้ แต่ไม่แก้ตอนนี้ถ้าไม่ block

### 0.4 แต่ละ Phase ต้องมีผลลัพธ์ที่บอสเห็นภาพ

ทุก Phase ต้องตอบได้ว่า:

- บอสจะเห็นอะไรเปลี่ยนไป
- เปิดหน้าไหนดู
- กด/พิมพ์อะไรเพื่อเทส
- output ที่ถูกต้องควรเป็นแบบไหน
- ถ้าผิดจะรู้ได้ยังไง

### 0.5 ห้ามนับ Phase ผ่านจากแค่ “เขียนโค้ดเสร็จ”

Phase ผ่านได้ต่อเมื่อ:

```text
code + test + real smoke + visible result + bugfix loop clean + phase report
```

---

## 1. Phase Execution Template

ทุก Phase ต้องใช้ template นี้

```text
Phase N: ชื่อ Phase
Purpose: ทำไปเพื่ออะไร
User-visible outcome: บอสจะเห็นอะไร
Allowed scope: ไฟล์/ระบบที่แก้ได้
Forbidden scope: ไฟล์/ระบบที่ห้ามแตะ
Subagents: ใครทำอะไร
Work packages: งานย่อย
Bugfix boundary: บัคแบบไหนแก้ใน Phase นี้
Real test: วิธีเทสจริง
Visual check: บอสดูอะไร
Done criteria: ผ่านเมื่อไร
Rollback: ถ้าพังย้อนยังไง
Phase report: ต้องสรุปอะไร
```

---

## 2. Subagent Bugfix Protocol

### 2.1 Roles

- Lead Orchestrator: คุม scope และตัดสินใจว่าบัคอยู่ใน Phase นี้ไหม
- Backend Agent: แก้ Python/FastAPI/Hermes bridge
- Frontend Agent: แก้ React/UI/UX
- Voice Agent: แก้ mic/audio/TTS/WebSocket voice
- Safety Agent: แก้ confirmation/policy/permissions
- QA Agent: reproduce bug, write failing test/smoke, verify fix
- Docs Agent: update phase report/runbook

### 2.2 Bug loop ต่อ Phase

```text
1. QA reproduce bug
2. Lead classify bug: current-phase / inherited / future / cross-blocking
3. If current-phase: add test or smoke step
4. Responsible agent fixes minimal scope
5. QA reruns exact failing test
6. QA reruns Phase gate
7. Docs records bug + fix + verification
8. Lead allows Phase continue
```

### 2.3 Bugfix ห้ามทำอะไร

- ห้าม rewrite architecture เพื่อแก้บัคเล็ก
- ห้ามแก้หลาย Phase พร้อมกันโดยไม่บันทึก
- ห้ามปิด test เพื่อให้ผ่าน
- ห้ามบอกว่าผ่านถ้า smoke จริงยังไม่ผ่าน
- ห้ามเปิด remote/full voice เพื่อ debug ถ้า Phase ยังไม่ถึง

---

## 3. Phase 0 — Safety Freeze + Baseline

### Purpose

ทำให้พื้นที่ทำงานปลอดภัยก่อนเริ่ม และรู้ baseline จริง

### User-visible outcome

บอสจะเห็นรายงานชัดว่า:

- ตอนนี้ remote tunnel ปิดแล้วหรือยัง
- UI/backend เปิดอยู่ไหม
- test baseline เป็นยังไง
- มี process เสี่ยงอะไรไหม

### Allowed scope

- Read-only commands
- Kill `cloudflared` ถ้ามี
- เขียน phase report เท่านั้น

### Forbidden scope

- ห้ามแก้ production code
- ห้ามเปิด remote
- ห้ามเปิด full voice ใหม่

### Subagents

- QA Agent: process/port/test baseline
- Docs Agent: phase report
- Lead: ตัดสินใจ stop/keep process

### Work packages

#### WP0.1 Check process and tunnel

```bash
pgrep -fl cloudflared || true
lsof -nP -iTCP:3001 -sTCP:LISTEN || true
lsof -nP -iTCP:8741 -sTCP:LISTEN || true
```

#### WP0.2 Stop remote tunnel

```bash
pkill -f 'cloudflared tunnel --url http://localhost:3001' || true
pgrep -fl cloudflared || true
```

#### WP0.3 Baseline tests

```bash
cd '/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi'
.venv/bin/python -m pytest tests/test_auth.py tests/test_confirmation.py -q
```

### Bugfix boundary

แก้ได้เฉพาะ:

- process/tunnel ค้าง
- test command ใช้ Python ผิดตัว
- port conflict ที่ block baseline

ห้ามแก้ app logic ใน Phase 0

### Real test

- `cloudflared` ไม่รัน
- port status ชัด
- test baseline มี output จริง

### Visual check for Boss

ไม่มี UI ใหม่ใน Phase นี้ แต่บอสเห็น summary:

```text
Remote: OFF
UI: ON/OFF
Backend: ON/OFF
Baseline tests: PASS/FAIL with reason
```

### Done criteria

- remote off
- baseline recorded
- known process state recorded

### Rollback

ไม่มี code change ต้อง rollback แค่ restart process ถ้าจำเป็น

---

## 4. Phase 1 — MayAss Config Foundation

### Purpose

สร้างสวิตช์เปิด/ปิด MayAss ให้ rollback-safe ก่อนแก้สมองจริง

### User-visible outcome

บอสยังไม่เห็น UI เปลี่ยนเยอะ แต่ระบบจะมี flag ชัด:

```text
MAYASS_ENABLED=true/false
MAYASS_REMOTE_ENABLED=false default
MAYASS_AUDIO_OWNER=browser default
```

### Allowed scope

- `jarvis/config/settings.py`
- `tests/test_mayass_settings.py`

### Forbidden scope

- ห้ามแก้ UI
- ห้ามแก้ voice
- ห้าม route chat

### Subagents

- Backend Agent: settings flags
- QA Agent: tests

### Work packages

#### WP1.1 Add tests first

Create `tests/test_mayass_settings.py`

Tests:

- default MayAss disabled
- remote disabled default
- audio owner browser default
- invalid mode fallback

#### WP1.2 Add settings flags

Modify `jarvis/config/settings.py`

Add:

```python
MAYASS_ENABLED
MAYASS_DISPLAY_NAME
MAYASS_CODENAME
MAYASS_REMOTE_ENABLED
MAYASS_DEFAULT_MODE
MAYASS_AUDIO_OWNER
MAYASS_HERMES_COMMAND
MAYASS_HERMES_PROFILE
```

#### WP1.3 Verify settings reload behavior

Run:

```bash
.venv/bin/python -m pytest tests/test_mayass_settings.py -q
```

### Bugfix boundary

แก้ได้เฉพาะ:

- env parsing bug
- invalid default bug
- import-time settings bug

ถ้า UI พังจากไม่ได้แตะ UI ถือเป็น inherited/cross bug ให้บันทึก ไม่แก้ใน Phase นี้ เว้นแต่ block test

### Real test

```bash
MAYASS_ENABLED=true .venv/bin/python - <<'PY'
from jarvis.config import settings
print(settings.MAYASS_ENABLED)
print(settings.MAYASS_REMOTE_ENABLED)
print(settings.MAYASS_AUDIO_OWNER)
PY
```

Expected:

```text
True
False
browser
```

### Visual check for Boss

Terminal output แสดง flags จริง

### Done criteria

- tests pass
- env flags read correctly
- default remote off

### Rollback

ตั้ง `MAYASS_ENABLED=false` แล้วระบบกลับ Jarvis path เดิม

---

## 5. Phase 2 — MayAss Identity Layer

### Purpose

สร้าง identity MayAss/Maymint กลางระบบก่อนเปลี่ยน UI ทั้งหมด

### User-visible outcome

บอสจะเห็นอย่างน้อย chat empty state หรือ label บางจุดเริ่มเป็น:

```text
คุยกับมาย
Maymint
บอส
มายกำลังคิด...
```

### Allowed scope

- `jarvis/core/mayass_identity.py`
- `tests/test_mayass_identity.py`
- Minimal UI identity files:
  - `jarvis/ui/jarvis-ui/src/components/chat/ChatView.tsx`

### Forbidden scope

- ห้ามแก้ backend chat routing
- ห้ามแก้ voice
- ห้ามแก้ dashboard ทั้งหมดใน Phase นี้

### Subagents

- Backend Agent: identity module
- Frontend Agent: minimal ChatView labels
- QA Agent: visible string check

### Work packages

#### WP2.1 Identity module

Create `jarvis/core/mayass_identity.py`

Contains:

- display name
- assistant short name
- user display name
- greeting
- shutdown line

#### WP2.2 Identity tests

Create `tests/test_mayass_identity.py`

Assert:

- no JARVIS
- user = บอส
- assistant = มาย

#### WP2.3 Minimal ChatView UI labels

Modify `ChatView.tsx` only:

- `Start a conversation with JARVIS` → `คุยกับมาย`
- `JARVIS` visible assistant name → `Maymint`
- `J` avatar → `M`
- `Becs` → `บอส`
- `Processing...` → `มายกำลังคิด...`

### Bugfix boundary

แก้ได้เฉพาะ:

- wrong visible label
- TypeScript compile error caused by ChatView changes
- identity module import error

ห้ามแก้ broader styling unless ChatView unusable

### Real test

Backend:

```bash
.venv/bin/python -m pytest tests/test_mayass_identity.py -q
```

Frontend:

```bash
cd jarvis/ui/jarvis-ui
npm run build
```

### Visual check for Boss

Open local UI:

```text
http://127.0.0.1:3001
```

บอสควรเห็นใน Chat page:

- `คุยกับมาย` หรือ Maymint wording
- ไม่มี `Start a conversation with JARVIS`
- ไม่มี `Becs` ใน chat bubble labels

### Done criteria

- identity tests pass
- frontend build pass
- visible ChatView identity changed

### Rollback

Revert only `ChatView.tsx`, `mayass_identity.py`, test file

---

## 6. Phase 3 — Hermes Brain Bridge Text MVP

### Purpose

พิสูจน์ว่า MayAss เรียก Hermes/Maymint ได้จริงแบบ text-only

### User-visible outcome

ยังไม่ route UI หลัก แต่มี backend smoke ที่ตอบจาก Hermes จริง

บอสจะเห็น terminal output ประมาณ:

```text
backend=hermes
mode=realtime
text=มายพร้อมแล้วค่ะบอส...
```

### Allowed scope

- `jarvis/core/mayass_bridge.py`
- `tests/test_mayass_bridge.py`

### Forbidden scope

- ห้ามแก้ `/chat` route
- ห้ามแก้ UI
- ห้ามแก้ voice

### Subagents

- Backend Agent: bridge
- QA Agent: fake runner tests + real Hermes smoke

### Work packages

#### WP3.1 Request/response models

Create:

```python
MayAssBridgeRequest
MayAssBridgeResponse
```

Fields:

- text
- source
- mode
- session_id
- wants_voice
- allow_tools
- confirmation_policy

#### WP3.2 Fake runner tests

Tests must not require Hermes process

#### WP3.3 Real Hermes subprocess runner

Command pattern:

```bash
hermes chat -Q --profile default -q '<prompt>'
```

#### WP3.4 Prompt envelopes

- realtime envelope
- work envelope

Both must contain Maymint identity and not Jarvis

### Bugfix boundary

แก้ได้เฉพาะ:

- subprocess timeout
- prompt contamination
- stdout parsing
- bridge response format

ถ้า Hermes CLI config มีปัญหา ให้บันทึก as environment blocker และ provide fake-runner test pass

### Real test

```bash
cd '/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi'
.venv/bin/python -m pytest tests/test_mayass_bridge.py -q
```

Manual smoke:

```bash
MAYASS_ENABLED=true .venv/bin/python - <<'PY'
import asyncio
from jarvis.core.mayass_bridge import MayAssBridge, MayAssBridgeRequest
async def main():
    bridge = MayAssBridge()
    res = await bridge.process(MayAssBridgeRequest(text='ทักทายบอสสั้น ๆ', mode='realtime'))
    print(res.backend)
    print(res.mode)
    print(res.text[:300])
asyncio.run(main())
PY
```

### Visual check for Boss

Terminal output ต้องเป็นภาษา/ตัวตนมาย ไม่ใช่ Jarvis

### Done criteria

- unit tests pass
- real smoke succeeds or environment blocker documented honestly
- bridge does not touch Jarvis memory/tools

### Rollback

Remove `mayass_bridge.py` and tests. No existing route affected

---

## 7. Phase 4 — `/chat` Route Integration

### Purpose

ทำให้ Jarvis Chat UI ส่งข้อความเข้า Hermes/Maymint จริง

### User-visible outcome

บอสเปิด UI เดิมแล้วพิมพ์คุยกับมายได้จริงในหน้าเดิม

Expected:

```text
บอสพิมพ์: มาย ตอนนี้เธอคือระบบอะไร
ระบบตอบ: มายคือ Maymint/Hermes ที่รันผ่าน MayAss shell...
```

### Allowed scope

- `jarvis/core/server.py`
- `tests/test_mayass_chat_route.py`
- optional frontend mode payload only if necessary

### Forbidden scope

- ห้ามแก้ voice
- ห้ามแก้ tools ownership
- ห้ามแก้ dashboard full rebrand

### Subagents

- Backend Agent: route helper
- QA Agent: API route tests + browser smoke
- Frontend Agent: only if request payload needs mode support

### Work packages

#### WP4.1 Add process helper

Create helper in `server.py` or small module:

```python
async def process_user_request(text, source='chat', mode='realtime')
```

#### WP4.2 Switch `/chat`

If `MAYASS_ENABLED=true`, use MayAss bridge
Else use JarvisBrain fallback

#### WP4.3 Route tests

Tests:

- MayAss off → Jarvis brain called
- MayAss on → bridge called
- response shape unchanged

#### WP4.4 Real UI smoke

Start:

```bash
MAYASS_ENABLED=true MAYASS_REMOTE_ENABLED=false JARVIS_OPEN_DASHBOARD=false JARVIS_UI_MODE=dev UI_PORT=3001 API_PORT=8741 ./start.sh server
```

Open:

```text
http://127.0.0.1:3001
```

Send:

```text
มาย ตอบสั้น ๆ ว่าตอนนี้เธอใช้สมองอะไร
```

### Bugfix boundary

แก้ได้เฉพาะ:

- `/chat` route error
- bridge integration bug
- response format mismatch
- UI cannot display chat response due to backend shape

ห้ามแก้ voice/audio here

### Real test

```bash
curl -sS -X POST http://127.0.0.1:8741/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"มายทักทายบอสสั้น ๆ","mode":"realtime"}'
```

### Visual check for Boss

- เปิด UI เดิม
- พิมพ์แล้วคำตอบขึ้นใน chat
- คำตอบเป็นมาย ไม่ใช่ JARVIS

### Done criteria

- route tests pass
- curl smoke pass
- browser chat smoke pass
- no visible Jarvis in chat response

### Rollback

Set `MAYASS_ENABLED=false`; route returns Jarvis fallback

---

## 8. Phase 5 — Memory Quarantine

### Purpose

ตัด Jarvis memory/profile เก่าออกจาก MayAss path

### User-visible outcome

บอสจะไม่เห็นมายพูดข้อมูลเก่าผิด ๆ เช่น Becs, sir, Forney, Texas เว้นแต่บอสพูดเอง

### Allowed scope

- `jarvis/core/mayass_bridge.py`
- `jarvis/core/brain.py` only for guards
- `jarvis/config/settings.py` prompt quarantine
- `tests/test_mayass_memory_quarantine.py`

### Forbidden scope

- ห้ามลบ data/memory เดิม
- ห้าม import memory Jarvis เข้า Hermes อัตโนมัติ

### Subagents

- Backend Agent: memory boundary
- Safety Agent: contamination rules
- QA Agent: leakage tests

### Work packages

#### WP5.1 Add leakage tests

Test forbidden strings in MayAss prompt:

- JARVIS
- Becs
- sir
- Forney
- Texas as default location

#### WP5.2 Prevent Jarvis memory writes

MayAss path must not call:

- `self.memory.add` with `JARVIS:`
- `self.memory.process_exchange` from old brain

#### WP5.3 Archive-only policy

Old memory remains untouched. Import later only after review

### Bugfix boundary

แก้ได้เฉพาะ:

- old prompt leakage
- memory write leakage
- wrong context in MayAss response

### Real test

Ask UI:

```text
มาย จำได้ไหมว่าผมชื่ออะไร ตอบตามบริบทของมายเท่านั้น
```

Expected:

- calls user บอส if known
- does not say Becs/sir/Forney

### Visual check for Boss

Chat response should feel like Maymint, not Jarvis

### Done criteria

- leakage tests pass
- real chat does not surface old Jarvis persona/facts

### Rollback

Disable MayAss mode; old Jarvis memory remains untouched

---

## 9. Phase 6 — Confirmation Popup + Permission Policy

### Purpose

ให้สิทธิ์ Maymint ทำงานจริง แต่ action สำคัญต้องมี popup ให้บอสตัดสินใจ

### User-visible outcome

บอสเห็น popup ใหม่พร้อม 3 ปุ่ม:

```text
ยืนยันครั้งนี้
ยืนยันถาวรสำหรับงานแบบนี้
ไม่ยืนยัน
```

และเห็นข้อมูลประกอบ:

- มายจะทำอะไร
- กระทบอะไร
- risk level
- ย้อนกลับได้ไหม
- เหตุผล

### Allowed scope

- `jarvis/core/mayass_policy.py`
- `jarvis/core/pending_actions.py`
- `jarvis/core/server.py` confirmation endpoints
- `src/components/shared/ConfirmationModal.tsx`
- `src/lib/types.ts`
- `tests/test_mayass_confirmation_policy.py`

### Forbidden scope

- ห้ามเปิด tool execution ใหม่ก่อน policy ผ่าน
- ห้าม permanent approve critical destructive action

### Subagents

- Safety Agent: policy engine
- Frontend Agent: modal UI
- Backend Agent: endpoint
- QA Agent: modal/API tests

### Work packages

#### WP6.1 Policy engine

Decisions:

- confirm_once
- confirm_always
- deny

#### WP6.2 Rich pending action payload

Fields:

- action_type
- affected_targets
- reversible
- reason
- consequence_if_denied
- permanent_policy_key

#### WP6.3 Modal UI v2

Thai labels + risk explanation

#### WP6.4 API smoke

- create fake pending action
- approve once
- deny
- approve always

### Bugfix boundary

แก้ได้เฉพาะ:

- popup not showing
- button wrong decision
- policy persistence bug
- critical approval bug

### Real test

Use fake pending action endpoint/test fixture, then open UI and verify modal

Expected UI:

```text
Risk: high
มายกำลังจะ...
[ยืนยันครั้งนี้] [ยืนยันถาวรสำหรับงานแบบนี้] [ไม่ยืนยัน]
```

### Done criteria

- backend policy tests pass
- modal displays correctly
- each button sends correct decision
- critical cannot be permanent-approved

### Rollback

Fallback to old approve/deny endpoint if needed, but keep MayAss tool execution blocked until v2 works

---

## 10. Phase 7 — Hermes Tool Ownership

### Purpose

เปลี่ยนความเป็นเจ้าของ tools จาก JarvisBrain เป็น Hermes/Maymint

### User-visible outcome

บอสสั่งงานจริงผ่าน UI แล้ว Maymint ใช้ Hermes tools หรือขอ confirmation ก่อนทำ ไม่ใช่ Jarvis agent เดิมแอบทำเอง

### Allowed scope

- `jarvis/core/server.py`
- `jarvis/core/mayass_bridge.py`
- tests for no Jarvis agent executor call
- action card response models

### Forbidden scope

- ห้ามลบ Jarvis tools เดิม
- ห้ามให้ Jarvis AgentExecutor เป็น decision maker หลักใน MayAss mode

### Subagents

- Backend Agent: tool boundary
- Safety Agent: risk mapping
- QA Agent: executor bypass tests

### Work packages

#### WP7.1 Tool map

Document:

```text
file → Hermes file tools
shell → Hermes terminal
browser → Hermes browser
notes/calendar → Hermes skills if configured
```

#### WP7.2 Bypass Jarvis executor

MayAss path must not call `AgentExecutor.execute`

#### WP7.3 Action cards skeleton

Bridge response can include action cards for UI later

### Bugfix boundary

แก้ได้เฉพาะ:

- old Jarvis executor called in MayAss path
- action result not shown
- confirmation not triggered for risky planned actions

### Real test

Ask work mode:

```text
มาย ช่วยบอกสถานะระบบแบบอ่านอย่างเดียว
```

Expected:

- response through Hermes path
- no unsafe Jarvis tool execution

### Done criteria

- MayAss requests do not route through old Jarvis agent executor
- risky actions stop at confirmation

### Rollback

Set `MAYASS_ENABLED=false` to restore old Jarvis tool behavior

---

## 11. Phase 8 — Voice Modes + Audio Fix

### Purpose

ทำเสียงเป็นมาย และแก้เสียงซ้ำ/ไมค์วน

### User-visible outcome

บอสมี 2 voice modes:

```text
คุยเร็ว
ทำงานจริง
```

และเมื่อมายตอบ เสียงออกครั้งเดียว ไม่เล่นซ้ำ 2 รอบ

### Allowed scope

- `jarvis/voice/speaker.py`
- `jarvis/voice/listener.py`
- `jarvis/core/server.py` audio routing
- frontend WebSocket audio handling
- tests `test_mayass_audio_routing.py`

### Forbidden scope

- ห้ามเปิด remote
- ห้าม wake word default จน PTT ผ่าน

### Subagents

- Voice Agent: audio policy
- Frontend Agent: mode selector/audio client
- QA Agent: log verification

### Work packages

#### WP8.1 Audio owner

Default:

```text
MAYASS_AUDIO_OWNER=browser
```

Rules:

- browser owner → no macOS say for same turn
- macOS say owner → no browser voice_audio
- none → text only

#### WP8.2 Pause mic during playback

No listening while speaking

#### WP8.3 Browser PTT smoke

User clicks mic manually

#### WP8.4 Realtime/work mode selector

Voice sends mode to backend

### Bugfix boundary

แก้ได้เฉพาะ:

- duplicate audio
- mic captures own TTS
- wrong client receives audio
- mode not sent with voice

### Real test

1. Start server MayAss voice browser mode
2. Open UI
3. Click mic manually
4. Speak short Thai
5. Verify one response, one audio
6. Check logs no simultaneous macOS say + voice_audio for same turn

### Visual check for Boss

- mode selector visible
- state shows listening/transcribing/thinking/speaking
- no repeated voice

### Done criteria

- one audio owner verified
- browser PTT works
- no feedback loop

### Rollback

Set `MAYASS_AUDIO_OWNER=none` for text-only safe mode

---

## 12. Phase 9 — Full MayAss UI Surface

### Purpose

ทุกหน้าที่บอสเห็นเปลี่ยนจาก Jarvis เป็น MayAss/Maymint โดย UX/HUD เดิมยังอยู่

### User-visible outcome

บอสเปิดทุก view แล้วเห็นเป็น MayAss:

- Chat
- Cinematic
- Dashboard
- Overlay
- Status
- Login

### Allowed scope

Frontend mostly:

- `src/components/cinematic/*`
- `src/components/dashboard/*`
- `src/components/overlay/*`
- `src/components/shared/*`
- `src/components/auth/LoginScreen.tsx`
- `desktop-overlay/overlay.html`

### Forbidden scope

- ห้ามเปลี่ยน backend brain route
- ห้ามแก้ voice runtime ยกเว้น UI display bug

### Subagents

- Frontend Agent: UI surfaces
- QA Agent: visual/browser console
- Docs Agent: screenshots/report

### Work packages

#### WP9.1 Cinematic MayAss

Visible JARVIS → MayAss/Maymint

#### WP9.2 Dashboard MayAss

Show backend as Hermes, memory as Maymint, remote off/on

#### WP9.3 Overlay MayAss

Overlay visible strings become Maymint

#### WP9.4 Forbidden visible strings check

Forbidden in visible UI:

- J.A.R.V.I.S.
- Just A Rather Very Intelligent System
- Start a conversation with JARVIS
- Becs
- sir
- Forney

### Bugfix boundary

แก้ได้เฉพาะ:

- UI string leakage
- broken layout from UI changes
- TS/build errors
- browser console errors from touched UI

### Real test

```bash
cd jarvis/ui/jarvis-ui
npm run build
```

Browser:

- open chat
- switch cinematic
- switch dashboard
- open overlay page
- inspect console

### Visual check for Boss

บอสเห็น screenshot/หน้าเว็บที่ทุก surface เป็น MayAss/Maymint

### Done criteria

- build pass
- browser console clean
- no forbidden visible strings

### Rollback

Revert frontend files only

---

## 13. Phase 10 — Remote Optional + Production Hardening

### Purpose

ทำให้ระบบเริ่ม/หยุด/ใช้จริงได้ และ remote ปิด default ตามที่บอสสั่ง

### User-visible outcome

บอสมี run modes ชัด:

```text
safe text mode
browser voice mode
work mode
remote mode เฉพาะตอนสั่งเปิด
```

### Allowed scope

- `start.sh`
- `jarvis/main.py`
- docs/runbook
- tests for remote off default

### Forbidden scope

- ห้ามเปิด remote โดย default
- ห้าม hardcode PIN

### Subagents

- Safety Agent: remote policy
- Docs Agent: runbook
- QA Agent: final smoke

### Work packages

#### WP10.1 Launch profiles

Define commands:

- `mayass-server-safe`
- `mayass-voice-browser`
- `mayass-work`
- `mayass-remote`

#### WP10.2 Remote off default test

```bash
MAYASS_ENABLED=true MAYASS_REMOTE_ENABLED=false ./start.sh full
pgrep -fl cloudflared || true
```

Expected: none

#### WP10.3 Operator guide

For Boss:

- เปิดยังไง
- ปิดยังไง
- ใช้ voice ยังไง
- เปิด remote ยังไงเมื่อพร้อม
- ถ้าเสียงซ้ำทำยังไง

#### WP10.4 Final regression

```bash
.venv/bin/python -m pytest -q
cd jarvis/ui/jarvis-ui && npm run build
```

### Bugfix boundary

แก้ได้เฉพาะ:

- launch script bug
- remote starts when it should not
- runbook mismatch
- final smoke blockers from MayAss launch config

### Real test

- start safe mode
- chat works
- stop mode
- start browser voice mode
- PTT works
- remote remains off

### Visual check for Boss

บอสได้คำสั่งเปิดใช้งานจริงและหน้าที่เปิดแล้วเห็น MayAss พร้อมใช้

### Done criteria

- runbook exists
- remote off default verified
- launch modes tested
- final smoke report complete

---

## 14. Phase Report Format

หลังจบแต่ละ Phase ต้องมี report สั้น ๆ แบบนี้

```text
Phase N: <name>
Status: PASS / BLOCKED / ROLLED BACK
Changed files:
Tests run:
Real smoke:
User-visible result:
Bugs found:
Bugs fixed in phase:
Known inherited issues:
Next phase allowed: yes/no
```

Report เก็บใน:

```text
.hermes/plans/reports/phase-N-<slug>.md
```

---

## 15. Master Done Criteria

งานทั้งหมดจบเมื่อ:

- Phase 0-10 PASS
- แต่ละ Phase มี report
- MayAss UI ใช้ได้จริง
- `/chat` ใช้ Hermes/Maymint จริง
- memory เป็น Maymint ไม่ปน Jarvis
- tools เป็น Hermes-owned
- confirmation popup v2 ใช้ได้
- voice ไม่ซ้ำ/ไม่ feedback
- remote off default
- runbook พร้อมให้บอสใช้

---

## 16. สรุปภาพที่บอสจะเห็นหลังแต่ละ Sprint

### หลัง Sprint 1 / Phase 0-4

บอสเปิด UI Jarvis เดิม แล้วพิมพ์คุยกับมายได้จริง

### หลัง Sprint 2 / Phase 5-7

มายไม่ปน memory Jarvis และ action สำคัญมี popup ให้ยืนยัน

### หลัง Sprint 3 / Phase 8

บอสคุยเสียงกับมายได้แบบไม่ซ้ำ ไม่วนไมค์ มี realtime/work mode

### หลัง Sprint 4 / Phase 9

ทุกหน้าเป็น MayAss/Maymint เต็มภาพ ไม่เห็น Jarvis persona

### หลัง Sprint 5 / Phase 10

บอสมีระบบที่เปิด/ปิด/ใช้งานจริงได้ พร้อม runbook และ remote เป็น optional

---

## 17. Recommended Next Step

เริ่ม Phase 0 ก่อนเท่านั้น

ห้ามเริ่มเขียน bridge หรือ UI จนกว่า:

- remote off verified
- baseline tests recorded
- process state clear

เพราะถ้า baseline ไม่ชัด เวลาเจอบัคจะไม่รู้ว่าเป็นบัคเดิมหรือบัคจาก Phase ใหม่
