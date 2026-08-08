# Phase 1 Deep Bug Hunt / Consistency Report — Corrected

วันที่: 2026-08-05
Repo: `/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi`
Phase: `1 — MayAss Config Foundation`
Status: `PASS`

> Note: artifact รอบ `phase-1-deep-consistency-20260805T113716.*` ใช้ helper runner ผิด ทำให้ command checks เป็น `exit_code=-1` และ overall false ทั้งที่ไม่มี issue จากโค้ดจริง รายงาน corrected นี้ใช้คำสั่งจริงผ่าน terminal โดยตรง

## Goal

เทส Phase 1 แบบละเอียดเพื่อหา:

- บัคใน config flags
- edge cases ของ env values
- ความไม่สอดคล้องกับ master plan
- side effect นอก scope
- remote/tunnel ที่ไม่ควรเปิด
- regression ของ test suite เดิม

## Scope ที่ตรวจ

Phase 1 อนุญาตให้แตะเฉพาะ:

```text
jarvis/config/settings.py
tests/test_mayass_settings.py
```

## 1. Targeted pytest

Command:

```bash
.venv/bin/python -m pytest tests/test_mayass_settings.py -q
```

Result:

```text
....                                                                     [100%]
4 passed in 0.06s
```

Status: `PASS`

## 2. Full regression pytest

Command:

```bash
.venv/bin/python -m pytest -q
```

Result:

```text
s....................................................................... [ 18%]
........................................................................ [ 36%]
........................................................................ [ 54%]
........................................................................ [ 72%]
........................................................................ [ 91%]
...................................                                      [100%]
394 passed, 1 skipped in 6.83s
```

Status: `PASS`

## 3. Python compile check

Command:

```bash
.venv/bin/python -m py_compile jarvis/config/settings.py tests/test_mayass_settings.py
```

Result: exit code `0`

Status: `PASS`

## 4. Env matrix edge cases

Command: isolated Python subprocesses with env overrides

Results:

```text
defaults: False|False|realtime|browser|MayAss|Maymint-Hermes|hermes chat -Q|default
true_values: True|True|realtime|browser|MayAss|Maymint-Hermes|hermes chat -Q|default
yes_on_values: True|True|realtime|browser|MayAss|Maymint-Hermes|hermes chat -Q|default
false_values: False|False|realtime|browser|MayAss|Maymint-Hermes|hermes chat -Q|default
work_macos: False|False|work|macos|MayAss|Maymint-Hermes|hermes chat -Q|default
none_audio: False|False|realtime|none|MayAss|Maymint-Hermes|hermes chat -Q|default
invalid_fallback: False|False|realtime|browser|MayAss|Maymint-Hermes|hermes chat -Q|default
whitespace_string_fallback: False|False|realtime|browser|MayAss|Maymint-Hermes|hermes chat -Q|default
```

Interpretation:

- default safe
- bool true variants work
- false/0 remain false
- `work` mode accepted
- `macos`/`none` audio owner accepted
- invalid mode/audio owner fallback to safe defaults
- blank display/codename/command/profile fallback to defaults

Status: `PASS`

## 5. Scope consistency check

Search result for `MAYASS_`:

```text
jarvis/config/settings.py
tests/test_mayass_settings.py
```

Interpretation:

- MayAss Phase 1 config did not leak into UI, voice, chat route, dashboard, or Hermes bridge
- This matches Phase 1 forbidden scope

Status: `PASS`

## 6. Git / changed files check

Relevant output:

```text
M jarvis/config/settings.py
?? .hermes/
?? tests/test_mayass_settings.py
```

Interpretation:

- production code changed only in `jarvis/config/settings.py`
- test added only in `tests/test_mayass_settings.py`
- `.hermes/` contains plans/reports/artifacts
- no UI/voice/chat files modified

Status: `PASS`

## 7. Remote / tunnel safety check

Command:

```bash
pgrep -fl cloudflared || true
```

Result:

```text
no output
```

Interpretation:

- no cloudflared process
- remote tunnel remains off

Status: `PASS`

## 8. Runtime side-effect check

Current local server state:

```text
UI local: port 3001 LISTEN
Backend local: port 8741 LISTEN
Remote/cloudflared: OFF
```

Interpretation:

- local UI/backend were already opened for baseline viewing
- Phase 1 did not open remote or full voice

Status: `PASS`

## Bugs found in Phase 1 scope

ไม่พบบัคใน Phase 1 scope จาก deep bug hunt รอบนี้

## Inconsistencies / not-yet-fixed observations

สิ่งเหล่านี้ดูเหมือน “ยังไม่เป็น MayAss เต็ม” แต่ไม่ใช่บัคของ Phase 1 เพราะ master plan ตั้งใจให้ทำใน phase ถัดไป:

1. UI ยังแสดง `J.A.R.V.I.S.`
   - เหตุผล: Phase 1 ห้ามแตะ UI
   - Phase ที่เกี่ยวข้อง: Phase 2 / Phase 9

2. live server process ที่เปิดอยู่เริ่มก่อนเพิ่ม MayAss env flags
   - เหตุผล: Phase 1 verify import-time config ผ่าน fresh Python processes แล้ว
   - ถ้าต้องดู config ใน server จริง ควร restart ใน phase ที่ route/config runtime ต้องใช้จริง

3. `MAYASS_REMOTE_ENABLED` ยังไม่ผูกกับ `start.sh`
   - เหตุผล: Phase 1 คือ config foundation ใน Python settings
   - `start.sh` remote hardening อยู่ Phase 10
   - ตอนนี้ remote จริงยังปิดผ่าน `JARVIS_ENABLE_TUNNEL=false` และไม่มี cloudflared

4. system prompt เดิมยังมี JARVIS/Becs/sir/Forney
   - เหตุผล: memory/persona quarantine อยู่ Phase 5
   - Phase 1 ห้ามแก้ prompt/brain routing

## Reasonableness verdict

Phase 1 สมเหตุสมผลตาม master plan:

- เริ่มจาก config switch ก่อนแตะระบบใหญ่
- default ปลอดภัย: MayAss off, remote off, browser audio owner
- invalid values fallback อย่างปลอดภัย
- ไม่มี side effect ต่อ UI/voice/chat/remote
- rollback ได้ด้วย `MAYASS_ENABLED=false` หรือ revert เฉพาะสองไฟล์

## Final verdict

`Phase 1 — MayAss Config Foundation`: `PASS`

พร้อมข้ามไป `Phase 2 — MayAss Identity Layer` เมื่อบอสอนุมัติ
