# MAYASS / Maymint-Hermes over Jarvis Master Plan

วันที่: 2026-08-05
สถานะ: แผนยืนยันจากบอส / ยังไม่ใช่ implementation เสร็จ
โปรเจกต์ฐาน: `/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi`

## 0. สรุปเจตนาของบอส

บอสต้องการเปลี่ยนระบบ Jarvis เดิมให้กลายเป็นระบบของมายแบบจริง ไม่ใช่ mockup และไม่ใช่แค่ re-skin ผิวหน้า

เป้าหมายสุดท้ายคือระบบเดียวชื่อ `MayAss` / `Maymint` ที่มีหน้าตาและ runtime แบบ Jarvis แต่สมอง ความจำ ตัวตน เครื่องมือ และการตัดสินใจเป็น Hermes/Maymint ทั้งหมด

Jarvis เดิมจะเหลือเป็น shell/runtime เท่านั้น:

- UI cinematic/HUD
- browser/mobile surface
- websocket/status bridge
- voice runtime
- overlay
- local app launcher
- optional remote tunnel ในอนาคต

Maymint/Hermes จะเป็นแกนหลัก:

- identity/persona
- brain/reasoning
- memory/profile
- tools/action execution
- skills
- safety confirmation
- voice style
- long-running work mode

## 1. Decisions confirmed by Boss

### 1. Identity / ตัวตน

ยืนยัน: ลบ persona `J.A.R.V.I.S.` ออก แล้วแทนด้วย `Maymint / มาย / MayAss`

ต้องเปลี่ยน:

- ชื่อระบบใน UI
- greeting
- labels
- system prompt
- spoken text
- voice style
- memory/profile wording
- dashboard wording
- overlay wording
- remote/mobile wording เมื่อเปิดใช้ภายหลัง

### 2. Brain / สมอง

ยืนยัน: คำสั่งทั้งหมดต้องวิ่งเข้า Hermes/Maymint เป็นหลัก ไม่ใช่ Jarvis brain เดิม

เส้นทางที่ต้องเป็นจริง:

```text
Jarvis UI / mic / overlay / mobile
→ MayAss brain adapter
→ Hermes/Maymint
→ response/action result
→ Jarvis UI/voice/overlay display
```

หมายเหตุสำคัญจากบอส: ต้องทำภายในระบบ Jarvis เดิม หน้าเดียวกัน ระบบเดียวกัน ไม่ใช่แยกเว็บใหม่มั่ว ๆ

### 3. Tools / เครื่องมือ

ยืนยัน: ใช้ tools ของ Hermes เป็นหลัก ไม่ใช่สร้าง tool ใหม่ซ้ำใน Jarvis

หลักการ:

- Jarvis ไม่ควรมี tool brain เป็นเจ้าของอีกต่อไป
- Jarvis เป็น UI/runtime bridge
- Hermes เป็นผู้ถือสิทธิ์และเครื่องมือจริง
- ถ้า Jarvis มี tool ที่ดี ให้แปลงเป็น bridge/MCP/plugin ให้ Hermes ใช้ ไม่ให้ Jarvis ตัดสินใจเอง

### 4. Memory / ความจำ

ยืนยัน: ใช้ memory ของ Maymint/Hermes เป็นหลัก เพราะระบบนี้ต้องเป็นมายจริง

Jarvis memory เดิมควร:

- ไม่ใช้เป็น memory หลัก
- อาจ archive ไว้
- อาจ import เฉพาะข้อมูลที่บอสยืนยันว่ามีประโยชน์
- ห้ามให้ข้อมูลเก่าอย่าง `sir`, `Forney`, persona Jarvis, หรือ facts ผิด ๆ มาปนกับ Maymint

### 5. UI / UX

ยืนยัน: เก็บ UX/UI แบบ Jarvis ไว้ แต่เปลี่ยนหลังบ้านให้เป็น Maymint/Hermes

ต้องคง:

- cinematic HUD
- dashboard feel
- voice/overlay layout
- system status
- remote/mobile-ready architecture

ต้องเปลี่ยน:

- branding จาก J.A.R.V.I.S. เป็น MayAss/Maymint
- flow ให้เป็น Maymint workspace
- backend brain เป็น Hermes
- wording และ state ทั้งหมดให้ truthful ตาม Maymint

### 6. Voice

ยืนยัน: เสียงต้องเป็นมาย 100%

