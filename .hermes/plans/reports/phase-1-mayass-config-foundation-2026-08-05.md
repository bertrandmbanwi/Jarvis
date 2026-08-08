# Phase 1 Report — MayAss Config Foundation

วันที่: 2026-08-05
Repo: `/Users/meuu/Desktop/โปรเจ็ค hermes/Jarvis-bertrandmbanwi`
Phase: `1 — MayAss Config Foundation`
Status: `PASS`

## Goal

สร้างสวิตช์ config สำหรับ MayAss ให้ rollback-safe ก่อนแตะ UI, voice, chat routing หรือ Hermes bridge

## Allowed scope

แตะเฉพาะ:

```text
jarvis/config/settings.py
tests/test_mayass_settings.py
```

## Forbidden scope respected

ไม่ได้แตะ:

- UI
- voice
- chat route
- dashboard/cinematic
- Hermes bridge
- remote tunnel

## TDD Evidence

### RED

สร้าง test ก่อนใน:

```text
tests/test_mayass_settings.py
```

รัน targeted test ก่อนแก้ production code:

```bash
.venv/bin/python -m pytest tests/test_mayass_settings.py -q
```

ผล RED:

```text
4 failed
AttributeError: module 'jarvis.config.settings' has no attribute 'MAYASS_ENABLED'
AttributeError: module 'jarvis.config.settings' has no attribute 'MAYASS_DISPLAY_NAME'
AttributeError: module 'jarvis.config.settings' has no attribute 'MAYASS_DEFAULT_MODE'
```

แปลว่า test fail เพราะ feature ยังไม่มีจริง ถูกต้องตาม TDD

### GREEN

เพิ่ม config flags ใน:

```text
jarvis/config/settings.py
```

เพิ่ม:

```text
MAYASS_ENABLED
MAYASS_DISPLAY_NAME
MAYASS_CODENAME
MAYASS_REMOTE_ENABLED
MAYASS_DEFAULT_MODE
MAYASS_AUDIO_OWNER
MAYASS_HERMES_COMMAND
MAYASS_HERMES_PROFILE
```

เพิ่ม helper เฉพาะ settings:

```text
_env_bool
_env_choice
```

## Verification

### 1. Targeted Phase 1 test

Command:

```bash
.venv/bin/python -m pytest tests/test_mayass_settings.py -q
```

Result:

```text
4 passed in 0.06s
```

Status: `PASS`

### 2. Real env smoke

Command:

```bash
MAYASS_ENABLED=true MAYASS_REMOTE_ENABLED=false MAYASS_AUDIO_OWNER=browser MAYASS_DEFAULT_MODE=work .venv/bin/python - <<'PY'
from jarvis.config import settings
print(f'MAYASS_ENABLED={settings.MAYASS_ENABLED}')
print(f'MAYASS_REMOTE_ENABLED={settings.MAYASS_REMOTE_ENABLED}')
print(f'MAYASS_AUDIO_OWNER={settings.MAYASS_AUDIO_OWNER}')
print(f'MAYASS_DEFAULT_MODE={settings.MAYASS_DEFAULT_MODE}')
print(f'MAYASS_DISPLAY_NAME={settings.MAYASS_DISPLAY_NAME}')
print(f'MAYASS_CODENAME={settings.MAYASS_CODENAME}')
print(f'MAYASS_HERMES_COMMAND={settings.MAYASS_HERMES_COMMAND}')
print(f'MAYASS_HERMES_PROFILE={settings.MAYASS_HERMES_PROFILE}')
PY
```

Result:

```text
MAYASS_ENABLED=True
MAYASS_REMOTE_ENABLED=False
MAYASS_AUDIO_OWNER=browser
MAYASS_DEFAULT_MODE=work
MAYASS_DISPLAY_NAME=MayAss
MAYASS_CODENAME=Maymint-Hermes
MAYASS_HERMES_COMMAND=hermes chat -Q
MAYASS_HERMES_PROFILE=default
```

Status: `PASS`

### 3. Invalid value fallback smoke

Command:

```bash
MAYASS_DEFAULT_MODE=bad MAYASS_AUDIO_OWNER=bad .venv/bin/python - <<'PY'
from jarvis.config import settings
print(f'MAYASS_DEFAULT_MODE={settings.MAYASS_DEFAULT_MODE}')
print(f'MAYASS_AUDIO_OWNER={settings.MAYASS_AUDIO_OWNER}')
PY
```

Result:

```text
MAYASS_DEFAULT_MODE=realtime
MAYASS_AUDIO_OWNER=browser
```

Status: `PASS`

### 4. Full regression

Command:

```bash
.venv/bin/python -m pytest -q
```

Result:

```text
394 passed, 1 skipped in 6.99s
```

Status: `PASS`

### 5. Runtime safety check

Checked:

```bash
pgrep -fl cloudflared || true
curl -sS -m 5 http://127.0.0.1:8741/health/ping || true
```

Result:

```text
no cloudflared process
{"status":"ok"}
```

Status: `PASS`

## Bugs found

ไม่พบบัคใน Phase 1

## Known inherited issues not fixed in this Phase

- UI ยังขึ้นชื่อ J.A.R.V.I.S. อยู่ เพราะ Phase 1 ห้ามแตะ UI
- Chat ยังไม่ได้ route เข้า Hermes/Maymint เพราะเป็น Phase 4
- Voice/audio duplicate ยังไม่ได้แก้ เพราะเป็น Phase 8
- Jarvis memory/persona เก่ายังอยู่ใน settings prompt เดิม เพราะ memory quarantine เป็น Phase 5

## User-visible result

Phase 1 เห็นผลผ่าน terminal/config smoke ไม่ใช่ UI:

```text
MAYASS_ENABLED=True
MAYASS_REMOTE_ENABLED=False
MAYASS_AUDIO_OWNER=browser
MAYASS_DEFAULT_MODE=work
```

UI ยังไม่เปลี่ยนตามแผน เพราะ Phase 1 เป็น config foundation เท่านั้น

## Rollback

Rollback ได้โดยตั้ง:

```bash
MAYASS_ENABLED=false
```

หรือ revert เฉพาะไฟล์:

```text
jarvis/config/settings.py
tests/test_mayass_settings.py
```

## Phase 1 Done Criteria

- [x] tests pass
- [x] env flags read correctly
- [x] default remote off
- [x] invalid mode/audio owner fallback safe
- [x] full pytest pass
- [x] no remote tunnel opened
- [x] phase report written

## Final status

`Phase 1 — MayAss Config Foundation`: PASS

พร้อมไป Phase 2 — MayAss Identity Layer เมื่อบอสอนุมัติ
