"""Agent Skills discovery, progressive disclosure and file confinement."""

import pytest

from jarvis.core import skills


@pytest.fixture
def skill_dirs(tmp_path, monkeypatch):
    repo, user = tmp_path / "repo", tmp_path / "user"
    (repo / "demo").mkdir(parents=True)
    (repo / "demo" / "SKILL.md").write_text("---\nname: demo\ndescription: Demo skill for tests.\n---\n\nDo the demo.\n")
    (repo / "demo" / "notes.md").write_text("reference")
    (repo / "broken").mkdir()
    (repo / "broken" / "SKILL.md").write_text("no frontmatter here")
    (user / "demo").mkdir(parents=True)
    monkeypatch.setattr(skills, "SKILL_DIRS", [repo, user])
    monkeypatch.setattr(skills, "_cache", None)
    return repo, user


def test_discovery_skips_invalid_skills(skill_dirs):
    assert set(skills.discover_skills()) == {"demo"}


def test_user_skill_overrides_repo_skill(skill_dirs):
    _, user = skill_dirs
    (user / "demo" / "SKILL.md").write_text("---\nname: demo\ndescription: My version.\n---\nMine.\n")
    assert skills.discover_skills()["demo"].description == "My version."


def test_prompt_lists_names_and_descriptions_only(skill_dirs):
    prompt = skills.skills_prompt()
    assert "- demo: Demo skill for tests." in prompt
    assert "Do the demo." not in prompt


@pytest.mark.asyncio
async def test_use_skill_loads_instructions_and_files(skill_dirs):
    text = await skills.use_skill("demo")
    assert "Do the demo." in text and "notes.md" in text
    assert "No skill named" in await skills.use_skill("missing")


@pytest.mark.asyncio
async def test_read_skill_file_is_confined_to_the_skill(skill_dirs, tmp_path):
    (tmp_path / "secret.txt").write_text("secret")
    assert await skills.read_skill_file("demo", "notes.md") == "reference"
    assert "No file" in await skills.read_skill_file("demo", "../../secret.txt")


def test_bundled_skills_are_valid():
    for folder in (skills.SKILL_DIRS[0]).glob("*/SKILL.md"):
        name, description, body = skills.parse_skill_file(folder)
        assert name == folder.parent.name and description and body


def test_bundled_skills_only_reference_real_tools():
    import re

    from jarvis.agent.tools_schema import TOOL_REGISTRY

    for folder in (skills.SKILL_DIRS[0]).glob("*/SKILL.md"):
        body = folder.read_text()
        for token in re.findall(r"`([a-z_]+)`", body):
            if "_" in token and not token.startswith("days"):
                assert token in TOOL_REGISTRY, f"{folder.parent.name} mentions unknown tool {token}"