ต้องมี 2 mode:

1. Realtime talk mode
   - คุยเร็ว
   - คิดเร็ว
   - ตอบเร็ว
   - แต่ห้ามมั่ว ต้องคุณภาพพอใช้จริง
   - เหมาะกับคุยเล่น สั่งง่าย ถามสั้น

2. Work mode / real task mode
   - ยอมคิดนานกว่า
   - สร้างเสียงนานกว่าได้
   - ใช้สำหรับงานจริง วิเคราะห์ เขียนโค้ด สรุป วางแผน ทำ action
   - ต้องมีสถานะกำลังคิด/ทำงานชัดเจน

ต้องแก้ก่อนใช้งานจริง:

- เสียงซ้ำ 2 รอบ
- macOS say + browser audio ทำงานพร้อมกัน
- mic feedback loop
- multiple websocket clients wants_audio=true พร้อมกัน

### 7. Remote access

ยืนยัน: ยังไม่ต้องเปิด remote/tunnel ตอนนี้

สถานะที่ต้องทำตอนนี้:

- ปิด Cloudflare quick tunnel
- เก็บ capability ไว้ใน code/config เป็น feature ที่เปิดภายหลังได้
- ยังไม่ต้องเปิดให้เข้าได้จากนอกเครื่อง
- เมื่อเปิดในอนาคต ต้องมี PIN/login/session protection

### 8. Safety

ยืนยัน: ให้สิทธิ์ Maymint ทุกอย่าง แต่ action สำคัญต้องมี confirmation popup

ต้องมีตัวเลือกใน popup:

- ยืนยันครั้งนี้
- ยืนยันถาวร / ไม่ต้องถามอีกสำหรับ action type นี้
- ไม่ยืนยัน / ยกเลิก

ต้องมีข้อมูลประกอบการตัดสินใจ:

- Maymint กำลังจะทำอะไร
- ไฟล์/แอป/บัญชี/เว็บ/คำสั่งไหนได้รับผล
- risk level
- reversible หรือ irreversible
- เหตุผลที่ Maymint แนะนำให้ทำ
- consequence ถ้าไม่ทำ

### 9. Strategy

ยืนยัน: ทำจริงใน repo Jarvis นี้ ไม่ใช่แค่ mockup

ต้องมี:

- source audit
- adapter architecture
- test/smoke verification
- working local artifact
- rollback-safe edits
- แยก stage ก่อนเปิด full dangerous mode

### 10. Final result

ยืนยัน: ใช้แทน Jarvis เดิมไปเลย

ระบบสุดท้าย:

```text
Name: MayAss / Maymint
UI: Jarvis-style cinematic HUD
Brain: Hermes/Maymint
Memory: Maymint/Hermes memory
Tools: Hermes tools
Voice: Maymint voice/style
Overlay: Jarvis overlay adapted to Maymint
Remote: optional, off by default until Boss asks
```

## 2. Current live state at planning time

- Jarvis local UI ยังเปิดอยู่ที่ `http://127.0.0.1:3001`
- Jarvis backend ยังเปิดอยู่ที่ `127.0.0.1:8741`
- Cloudflare quick tunnel ถูกปิดแล้วตาม decision ข้อ 7
- Full voice mode เคยเปิดจริงและพบปัญหา:
  - macOS say พูดพร้อม browser audio
  - mic feedback loop
  - wake/follow-up activation จากเสียงรอบข้าง
  - Jarvis memory/persona เก่าโผล่ เช่นข้อมูลที่ไม่ใช่ Maymint
- จึงต้องทำ migration แบบมี gates ไม่ใช่เปิด full ต่อทันทีแล้วแก้ไปเรื่อย ๆ

## 3. Target architecture

```text
[Browser / Mobile / Overlay / Voice]
        ↓
[Jarvis UI Shell]
- cinematic view
- dashboard/status
- chat input
- voice button/status
- confirmation popup
- websocket display
        ↓
[MayAss Runtime Bridge]
- auth/session context
- transcript normalization
- mode selector: realtime/work
- audio owner control
- confirmation policy
        ↓
[Hermes/Maymint Brain]
- persona Maymint
- memory/profile
- skills
- tools
- Oracle/context
- action planning
        ↓
[Hermes Tool Execution]
- file/search/terminal/browser/etc.
- dangerous action confirmation
        ↓
[Result Renderer]
- text
- voice
- UI event timeline
- action/result cards
```

