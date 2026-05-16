"""Tests for JARVIS app lifecycle diagnostics and macOS LaunchAgent rendering."""
import os
import plistlib

from jarvis.core import app_lifecycle


def test_launch_agent_plist_is_rendered_without_hardcoded_user_paths(tmp_path):
    plist_bytes = app_lifecycle.render_launch_agent_plist(tmp_path)
    plist = plistlib.loads(plist_bytes)

    assert plist["Label"] == app_lifecycle.LAUNCH_AGENT_LABEL
    assert plist["ProgramArguments"] == ["/bin/bash", str(tmp_path / "start.sh"), "full"]
    assert plist["WorkingDirectory"] == str(tmp_path)
    assert plist["EnvironmentVariables"]["JARVIS_HOME"] == str(tmp_path)
    plist_text = plist_bytes.decode("utf-8")
    assert "/Users/bertrandmbanwi/Documents/Jarvis" not in plist_text
    assert "__JARVIS_HOME__" not in plist_text


def test_install_launch_agent_writes_rendered_plist(tmp_path):
    launch_agents_dir = tmp_path / "LaunchAgents"
    jarvis_home = tmp_path / "Jarvis"

    result = app_lifecycle.install_launch_agent(
        jarvis_home=jarvis_home,
        launch_agents_dir=launch_agents_dir,
        dry_run=False,
    )

    plist_path = launch_agents_dir / app_lifecycle.LAUNCH_AGENT_FILENAME
    assert result["status"] == "installed"
    assert result["path"] == str(plist_path)
    assert plist_path.exists()

    plist = plistlib.loads(plist_path.read_bytes())
    assert plist["ProgramArguments"][1] == str(jarvis_home / "start.sh")
    assert plist["StandardOutPath"] == str(jarvis_home / "data" / "logs" / "launchd-stdout.log")


def test_lifecycle_status_reports_runtime_and_processes(tmp_path):
    runtime_file = tmp_path / "runtime" / "lifecycle.json"
    app_lifecycle.write_runtime_state(
        status="running",
        mode="full",
        api_port=9991,
        ui_port=3999,
        runtime_file=runtime_file,
        processes={"parent_pid": os.getpid(), "ui_pid": "", "overlay_pid": ""},
    )

    status = app_lifecycle.get_status(
        runtime_file=runtime_file,
        launch_agents_dir=tmp_path / "LaunchAgents",
        probe_launchctl=False,
    )

    assert status["status"] == "online"
    assert status["runtime"]["status"] == "running"
    assert status["runtime"]["mode"] == "full"
    assert status["runtime"]["state_file_exists"] is True
    assert status["ports"] == {"api": 9991, "ui": 3999}
    assert status["processes"]["backend"]["running"] is True
    assert status["launch_agent"]["installed"] is False


def test_restart_and_quit_support_dry_run(tmp_path):
    restart = app_lifecycle.restart_app(
        mode="server",
        dry_run=True,
        jarvis_home=tmp_path,
        runtime_file=tmp_path / "missing.json",
    )
    quit_result = app_lifecycle.quit_app(
        dry_run=True,
        runtime_file=tmp_path / "missing.json",
    )

    assert restart["status"] == "planned"
    assert restart["dry_run"] is True
    assert restart["restart_command"] == [str(tmp_path / "start.sh"), "server"]
    assert isinstance(restart["target_pid"], int)
    assert quit_result["status"] == "planned"
    assert quit_result["dry_run"] is True
    assert isinstance(quit_result["target_pid"], int)
