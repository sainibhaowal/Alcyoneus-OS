from pathlib import Path

import pytest

from alcyoneus.core.skills.activation import make_set_skill_tool
from alcyoneus.core.skills.models import SkillMeta
from alcyoneus.core.skills.registry import SkillsRegistry


def _skill(name: str, *, skill_file: str, skill_dir: str, **kwargs) -> SkillMeta:
    defaults = {
        "description": f"{name} description",
        "triggers": [],
        "resources": [],
        "tags": set(),
        "priority": 0,
    }
    defaults.update(kwargs)
    return SkillMeta(
        name=name,
        skill_file=skill_file,
        skill_dir=skill_dir,
        **defaults,
    )


def test_register_duplicate_name_different_file_raises(tmp_path: Path) -> None:
    registry = SkillsRegistry()

    skill_a_dir = tmp_path / "a"
    skill_b_dir = tmp_path / "b"
    skill_a_dir.mkdir()
    skill_b_dir.mkdir()

    skill_a_file = skill_a_dir / "SKILL.md"
    skill_b_file = skill_b_dir / "SKILL.md"
    skill_a_file.write_text("---\nname: dup\ndescription: d\n---\nA", encoding="utf-8")
    skill_b_file.write_text("---\nname: dup\ndescription: d\n---\nB", encoding="utf-8")

    registry.register(
        _skill(
            "dup",
            skill_file=str(skill_a_file),
            skill_dir=str(skill_a_dir),
        )
    )

    with pytest.raises(ValueError, match="Duplicate skill name"):
        registry.register(
            _skill(
                "dup",
                skill_file=str(skill_b_file),
                skill_dir=str(skill_b_dir),
            )
        )


def test_register_same_file_is_idempotent(tmp_path: Path) -> None:
    registry = SkillsRegistry()

    skill_dir = tmp_path / "same"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("---\nname: s\ndescription: d\n---\nX", encoding="utf-8")

    meta = _skill("s", skill_file=str(skill_file), skill_dir=str(skill_dir))
    registry.register(meta)
    registry.register(meta)

    assert registry.names() == ["s"]


def test_build_trigger_table_orders_by_priority_and_sanitizes() -> None:
    registry = SkillsRegistry()

    registry.register(
        SkillMeta(
            name="low",
            description="low desc",
            triggers=["low | one", "line\nbreak"],
            resources=[],
            tags=set(),
            priority=1,
            skill_dir=".",
            skill_file="",
        )
    )
    registry.register(
        SkillMeta(
            name="high",
            description="high desc",
            triggers=["first"],
            resources=[],
            tags=set(),
            priority=10,
            skill_dir=".",
            skill_file="",
        )
    )

    table = registry.build_trigger_table()

    high_idx = table.find("`high`")
    low_idx = table.find("`low`")
    assert high_idx != -1
    assert low_idx != -1
    assert high_idx < low_idx
    assert "low \\| one" in table
    assert "line break" in table


def test_set_skill_resource_ambiguous_filename_requires_exact_path(tmp_path: Path) -> None:
    registry = SkillsRegistry()

    skill_dir = tmp_path / "skill"
    (skill_dir / "docs").mkdir(parents=True)
    (skill_dir / "refs").mkdir(parents=True)

    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("---\nname: write\ndescription: d\n---\nBody", encoding="utf-8")

    (skill_dir / "docs" / "guide.md").write_text("docs guide", encoding="utf-8")
    (skill_dir / "refs" / "guide.md").write_text("refs guide", encoding="utf-8")

    registry.register(
        SkillMeta(
            name="write",
            description="d",
            triggers=[],
            resources=["docs/guide.md", "refs/guide.md"],
            tags=set(),
            priority=0,
            skill_dir=str(skill_dir),
            skill_file=str(skill_file),
        )
    )

    set_skill = make_set_skill_tool(registry)
    res = set_skill("write", "guide.md")

    assert res.startswith("ERROR: Resource 'guide.md' is ambiguous.")
    assert "docs/guide.md" in res
    assert "refs/guide.md" in res


def test_set_skill_resource_exact_path_still_works(tmp_path: Path) -> None:
    registry = SkillsRegistry()

    skill_dir = tmp_path / "skill"
    (skill_dir / "docs").mkdir(parents=True)

    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("---\nname: write\ndescription: d\n---\nBody", encoding="utf-8")
    (skill_dir / "docs" / "guide.md").write_text("docs guide", encoding="utf-8")

    registry.register(
        SkillMeta(
            name="write",
            description="d",
            triggers=[],
            resources=["docs/guide.md"],
            tags=set(),
            priority=0,
            skill_dir=str(skill_dir),
            skill_file=str(skill_file),
        )
    )

    set_skill = make_set_skill_tool(registry)
    res = set_skill("write", "docs/guide.md")

    assert res.startswith("## Resource: docs/guide.md")
    assert "docs guide" in res