## 4. Non-negotiable invariants

1. UI ของ Jarvis อยู่ได้ แต่สมองต้องเป็น Hermes/Maymint
2. ไม่มี persona J.A.R.V.I.S. โผล่ใน user-facing flow
3. ไม่มี memory/facts เก่าที่ทำให้มายกลายเป็น Jarvis
4. Tools ต้องเป็น Hermes-owned ไม่ใช่ Jarvis brain-owned
5. Remote tunnel ปิด by default
6. Voice ต้องมี audio owner เดียวต่อ turn
7. งานเสี่ยงต้องมี popup confirmation
8. ไม่มี fake success: ถ้ายังไม่ต่อ Hermes จริง ต้องบอกว่าเป็น stub/bridge pending
9. ทุก gate ต้องมี verification จริง
10. เก็บของเดิมไว้ rollback ได้ ห้ามลบทิ้งมั่ว ๆ

## 5. Implementation phases

### Phase A — Freeze and baseline

เป้าหมาย: รู้สถานะเดิมก่อนแก้

Tasks:

- ตรวจ git status / branch
- archive current run commands
- kill remote tunnel ถ้ามี
- เลือก mode ปลอดภัยสำหรับ dev: server mode ก่อน full voice
- ตรวจ ports `3001`, `8741`
- run targeted tests ด้วย Python 3.11
- smoke local UI/backend

Verification:

```bash
cd '/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi'
.venv/bin/python -m pytest -q
curl -sS http://127.0.0.1:8741/health/ping
curl -sS http://127.0.0.1:8741/auth/status
```

### Phase B — Identity replacement

เป้าหมาย: user-facing Jarvis กลายเป็น MayAss/Maymint

Tasks:

- search all user-facing strings:
  - JARVIS
  - J.A.R.V.I.S.
  - Just A Rather Very Intelligent System
  - sir
  - Remote Access PIN wording
  - Jarvis online
- เปลี่ยนเฉพาะ user-facing labels ก่อน
- อย่าเปลี่ยน internal class/module names ถ้ายังเสี่ยงทำให้ code พัง
- สร้าง compatibility aliases ถ้าจำเป็น

Verification:

- frontend compile ผ่าน
- browser console 0 errors
- screenshot/DOM ไม่มี JARVIS ใน visible UI ยกเว้น internal debug ที่ซ่อนไว้

### Phase C — Hermes brain adapter

เป้าหมาย: Jarvis chat/voice ส่งคำสั่งเข้า Hermes/Maymint

Adapter options:

1. Subprocess adapter ระยะแรก:

```bash
hermes chat -Q -q '<prompt>'
```

ข้อดี: ใช้ Hermes จริงเร็วสุด ไม่ต้องเขียน tool ใหม่เยอะ
ข้อเสีย: latency มากกว่า, session continuity ต้องออกแบบ

2. Hermes local API/proxy/gateway adapter ระยะถัดไป

ข้อดี: streaming/session/tool integration ดีกว่า
ข้อเสีย: ต้อง setup endpoint และ auth ชัด

Recommended path:

- เริ่มจาก subprocess adapter เพื่อพิสูจน์ real brain
- จากนั้นค่อย refactor เป็น persistent Hermes service/session bridge

Bridge contract:

```json
{
  "source": "mayass_ui|mayass_voice|mayass_overlay",
  "mode": "realtime|work",
  "text": "...",
  "session_id": "...",
  "needs_voice": true,
  "tool_policy": "hermes_default_with_confirmation"
}
```

### Phase D — Hermes tools ownership

เป้าหมาย: action/tool execution เป็นของ Hermes

Tasks:

- map Jarvis tools → Hermes native equivalent
- disable Jarvis autonomous tool execution where possible
- expose only UI/action requests to Hermes
- build action result cards in Jarvis UI

Examples:

- file read/write → Hermes file tools
- shell → Hermes terminal tool with approval rules
- browser → Hermes browser tools or Jarvis browser automation only as renderer/bridge
- memory → Hermes memory/session/oracle
- calendar/notes → Hermes skills/tools if configured

### Phase E — Confirmation popup

เป้าหมาย: สิทธิ์เต็ม แต่ action สำคัญต้องกดเลือก

Popup states:

```text
pending_confirmation
confirmed_once
confirmed_always
denied
expired
```

UI buttons:

