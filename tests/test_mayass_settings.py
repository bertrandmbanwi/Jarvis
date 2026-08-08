"""Tests for MayAss configuration flags.

Phase 1 scope: verify MayAss can be toggled safely without touching UI,
voice, chat routing, or Hermes bridge code.
"""
import importlib

BOOL_ENV_NAMES = [
    "MAYASS_ENABLED",
    "MAYASS_REMOTE_ENABLED",
]

STRING_ENV_NAMES = [
    "MAYASS_DISPLAY_NAME",
    "MAYASS_CODENAME",
    "MAYASS_DEFAULT_MODE",
    "MAYASS_AUDIO_OWNER",
    "MAYASS_HERMES_COMMAND",
    "MAYASS_HERMES_PROFILE",
]


def reload_settings(monkeypatch, **env):
    for name in BOOL_ENV_NAMES + STRING_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    import jarvis.config.settings as settings

    return importlib.reload(settings)


def test_mayass_defaults_are_safe_and_disabled(monkeypatch):
    settings = reload_settings(monkeypatch)

    assert settings.MAYASS_ENABLED is False
    assert settings.MAYASS_REMOTE_ENABLED is False
    assert settings.MAYASS_AUDIO_OWNER == "browser"
    assert settings.MAYASS_DEFAULT_MODE == "realtime"


def test_mayass_identity_and_hermes_defaults_are_explicit(monkeypatch):
    settings = reload_settings(monkeypatch)

    assert settings.MAYASS_DISPLAY_NAME == "MayAss"
    assert settings.MAYASS_CODENAME == "Maymint-Hermes"
    assert settings.MAYASS_HERMES_COMMAND == "hermes -z"
    assert settings.MAYASS_HERMES_PROFILE == "default"


def test_mayass_env_overrides_are_read_at_import(monkeypatch):
    settings = reload_settings(
        monkeypatch,
        MAYASS_ENABLED="true",
        MAYASS_REMOTE_ENABLED="true",
        MAYASS_DISPLAY_NAME="Maymint",
        MAYASS_CODENAME="MayAss Shell",
        MAYASS_DEFAULT_MODE="work",
        MAYASS_AUDIO_OWNER="none",
        MAYASS_HERMES_COMMAND="hermes chat --profile default -Q",
        MAYASS_HERMES_PROFILE="maymint",
    )

    assert settings.MAYASS_ENABLED is True
    assert settings.MAYASS_REMOTE_ENABLED is True
    assert settings.MAYASS_DISPLAY_NAME == "Maymint"
    assert settings.MAYASS_CODENAME == "MayAss Shell"
    assert settings.MAYASS_DEFAULT_MODE == "work"
    assert settings.MAYASS_AUDIO_OWNER == "none"
    assert settings.MAYASS_HERMES_COMMAND == "hermes chat --profile default -Q"
    assert settings.MAYASS_HERMES_PROFILE == "maymint"


def test_mayass_invalid_mode_and_audio_owner_fall_back_to_safe_values(monkeypatch):
    settings = reload_settings(
        monkeypatch,
        MAYASS_DEFAULT_MODE="unsafe-full-auto",
        MAYASS_AUDIO_OWNER="all-devices",
    )

    assert settings.MAYASS_DEFAULT_MODE == "realtime"
    assert settings.MAYASS_AUDIO_OWNER == "browser"
