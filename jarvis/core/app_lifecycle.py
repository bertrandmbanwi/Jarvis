"""JARVIS app lifecycle diagnostics and macOS launcher controls."""
from __future__ import annotations

import json
import os
import platform
import plistlib
import subprocess  # nosec B404
import sys
import time
from pathlib import Path
from typing import Any

from jarvis.config import settings

LAUNCH_AGENT_LABEL = "com.jarvis.assistant"
RUNTIME_DIR = settings.DATA_DIR / "runtime"
RUNTIME_STATE_FILE = RUNTIME_DIR / "lifecycle.json"
LAUNCH_AGENT_FILENAME = f"{LAUNCH_AGENT_LABEL}.plist"
DEFAULT_LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
USER_APP_CANDIDATE = Path.home() / "Applications" / "JARVIS.app"
SYSTEM_APP_CANDIDATE = Path("/Applications/JARVIS.app")


def _now() -> float:
    return round(time.time(), 3)


def _path(value: str | Path | None, default: Path) -> Path:
    return Path(value).expanduser().resolve() if value is not None else default


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _int_or_none(value: Any) -> int | None:
    try:
        pid = int(value)
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def _pid_is_running(pid: Any) -> bool:
    parsed = _int_or_none(pid)
    if parsed is None:
        return False
    try:
        os.kill(parsed, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _run_command(args: list[str], timeout: float = 3.0) -> dict[str, Any]:
    try:
        result = subprocess.run(  # nosec B603
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        return {"ok": False, "returncode": 127, "stdout": "", "stderr": str(exc)}
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "returncode": 124, "stdout": exc.stdout or "", "stderr": "Command timed out."}

    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _launchctl_path() -> str:
    return "/bin/launchctl"


def _launchctl_available() -> bool:
    return platform.system() == "Darwin" and Path(_launchctl_path()).exists()


def _launch_agent_target() -> str:
    return f"gui/{os.getuid()}/{LAUNCH_AGENT_LABEL}"


def _launch_agent_domain() -> str:
    return f"gui/{os.getuid()}"


def _process_summary(name: str, pid: Any) -> dict[str, Any]:
    parsed = _int_or_none(pid)
    return {"name": name, "pid": parsed, "running": _pid_is_running(parsed)}


def _runtime_processes(runtime_state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "launcher": _process_summary("launcher", runtime_state.get("parent_pid")),
        "backend": _process_summary("backend", os.getpid()),
        "ui": _process_summary("ui", runtime_state.get("ui_pid")),
        "nextjs": _process_summary("nextjs", runtime_state.get("nextjs_pid")),
        "proxy": _process_summary("proxy", runtime_state.get("proxy_pid")),
        "overlay": _process_summary("overlay", runtime_state.get("overlay_pid")),
        "tunnel": _process_summary("tunnel", runtime_state.get("tunnel_pid")),
        "ollama": _process_summary("ollama", runtime_state.get("ollama_pid")),
    }


def _installed_app_candidates(jarvis_home: Path) -> list[dict[str, Any]]:
    candidates = [
        ("user", USER_APP_CANDIDATE),
        ("system", SYSTEM_APP_CANDIDATE),
        ("dist", jarvis_home / "dist" / "JARVIS.app"),
    ]
    return [{"scope": scope, "path": str(path), "installed": path.exists()} for scope, path in candidates]


def _launch_agent_status(plist_path: Path, probe_launchctl: bool) -> dict[str, Any]:
    loaded = False
    launchctl: dict[str, Any] = {"available": _launchctl_available(), "checked": False}
    if probe_launchctl and _launchctl_available():
        result = _run_command([_launchctl_path(), "print", _launch_agent_target()])
        launchctl.update(result)
        launchctl["checked"] = True
        loaded = bool(result.get("ok"))

    return {
        "label": LAUNCH_AGENT_LABEL,
        "path": str(plist_path),
        "installed": plist_path.exists(),
        "loaded": loaded,
        "launchctl": launchctl,
    }


def render_launch_agent_plist(jarvis_home: str | Path | None = None) -> bytes:
    """Render a launchd plist for the current checkout without hardcoded paths."""
    home = _path(jarvis_home, settings.JARVIS_HOME)
    log_dir = home / "data" / "logs"
    plist = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": ["/bin/bash", str(home / "start.sh"), "full"],
        "WorkingDirectory": str(home),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 10,
        "StandardOutPath": str(log_dir / "launchd-stdout.log"),
        "StandardErrorPath": str(log_dir / "launchd-stderr.log"),
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(Path.home()),
            "JARVIS_HOME": str(home),
        },
        "ProcessType": "Standard",
    }
    return plistlib.dumps(plist, sort_keys=False)