- ยืนยันครั้งนี้
- ยืนยันถาวรสำหรับงานแบบนี้
- ยกเลิก

Confirmation payload:

```json
{
  "action_id": "...",
  "action_type": "shell|file_write|delete|message|remote|config|account",
  "summary_th": "มายกำลังจะ...",
  "risk_level": "low|medium|high|critical",
  "affected_targets": ["..."],
  "reversible": true,
  "reason": "...",
  "choices": ["confirm_once", "confirm_always", "deny"]
}
```

### Phase F — Voice modes

เป้าหมาย: มี 2 mode ตามที่บอสต้องการ

Realtime mode:

- low latency
- shorter prompts
- no heavy tools unless user explicitly asks
- fast model/provider where possible
- TTS fast
- answer concise but grounded

Work mode:

- full Hermes reasoning/tools
- can take longer
- status timeline visible
- TTS after final/important chunks
- confirmation for risky actions

ต้องแก้ audio routing:

- choose one audio owner:
  - browser only หรือ macOS say only
- prevent duplicate clients wants_audio=true
- pause mic during playback
- no follow-up capture while speaking

### Phase G — Remote as optional feature

เป้าหมาย: remote off by default แต่เปิดได้เมื่อบอสสั่ง

Tasks:

- config flag: `MAYASS_REMOTE_ENABLED=false`
- named tunnel recommended for persistent URL
- quick tunnel only for temporary testing
- login/PIN required
- session expiry
- audit log remote actions

### Phase H — MayAss final hardening

เป้าหมาย: ใช้แทน Jarvis เดิมได้จริง

Checklist:

- UI name MayAss/Maymint everywhere
- Hermes brain adapter green
- Maymint memory active
- Jarvis brain disabled or bypassed
- Hermes tools active
- confirmation popup works
- voice realtime/work modes work
- audio duplicate fixed
- remote off by default
- full local smoke pass
- docs/runbook written

## 6. Proposed first implementation slice

ควรเริ่มจาก slice เล็กที่พิสูจน์แกนจริง:

`Jarvis Chat UI → Hermes/Maymint response → Jarvis UI render`

ไม่เริ่มจาก voice/full เพราะจะซับซ้อนจาก mic/audio/feedback loop

Steps:

1. Add MayAss config flag
2. Add Hermes subprocess adapter
3. Replace chat route brain call with adapter in MayAss mode
4. Keep fallback to Jarvis brain behind flag
5. Change UI identity to MayAss/Maymint
6. Smoke chat in browser
7. Then wire voice transcript to the same adapter

## 7. Open confirmations still needed

1. ชื่อ final สะกดว่า `MayAss` แน่นอนใช่ไหม หรือให้ใช้ `Maymint` เป็นชื่อหลักแล้ว `MayAss` เป็น codename?
2. Realtime mode จะใช้ model/provider ไหน:
   - local Ollama fast
   - Hermes current provider
   - Gemini/Vertex/OpenRouter
3. Work mode จะใช้ Hermes default current profile ใช่ไหม?
4. Popup confirmation ให้จำถาวรเก็บไว้ที่ไหน:
   - config file ใน repo
   - Hermes memory/config
   - MayAss policy database
5. จะให้ Jarvis memory เดิม archive อย่างเดียว หรืออ่านเพื่อ migrate เฉพาะ facts ที่บอส approve?

## 8. Immediate safety note

เพราะบอสเคยเปิด full risk mode และ remote tunnel มาแล้ว:

- remote tunnel ปิดแล้วตาม decision ล่าสุด
- local UI/backend ยังรันอยู่
- ถ้าจะเริ่ม implementation จริง ควรเปลี่ยนกลับเป็น server/dev mode ก่อนแก้ code เพื่อลด mic feedback และ side effects

## 9. Definition of done

ระบบจะนับว่าเริ่มเป็น MayAss จริงเมื่อ:

1. User-facing UI เรียกตัวเองว่า MayAss/Maymint
2. Chat จาก UI ถูกตอบโดย Hermes/Maymint จริง
3. Memory/persona เป็นของ Maymint
4. Jarvis brain เดิมไม่ใช่ decision maker หลัก
5. Tools/action มาจาก Hermes หรือผ่าน Hermes approval
6. มี confirmation popup สำหรับ risky actions
7. Voice ไม่ซ้ำและไม่ feedback loop
8. Remote ปิด default และเปิดได้เมื่อบอสสั่งเท่านั้น

