"""Tests for the macOS app packaging script."""
import plistlib
import subprocess


def test_package_macos_app_creates_launcher_bundle(tmp_path):
    result = subprocess.run(
        [
            "bash",
            "scripts/package_macos_app.sh",
            "--output",
            str(tmp_path),
            "--no-dmg",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    app_dir = tmp_path / "JARVIS.app"
    executable = app_dir / "Contents" / "MacOS" / "JARVIS"
    plist_path = app_dir / "Contents" / "Info.plist"
    home_file = app_dir / "Contents" / "Resources" / "jarvis-home"

    assert "Created" in result.stdout
    assert executable.exists()
    assert executable.stat().st_mode & 0o111
    assert home_file.read_text(encoding="utf-8").strip().endswith("Jarvis")

    with plist_path.open("rb") as fh:
        plist = plistlib.load(fh)

    assert plist["CFBundleIdentifier"] == "com.jarvis.assistant"
    assert plist["CFBundleExecutable"] == "JARVIS"
