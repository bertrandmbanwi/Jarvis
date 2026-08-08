from __future__ import annotations

from pathlib import Path

VISIBLE_FILES = [
    Path("jarvis/ui/jarvis-ui/src/app/layout.tsx"),
    Path("jarvis/ui/jarvis-ui/src/components/auth/LoginScreen.tsx"),
    Path("jarvis/ui/jarvis-ui/src/components/shared/StatusBar.tsx"),
    Path("jarvis/ui/jarvis-ui/src/components/chat/ChatView.tsx"),
    Path("jarvis/ui/jarvis-ui/src/components/dashboard/DashboardView.tsx"),
    Path("jarvis/ui/jarvis-ui/src/components/settings/SettingsPanel.tsx"),
    Path("jarvis/ui/jarvis-ui/src/components/product/ProductView.tsx"),
]

FORBIDDEN_STRINGS = [
    "J.A.R.V.I.S.",
    "Just A Rather Very Intelligent System",
    "JARVIS Settings",
    "Restart JARVIS",
    "Quit JARVIS",
    "The PIN is displayed in the JARVIS terminal on startup.",
    "No activity yet. Use Voice or Chat to interact with JARVIS.",
    "Start a conversation with JARVIS",
    "Enter your access PIN",
]


def test_visible_ui_strings_do_not_use_legacy_jarvis_branding() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    hits: list[str] = []

    for rel_path in VISIBLE_FILES:
        text = (repo_root / rel_path).read_text(encoding="utf-8")
        for needle in FORBIDDEN_STRINGS:
            if needle in text:
                hits.append(f"{rel_path}: {needle}")

    assert not hits, "Legacy visible branding still present:\n" + "\n".join(sorted(hits))
