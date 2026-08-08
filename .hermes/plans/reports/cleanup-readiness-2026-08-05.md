# Cleanup Readiness Report — MayAss/Jarvis workspace

วันที่: 2026-08-05
โหมด: เคลียร์งานเก่าก่อนเริ่มงาน MayAss implementation

## สรุปสถานะ

- Repo: `/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi`
- Branch: `main`
- Quick verification: `17 passed in 1.49s`
- Cloudflare remote tunnel: ไม่พบ `cloudflared`
- Local Jarvis UI/backend: ยังเปิดอยู่
  - UI port 3001: `node` / Next.js
  - Backend port 8741: `python3.11`
- Static HTML server port 8799: ไม่พบ listener

## สิ่งที่ค้างอยู่ใน workspace

### A. ควรเก็บไว้สำหรับงาน MayAss ต่อ

- `.hermes/plans/2026-08-05_0710-mayass-master-workplan-phase-isolated-v2.md`
  - แผน phase-isolated ตัวหลัก
- `MAYASS_PHASE_ISOLATED_MASTER_PLAN_PRESENTATION_2026-08-05.html`
  - HTML presentation ให้บอสเปิดดูภาพรวม
- `MAYASS_HERMES_OVER_JARVIS_MASTER_PLAN_2026-08-05.md`
  - แผนเก่า ใช้เป็น history/reference

### B. รายงาน/HTML เก่าที่ควร archive ไม่ควรลบทิ้งทันที

- `Jarvis-Reverse-Engineering-Report.html`
- `Jarvis_UI_Original_Mock_Showcase.html`
- `รายงานฉบับเต็ม-แผนพัฒนา-Maymint-Voice-Assistant-ก่อน.html`
- `รายงานชำแหละ-Jarvis-สำหรับ-Maymint-Hermes.html`
- `รายงานสกัด-UI-ที่ต้องใช้พัฒนา-Maymint.html`
- `รายงานเจาะลึก-3ฟังก์ชัน-Jarvis-สู่-Maymint.html`
- `รายงานแบบเด็กๆ-Maymint-ควรเพิ่มอะไร.html`

ข้อเสนอ: ย้ายไป `.hermes/archive/reports/2026-08-05/` เพื่อให้ root repo สะอาด แต่ยังไม่ลบ

### C. ไฟล์เปลี่ยนแปลงที่ต้อง review ก่อนทำงานใหม่

- `jarvis/ui/jarvis-ui/package-lock.json`
  - สถานะ: modified
  - ต้องตรวจ diff ก่อนตัดสินใจว่าจะ keep หรือ revert

### D. Process ที่ควรตัดสินใจก่อนเริ่ม implementation

พบ local Jarvis full/server processes:

- `bash ./start.sh full`
- `npm run dev --hostname 0.0.0.0 --port 3001`
- `next-server` listening on port 3001
- backend Python listening on port 8741

ข้อเสนอสำหรับช่วงเคลียร์:

1. ถ้าบอสไม่ได้ใช้งาน UI อยู่ตอนนี้ → stop local Jarvis runtime เพื่อให้พื้นที่สะอาด
2. ถ้าบอสอยากเปิดดู UI ไปด้วย → คงไว้ แต่ห้ามถือว่าเป็น clean baseline

## Cleanup plan ที่ปลอดภัย

### Step 1 — หยุด runtime เก่าถ้าบอสอนุมัติ

- stop `start.sh full` และ process ลูกที่เปิด 3001/8741
- verify ports 3001/8741 ปิด

### Step 2 — Archive reports เก่า

- create `.hermes/archive/reports/2026-08-05/`
- move รายงานเก่าที่ไม่ใช่แผน active ไปเก็บ
- keep active plan/html ที่ root หรือย้ายตามที่บอสชอบ

### Step 3 — Review `package-lock.json`

- ดู diff
- ถ้าเกิดจาก `npm install` dependency setup จริง → keep ไว้ก่อน
- ถ้าเป็น noise → revert

### Step 4 — Final clean baseline

- `git status --short`
- `.venv/bin/python -m pytest -q`
- บันทึกผลใน report ใหม่

## ห้ามทำโดยไม่ถามบอสก่อน

- ห้ามลบรายงานเก่าแบบถาวร
- ห้าม revert `package-lock.json` ก่อนดู diff
- ห้าม kill runtime ถ้าบอสกำลังใช้งาน UI อยู่
- ห้ามเปิด remote tunnel

## สถานะตอนนี้

พร้อมสำหรับการเคลียร์ แต่ยังไม่ได้ลบ/ย้าย/kill runtime ใด ๆ จากรายงานนี้
