"""Agent Skills: reusable instructions loaded from SKILL.md folders.

A skill is a folder containing ``SKILL.md``: YAML frontmatter with ``name``
and ``description``, then Markdown instructions, plus optional reference
files. This is the open Agent Skills format used by Claude, Codex and other
agents, so existing skills can be dropped in.

Skills are read from ``skills/`` in this repository and ``~/.jarvis/skills``
(the user's copy wins on a name clash). Progressive disclosure: only names
and descriptions go into the system prompt; the model calls ``use_skill``
to load the full instructions when a skill fits. Bundled scripts are never
executed; skills are instructions and reference material only.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from jarvis.config import settings

logger = logging.getLogger("jarvis.skills")

SKILL_DIRS = [
    settings.JARVIS_HOME / "skills",
    Path(os.getenv("JARVIS_SKILLS_DIR", str(Path.home() / ".jarvis" / "skills"))),
]
MAX_SKILL_CHARS = 20000
_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path  # the skill folder

    @property
    def instructions(self) -> str:
        return parse_skill_file(self.path / "SKILL.md")[2]


def parse_skill_file(path: Path) -> tuple[str, str, str]:
    """Return (name, description, body) from a SKILL.md file."""
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(text)
    if not match:
        raise ValueError(f"{path}: missing YAML frontmatter")
    meta = yaml.safe_load(match.group(1)) or {}
    name = str(meta.get("name") or path.parent.name).strip()
    description = " ".join(str(meta.get("description", "")).split())
    if not description:
        raise ValueError(f"{path}: frontmatter needs a description")
    return name, description, match.group(2).strip()


_cache: tuple[tuple, dict[str, Skill]] | None = None


def _fingerprint() -> tuple:
    stamps = []
    for base in SKILL_DIRS:
        for skill_md in sorted(base.glob("*/SKILL.md")) if base.is_dir() else []:
            stamps.append((str(skill_md), skill_md.stat().st_mtime_ns))
    return tuple(stamps)


def discover_skills() -> dict[str, Skill]:
    """All valid skills by name, re-read only when a SKILL.md changes."""
    global _cache
    fingerprint = _fingerprint()
    if _cache is not None and _cache[0] == fingerprint:
        return _cache[1]
    skills: dict[str, Skill] = {}
    for skill_md, _ in fingerprint:
        path = Path(skill_md)
        try:
            name, description, _body = parse_skill_file(path)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            logger.warning("Skipping skill %s: %s", path, exc)
            continue
        skills[name] = Skill(name=name, description=description, path=path.parent)
    _cache = (fingerprint, skills)
    return skills


def skills_prompt() -> str:
    """Skill index for the system prompt; stable while skills are unchanged, so it caches."""
    skills = discover_skills()
    if not skills:
        return ""
    lines = [f"- {s.name}: {s.description}" for s in sorted(skills.values(), key=lambda s: s.name)]
    return (
        "\n<skills>\nSpecialised instructions are available for these tasks. When one fits the "
        "request, call use_skill with its name before starting, then follow it.\n"
        + "\n".join(lines)
        + "\n</skills>\n"
    )


async def use_skill(name: str) -> str:
    """Load a skill's full instructions and list its reference files."""
    skill = discover_skills().get(name)
    if skill is None:
        available = ", ".join(sorted(discover_skills())) or "none"
        return f"No skill named '{name}'. Available skills: {available}."
    files = sorted(
        str(p.relative_to(skill.path)) for p in skill.path.rglob("*") if p.is_file() and p.name != "SKILL.md"
    )
    body = skill.instructions[:MAX_SKILL_CHARS]
    listing = ("\n\nReference files (read with read_skill_file): " + ", ".join(files)) if files else ""
    return f"# Skill: {skill.name}\n\n{body}{listing}"


async def read_skill_file(name: str, path: str) -> str:
    """Read a reference file bundled with a skill (confined to the skill's folder)."""
    skill = discover_skills().get(name)
    if skill is None:
        return f"No skill named '{name}'."
    root = skill.path.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        return f"No file '{path}' in skill '{name}'."
    return target.read_text(encoding="utf-8", errors="replace")[:MAX_SKILL_CHARS]