def install_launch_agent(
    *,
    jarvis_home: str | Path | None = None,
    launch_agents_dir: str | Path | None = None,
    load: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Install or preview the user LaunchAgent plist."""
    home = _path(jarvis_home, settings.JARVIS_HOME)
    target_dir = _path(launch_agents_dir, DEFAULT_LAUNCH_AGENTS_DIR)
    plist_path = target_dir / LAUNCH_AGENT_FILENAME
    plist_bytes = render_launch_agent_plist(home)

    result: dict[str, Any] = {
        "status": "planned" if dry_run else "installed",
        "dry_run": dry_run,
        "path": str(plist_path),
        "jarvis_home": str(home),
        "load_requested": load,
        "launchctl": None,
    }

    if dry_run:
        result["plist"] = plist_bytes.decode("utf-8")
        return result

    target_dir.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(plist_bytes)

    if load and _launchctl_available():
        _run_command([_launchctl_path(), "bootout", _launch_agent_domain(), str(plist_path)])
        result["launchctl"] = _run_command([_launchctl_path(), "bootstrap", _launch_agent_domain(), str(plist_path)])

    return result


def uninstall_launch_agent(
    *,
    launch_agents_dir: str | Path | None = None,
    unload: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Uninstall or preview removal of the user LaunchAgent plist."""
    target_dir = _path(launch_agents_dir, DEFAULT_LAUNCH_AGENTS_DIR)
    plist_path = target_dir / LAUNCH_AGENT_FILENAME
    result: dict[str, Any] = {
        "status": "planned" if dry_run else "removed",
        "dry_run": dry_run,
        "path": str(plist_path),
        "existed": plist_path.exists(),
        "unload_requested": unload,
        "launchctl": None,
    }

    if dry_run:
        return result

    if unload and _launchctl_available():
        result["launchctl"] = _run_command([_launchctl_path(), "bootout", _launch_agent_domain(), str(plist_path)])
    if plist_path.exists():
        plist_path.unlink()
    return result


def write_runtime_state(
    *,
    status: str,
    mode: str,
    api_port: int | str,
    ui_port: int | str,
    runtime_file: str | Path | None = None,
    processes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a runtime state file for diagnostics."""
    path = _path(runtime_file, RUNTIME_STATE_FILE)
    previous = _read_json_file(path)
    payload: dict[str, Any] = {
        "status": status,
        "mode": mode,
        "api_port": int(api_port),
        "ui_port": int(ui_port),
        "jarvis_home": str(settings.JARVIS_HOME),
        "started_at": previous.get("started_at") if status != "starting" else _now(),
        "updated_at": _now(),
        "processes": processes or {},
    }
    if not payload["started_at"]:
        payload["started_at"] = _now()
    _write_json_file(path, payload)
    return payload


def get_status(
    *,
    jarvis_home: str | Path | None = None,
    runtime_file: str | Path | None = None,
    launch_agents_dir: str | Path | None = None,
    probe_launchctl: bool | None = None,
) -> dict[str, Any]:
    """Return a diagnostic snapshot for the app, wrapper script, and launch agent."""
    home = _path(jarvis_home, settings.JARVIS_HOME)
    runtime_path = _path(runtime_file, RUNTIME_STATE_FILE)
    target_dir = _path(launch_agents_dir, DEFAULT_LAUNCH_AGENTS_DIR)
    plist_path = target_dir / LAUNCH_AGENT_FILENAME
    runtime_state = _read_json_file(runtime_path)
    raw_processes = runtime_state.get("processes", {})
    runtime_processes = raw_processes if isinstance(raw_processes, dict) else {}

    launch_probe = platform.system() == "Darwin" if probe_launchctl is None else probe_launchctl
    process_snapshot = _runtime_processes(runtime_processes)
    launcher_running = bool(process_snapshot["launcher"]["running"])
    runtime_age_seconds = _now() - float(runtime_state.get("updated_at", 0) or 0) if runtime_state else None

    return {
        "status": "online",
        "platform": platform.system(),
        "is_macos": platform.system() == "Darwin",
        "jarvis_home": str(home),
        "paths": {
            "start_script": str(home / "start.sh"),
            "runtime_state": str(runtime_path),
            "logs_dir": str(home / "data" / "logs"),
        },
        "runtime": {
            "status": runtime_state.get("status", "unknown"),
            "mode": runtime_state.get("mode", os.getenv("JARVIS_LAUNCH_MODE", "")),
            "started_at": runtime_state.get("started_at"),
            "updated_at": runtime_state.get("updated_at"),
            "age_seconds": round(runtime_age_seconds, 1) if runtime_age_seconds is not None else None,
            "launcher_running": launcher_running,
            "state_file_exists": runtime_path.exists(),
        },
        "ports": {
            "api": int(runtime_state.get("api_port") or settings.API_PORT),
            "ui": int(runtime_state.get("ui_port") or settings.UI_PORT),
        },
        "processes": process_snapshot,
        "app_bundles": _installed_app_candidates(home),
        "launch_agent": _launch_agent_status(plist_path, launch_probe),
        "controls": {
            "can_quit": True,
            "can_restart": bool((home / "start.sh").exists()),
            "restart_strategy": "launch_agent" if plist_path.exists() else "detached_start",
        },
    }


def _target_process(runtime_file: str | Path | None = None) -> dict[str, Any]:
    runtime_state = _read_json_file(_path(runtime_file, RUNTIME_STATE_FILE))
    processes = runtime_state.get("processes", {})
    if isinstance(processes, dict):
        launcher_pid = _int_or_none(processes.get("parent_pid"))
        if launcher_pid and launcher_pid != os.getpid() and _pid_is_running(launcher_pid):
            return {"pid": launcher_pid, "source": "runtime_launcher", "process_group": True}
    parent_pid = os.getppid()
    if parent_pid > 1:
        return {"pid": parent_pid, "source": "parent", "process_group": False}
    return {"pid": os.getpid(), "source": "self", "process_group": False}


def _schedule_lifecycle_child(payload: dict[str, Any]) -> None:
    child_code = (
        "import json, os, signal, subprocess, sys, time\n"
        "payload=json.loads(sys.argv[1])\n"
        "time.sleep(float(payload.get('delay_seconds', 0.75)))\n"
        "target=int(payload['target_pid'])\n"
        "mode=payload.get('mode', 'quit')\n"
        "restart_cmd=payload.get('restart_cmd') or []\n"
        "cwd=payload.get('cwd') or None\n"
        "log_path=payload.get('log_path')\n"
        "use_process_group=bool(payload.get('process_group'))\n"
        "def alive(pid):\n"
        "    try:\n"
        "        os.kill(pid, 0)\n"
        "        return True\n"
        "    except ProcessLookupError:\n"
        "        return False\n"
        "    except PermissionError:\n"
        "        return True\n"
        "def send_signal(sig):\n"
        "    if use_process_group:\n"
        "        os.killpg(os.getpgid(target), sig)\n"
        "    else:\n"
        "        os.kill(target, sig)\n"
        "try:\n"
        "    send_signal(signal.SIGTERM)\n"
        "except ProcessLookupError:\n"
        "    pass\n"
        "if mode == 'restart':\n"
        "    time.sleep(float(payload.get('restart_wait_seconds', 2.0)))\n"
        "    if restart_cmd and log_path:\n"
        "        os.makedirs(os.path.dirname(log_path), exist_ok=True)\n"
        "        out = open(log_path, 'ab')\n"
        "        subprocess.Popen(restart_cmd, cwd=cwd, stdout=out, stderr=out, start_new_session=True)\n"
        "        out.close()\n"
        "    elif restart_cmd:\n"
        "        subprocess.Popen(restart_cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)\n"
        "else:\n"
        "    time.sleep(float(payload.get('force_after_seconds', 8.0)))\n"
        "    if alive(target):\n"
        "        try:\n"
        "            send_signal(signal.SIGKILL)\n"
        "        except ProcessLookupError:\n"
        "            pass\n"
    )
    subprocess.Popen(  # nosec B603
        [sys.executable, "-c", child_code, json.dumps(payload)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def restart_app(
    *,
    mode: str = "full",
    dry_run: bool = False,
    delay_seconds: float = 0.75,
    runtime_file: str | Path | None = None,
    jarvis_home: str | Path | None = None,
) -> dict[str, Any]:
    """Restart JARVIS by stopping the current wrapper and relaunching start.sh."""
    home = _path(jarvis_home, settings.JARVIS_HOME)
    start_script = home / "start.sh"
    target = _target_process(runtime_file)
    target_pid = int(target["pid"])
    plist_path = DEFAULT_LAUNCH_AGENTS_DIR / LAUNCH_AGENT_FILENAME
    launch_agent_loaded = bool(_launch_agent_status(plist_path, platform.system() == "Darwin").get("loaded"))
    restart_cmd = [] if launch_agent_loaded else [str(start_script), mode]
    payload = {
        "mode": "restart",
        "target_pid": target_pid,
        "target_source": target["source"],
        "process_group": target["process_group"],
        "restart_cmd": restart_cmd,
        "cwd": str(home),
        "delay_seconds": delay_seconds,
        "restart_wait_seconds": 2.0,
        "log_path": str(home / "data" / "logs" / "lifecycle-restart.log"),
    }
    result = {
        "status": "planned" if dry_run else "scheduled",
        "dry_run": dry_run,
        "mode": mode,
        "target_pid": target_pid,
        "target_source": target["source"],
        "process_group": target["process_group"],
        "strategy": "launch_agent" if launch_agent_loaded else "detached_start",
        "restart_command": restart_cmd,
        "message": "JARVIS restart scheduled." if not dry_run else "JARVIS restart preview.",
    }
    if not dry_run:
        _schedule_lifecycle_child(payload)
    return result


def quit_app(
    *,
    dry_run: bool = False,
    delay_seconds: float = 0.75,
    force_after_seconds: float = 8.0,
    runtime_file: str | Path | None = None,
) -> dict[str, Any]:
    """Quit JARVIS by signalling the current launcher process."""
    target = _target_process(runtime_file)
    target_pid = int(target["pid"])
    payload = {
        "mode": "quit",
        "target_pid": target_pid,
        "target_source": target["source"],
        "process_group": target["process_group"],
        "delay_seconds": delay_seconds,
        "force_after_seconds": force_after_seconds,
    }
    result = {
        "status": "planned" if dry_run else "scheduled",
        "dry_run": dry_run,
        "target_pid": target_pid,
        "target_source": target["source"],
        "process_group": target["process_group"],
        "force_after_seconds": force_after_seconds,
        "message": "JARVIS quit scheduled." if not dry_run else "JARVIS quit preview.",
    }
    if not dry_run:
        _schedule_lifecycle_child(payload)
    return result


def main(argv: list[str] | None = None) -> int:
    """Small CLI used by installer scripts."""
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else "status"
    if command == "status":
        print(json.dumps(get_status(), indent=2, sort_keys=True))
        return 0
    if command == "install-agent":
        print(json.dumps(install_launch_agent(), indent=2, sort_keys=True))
        return 0
    if command == "uninstall-agent":
        print(json.dumps(uninstall_launch_agent(), indent=2, sort_keys=True))
        return 0
    if command == "render-agent":
        sys.stdout.write(render_launch_agent_plist().decode("utf-8"))
        return 0
    print("Usage: python -m jarvis.core.app_lifecycle [status|install-agent|uninstall-agent|render-agent]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
