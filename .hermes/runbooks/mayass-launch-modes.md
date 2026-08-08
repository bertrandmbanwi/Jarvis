# MayAss Launch Modes

Phase 10 runbook: keep remote off by default and make the operator launch modes explicit.

## Safe defaults

These should remain false unless the operator explicitly turns them on:

```bash
MAYASS_REMOTE_ENABLED=false
JARVIS_ENABLE_TUNNEL=false
```

## Launch profiles

### `mayass-server-safe`

Safe text/server baseline with remote off. Use this when you want the lowest-risk local run.

```bash
MAYASS_ENABLED=true MAYASS_REMOTE_ENABLED=false JARVIS_ENABLE_TUNNEL=false JARVIS_OPEN_DASHBOARD=false ./start.sh server
```

### `mayass-voice-browser`

Browser voice mode. Uses the browser as the audio owner; remote remains off.

```bash
MAYASS_ENABLED=true MAYASS_REMOTE_ENABLED=false JARVIS_ENABLE_TUNNEL=false MAYASS_AUDIO_OWNER=browser ./start.sh full
```

### `mayass-work`

Work/chat routing mode for Maymint-Hermes tasks. Remote remains off.

```bash
MAYASS_ENABLED=true MAYASS_REMOTE_ENABLED=false JARVIS_ENABLE_TUNNEL=false MAYASS_DEFAULT_MODE=work ./start.sh server
```

### `mayass-remote`

Explicit operator-only remote mode. Turn this on only when you want phone access.

```bash
MAYASS_ENABLED=true MAYASS_REMOTE_ENABLED=true JARVIS_ENABLE_TUNNEL=true JARVIS_PIN_AUTH_ENABLED=true ./start.sh full
```

## Safety note

Remote remains off by default. If the tunnel is enabled, the script should require PIN auth and print the tunnel URL only after startup.

## Quick checks

```bash
MAYASS_ENABLED=true MAYASS_REMOTE_ENABLED=false JARVIS_ENABLE_TUNNEL=false ./start.sh full
pgrep -fl cloudflared || true
```

Expected: remote remains off and no cloudflared process starts.

## Operator guide

### How to open

Pick one launch profile and run it from the repo root. For normal local work, use `mayass-work`. For browser voice, use `mayass-voice-browser`. Do not enable remote for local-only use.

### How to stop

Press `Ctrl+C` in the terminal that launched `./start.sh`. The script traps shutdown and stops the API/UI child processes it started.

### Browser voice / push-to-talk

Use the Voice tab in the browser. Start with push-to-talk rather than always-on listening when testing a new room, mic, or speaker setup.

### Remote access

Remote is optional and off by default. Do not enable remote unless Boss explicitly wants phone access for that session. Remote mode must include `MAYASS_REMOTE_ENABLED=true`, `JARVIS_ENABLE_TUNNEL=true`, and PIN auth.

### Duplicate audio troubleshooting

If duplicate audio or feedback starts, stop voice input first, then relaunch with one audio owner only. Prefer browser voice with `MAYASS_AUDIO_OWNER=browser`; use `MAYASS_AUDIO_OWNER=none` for silent/text-only checks.
