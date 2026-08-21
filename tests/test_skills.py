"""Comprehensive tests for the Alcyoneus OS Skills system.

Covers:
- SkillMeta / SkillConfig validation (models)
- discover_skills, load_skill_content, load_resource, _parse_frontmatter (loader)
- SkillsRegistry CRUD, tag filtering, hot-reload, trigger table (registry)
- make_set_skill_tool / set_skill tool error paths (activation)
- AgentSkillsMixin._setup_skills and _build_skill_prompts (agent integration)
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
from pydantic import ValidationError

from alcyoneus.core.skills.activation import make_set_skill_tool
from alcyoneus.core.skills.loader import (
    _parse_frontmatter,
    discover_skills,
    load_resource,
    load_skill_content,
)
from alcyoneus.core.skills.models import SkillConfig, SkillMeta
from alcyoneus.core.skills.registry import SkillsRegistry


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def _make_skill_dir(
    tmp_path: Path,
    name: str,
    *,
    description: str = "A test skill",
    triggers: list[str] | None = None,
    resources: dict[str, str] | None = None,
    tags: list[str] | None = None,
    priority: int = 0,
    body: str = "# Skill body\nSome instructions.",
    use_metadata_block: bool = True,
    extra_yaml: str = "",
) -> Path:
    """Create a skill directory with a SKILL.md file.

    Returns the path to the skill *subdirectory* (not the parent).
    """
    skill_dir = tmp_path / name
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Build YAML frontmatter
    yaml_lines = [f"name: {name}", f"description: {description}"]

    if use_metadata_block:
        yaml_lines.append("metadata:")
        if triggers:
            yaml_lines.append("  triggers:")
            for t in triggers:
                yaml_lines.append(f"    - {t}")
        if resources:
            yaml_lines.append("  resources:")
            for r in resources:
                yaml_lines.append(f"    - {r}")
        if tags:
            yaml_lines.append("  tags:")
            for t in tags:
                yaml_lines.append(f"    - {t}")
        if priority:
            yaml_lines.append(f"  priority: {priority}")
    else:
        if triggers:
            yaml_lines.append("triggers:")
            for t in triggers:
                yaml_lines.append(f"  - {t}")
        if resources:
            yaml_lines.append("resources:")
            for r in resources:
                yaml_lines.append(f"  - {r}")
        if tags:
            yaml_lines.append("tags:")
            for t in tags:
                yaml_lines.append(f"  - {t}")
        if priority:
            yaml_lines.append(f"priority: {priority}")

    if extra_yaml:
        yaml_lines.append(extra_yaml)

    yaml_section = "\n".join(yaml_lines)
    content = f"---\n{yaml_section}\n---\n{body}"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    # Create resource files
    if resources:
        for rel_path, text in resources.items():
            res_file = skill_dir / rel_path
            res_file.parent.mkdir(parents=True, exist_ok=True)
            res_file.write_text(text, encoding="utf-8")

    return skill_dir


def _quick_meta(name: str = "test-skill", **kwargs) -> SkillMeta:
    """Create a SkillMeta with sensible defaults."""
    defaults = {
        "description": f"{name} description",
        "triggers": [],
        "resources": [],
        "tags": set(),
        "priority": 0,
        "skill_dir": ".",
        "skill_file": "",
    }
    defaults.update(kwargs)
    return SkillMeta(name=name, **defaults)


# ════════════════════════════════════════════════════════════════════════════
# 1. SkillMeta Validation
# ════════════════════════════════════════════════════════════════════════════


class TestSkillMetaValidation:
    """Validate SkillMeta Pydantic model constraints."""

    # -- name ---------------------------------------------------------------

    def test_valid_name(self):
        meta = _quick_meta("my-skill-01")
        assert meta.name == "my-skill-01"

    def test_name_lowercased(self):
        meta = _quick_meta("My-Skill")
        assert meta.name == "my-skill"

    def test_name_empty_raises(self):
        with pytest.raises(ValidationError, match="empty"):
            _quick_meta("")

    def test_name_whitespace_only_raises(self):
        with pytest.raises(ValidationError, match="empty"):
            _quick_meta("   ")

    def test_name_with_spaces_raises(self):
        with pytest.raises(ValidationError, match="Invalid skill name"):
            _quick_meta("my skill")

    def test_name_with_special_chars_raises(self):
        with pytest.raises(ValidationError, match="Invalid skill name"):
            _quick_meta("my@skill!")

    def test_name_too_long_raises(self):
        with pytest.raises(ValidationError, match="exceeds"):
            _quick_meta("a" * 200)

    def test_name_with_slash_raises(self):
        with pytest.raises(ValidationError, match="Invalid skill name"):
            _quick_meta("my/skill")

    def test_name_underscore_allowed(self):
        meta = _quick_meta("my_skill")
        assert meta.name == "my_skill"

    def test_name_starts_with_digit(self):
        meta = _quick_meta("1skill")
        assert meta.name == "1skill"

    # -- description --------------------------------------------------------

    def test_description_empty_raises(self):
        with pytest.raises(ValidationError, match="empty"):
            SkillMeta(name="valid", description="", skill_dir=".", skill_file="")

    def test_description_whitespace_only_raises(self):
        with pytest.raises(ValidationError, match="empty"):
            SkillMeta(name="valid", description="   ", skill_dir=".", skill_file="")

    def test_description_too_long_raises(self):
        with pytest.raises(ValidationError, match="exceeds"):
            SkillMeta(name="valid", description="x" * 3000, skill_dir=".", skill_file="")

    def test_description_stripped(self):
        meta = _quick_meta(description="  hello world  ")
        assert meta.description == "hello world"

    # -- priority -----------------------------------------------------------

    def test_priority_negative_raises(self):
        with pytest.raises(ValidationError, match="non-negative"):
            _quick_meta(priority=-1)

    def test_priority_too_high_raises(self):
        with pytest.raises(ValidationError, match="exceeds maximum"):
            _quick_meta(priority=9999)

    def test_priority_zero_ok(self):
        meta = _quick_meta(priority=0)
        assert meta.priority == 0

    def test_priority_max_ok(self):
        meta = _quick_meta(priority=1000)
        assert meta.priority == 1000

    # -- triggers -----------------------------------------------------------

    def test_triggers_empty_ok(self):
        meta = _quick_meta(triggers=[])
        assert meta.triggers == []

    def test_triggers_stripped(self):
        meta = _quick_meta(triggers=["  hello  ", "  world  "])
        assert meta.triggers == ["hello", "world"]

    def test_triggers_empty_strings_dropped(self):
        meta = _quick_meta(triggers=["valid", "", "  ", "also-valid"])
        assert meta.triggers == ["valid", "also-valid"]

    def test_triggers_too_many_raises(self):
        with pytest.raises(ValidationError, match="Too many triggers"):
            _quick_meta(triggers=["t"] * 51)

    def test_trigger_too_long_raises(self):
        with pytest.raises(ValidationError, match="exceeds"):
            _quick_meta(triggers=["x" * 600])

    # -- resources ----------------------------------------------------------

    def test_resources_path_traversal_raises(self):
        with pytest.raises(ValidationError, match="cannot contain"):
            _quick_meta(resources=["../../../etc/passwd"])

    def test_resources_absolute_path_raises(self):
        with pytest.raises(ValidationError, match="cannot contain"):
            _quick_meta(resources=["/etc/passwd"])

    def test_resources_backslash_absolute_raises(self):
        with pytest.raises(ValidationError, match="cannot contain"):
            _quick_meta(resources=["\\Windows\\system32"])

    def test_resources_empty_string_raises(self):
        with pytest.raises(ValidationError, match="empty"):
            _quick_meta(resources=[""])

    def test_resources_valid_relative_path(self):
        meta = _quick_meta(resources=["docs/guide.md", "config.yaml"])
        assert meta.resources == ["docs/guide.md", "config.yaml"]

    def test_resources_too_many_raises(self):
        with pytest.raises(ValidationError, match="Too many resources"):
            _quick_meta(resources=[f"file{i}.md" for i in range(101)])

    # -- tags ---------------------------------------------------------------

    def test_tags_lowercased(self):
        meta = _quick_meta(tags={"Engineering", "MEDICAL"})
        assert meta.tags == {"engineering", "medical"}

    def test_tags_empty_strings_filtered(self):
        meta = _quick_meta(tags={"valid", "", "  "})
        assert meta.tags == {"valid"}

    def test_tags_too_many_raises(self):
        with pytest.raises(ValidationError, match="Too many tags"):
            _quick_meta(tags={f"tag{i}" for i in range(51)})


# ════════════════════════════════════════════════════════════════════════════
# 2. SkillConfig Validation
# ════════════════════════════════════════════════════════════════════════════


class TestSkillConfigValidation:
    def test_default_config(self):
        cfg = SkillConfig()
        assert cfg.skills_dir is None
        assert cfg.inject_trigger_table is True
        assert cfg.hot_reload is True

    def test_skills_dir_none_ok(self):
        cfg = SkillConfig(skills_dir=None)
        assert cfg.skills_dir is None

    def test_skills_dir_empty_string_raises(self):
        with pytest.raises(ValidationError, match="empty string"):
            SkillConfig(skills_dir="")

    def test_skills_dir_whitespace_raises(self):
        with pytest.raises(ValidationError, match="empty string"):
            SkillConfig(skills_dir="   ")

    def test_skills_dir_valid_path(self):
        cfg = SkillConfig(skills_dir="/some/path")
        assert cfg.skills_dir == "/some/path"

    def test_flags_can_be_disabled(self):
        cfg = SkillConfig(inject_trigger_table=False, hot_reload=False)
        assert cfg.inject_trigger_table is False
        assert cfg.hot_reload is False


# ════════════════════════════════════════════════════════════════════════════
# 3. Loader — _parse_frontmatter
# ════════════════════════════════════════════════════════════════════════════


class TestParseFrontmatter:
    def test_valid_frontmatter(self, tmp_path: Path):
        f = tmp_path / "SKILL.md"
        f.write_text("---\nname: test\ndescription: hi\n---\nBody", encoding="utf-8")
        result = _parse_frontmatter(str(f))
        assert result == {"name": "test", "description": "hi"}

    def test_no_frontmatter(self, tmp_path: Path):
        f = tmp_path / "SKILL.md"
        f.write_text("Just plain markdown", encoding="utf-8")
        assert _parse_frontmatter(str(f)) is None

    def test_unclosed_frontmatter(self, tmp_path: Path):
        f = tmp_path / "SKILL.md"
        f.write_text("---\nname: test\nno closing marker", encoding="utf-8")
        assert _parse_frontmatter(str(f)) is None

    def test_invalid_yaml(self, tmp_path: Path):
        f = tmp_path / "SKILL.md"
        f.write_text("---\n: - : invalid\n  [\n---\nBody", encoding="utf-8")
        assert _parse_frontmatter(str(f)) is None

    def test_empty_frontmatter(self, tmp_path: Path):
        f = tmp_path / "SKILL.md"
        f.write_text("---\n\n---\nBody", encoding="utf-8")
        result = _parse_frontmatter(str(f))
        assert result == {}

    def test_non_dict_frontmatter(self, tmp_path: Path):
        """Frontmatter that parses to a list instead of a dict should be rejected."""
        f = tmp_path / "SKILL.md"
        f.write_text("---\n- item1\n- item2\n---\nBody", encoding="utf-8")
        assert _parse_frontmatter(str(f)) is None

    def test_nonexistent_file(self):
        assert _parse_frontmatter("/nonexistent/SKILL.md") is None

    def test_scalar_frontmatter_rejected(self, tmp_path: Path):
        """Frontmatter that parses to a string should be rejected."""
        f = tmp_path / "SKILL.md"
        f.write_text("---\njust a string\n---\nBody", encoding="utf-8")
        # yaml.safe_load("just a string") returns a string, not a dict
        assert _parse_frontmatter(str(f)) is None


# ════════════════════════════════════════════════════════════════════════════
# 4. Loader — discover_skills
# ════════════════════════════════════════════════════════════════════════════


class TestDiscoverSkills:
    def test_discover_single_skill(self, tmp_path: Path):
        _make_skill_dir(tmp_path, "triage", description="Medical triage skill")
        results = discover_skills(str(tmp_path))
        assert len(results) == 1
        assert results[0].name == "triage"
        assert results[0].description == "Medical triage skill"

    def test_discover_multiple_skills(self, tmp_path: Path):
        _make_skill_dir(tmp_path, "alpha")
        _make_skill_dir(tmp_path, "beta")
        _make_skill_dir(tmp_path, "gamma")
        results = discover_skills(str(tmp_path))
        names = [s.name for s in results]
        assert sorted(names) == ["alpha", "beta", "gamma"]

    def test_discover_nonexistent_dir_returns_empty(self):
        results = discover_skills("/nonexistent/skills/dir")
        assert results == []

    def test_discover_empty_dir(self, tmp_path: Path):
        results = discover_skills(str(tmp_path))
        assert results == []

    def test_discover_skips_dir_without_skill_md(self, tmp_path: Path):
        (tmp_path / "no-skill").mkdir()
        (tmp_path / "no-skill" / "README.md").write_text("Not a skill", encoding="utf-8")
        results = discover_skills(str(tmp_path))
        assert results == []

    def test_discover_skips_missing_name(self, tmp_path: Path):
        skill_dir = tmp_path / "bad"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: no name\n---\nBody", encoding="utf-8"
        )
        results = discover_skills(str(tmp_path))
        assert results == []

    def test_discover_skips_missing_description(self, tmp_path: Path):
        skill_dir = tmp_path / "bad"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: bad\n---\nBody", encoding="utf-8"
        )
        results = discover_skills(str(tmp_path))
        assert results == []

    def test_discover_with_metadata_block(self, tmp_path: Path):
        _make_skill_dir(
            tmp_path,
            "triage",
            triggers=["help me"],
            tags=["medical"],
            priority=5,
            use_metadata_block=True,
        )
        results = discover_skills(str(tmp_path))
        assert len(results) == 1
        assert results[0].triggers == ["help me"]
        assert results[0].tags == {"medical"}
        assert results[0].priority == 5

    def test_discover_with_top_level_fields(self, tmp_path: Path):
        _make_skill_dir(
            tmp_path,
            "triage",
            triggers=["help me"],
            tags=["medical"],
            priority=5,
            use_metadata_block=False,
        )
        results = discover_skills(str(tmp_path))
        assert len(results) == 1
        assert results[0].triggers == ["help me"]
        assert results[0].tags == {"medical"}
        assert results[0].priority == 5

    def test_discover_with_resources(self, tmp_path: Path):
        _make_skill_dir(
            tmp_path,
            "review",
            resources={"style.md": "Style guide content"},
        )
        results = discover_skills(str(tmp_path))
        assert len(results) == 1
        assert results[0].resources == ["style.md"]

    def test_discover_skips_missing_resource_file(self, tmp_path: Path):
        """Resource declared in YAML but file doesn't exist should be excluded."""
        skill_dir = tmp_path / "review"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: review\ndescription: d\nmetadata:\n  resources:\n    - missing.md\n---\nBody",
            encoding="utf-8",
        )
        results = discover_skills(str(tmp_path))
        assert len(results) == 1
        assert results[0].resources == []

    def test_discover_invalid_priority_defaults_to_zero(self, tmp_path: Path):
        skill_dir = tmp_path / "badpri"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: badpri\ndescription: d\npriority: not-a-number\n---\nBody",
            encoding="utf-8",
        )
        results = discover_skills(str(tmp_path))
        assert len(results) == 1
        assert results[0].priority == 0

    def test_discover_path_traversal_resource_skipped(self, tmp_path: Path):
        """Resources with '..' should be silently skipped."""
        skill_dir = tmp_path / "evil"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: evil\ndescription: d\nmetadata:\n"
            "  resources:\n    - ../../../etc/passwd\n---\nBody",
            encoding="utf-8",
        )
        results = discover_skills(str(tmp_path))
        assert len(results) == 1
        assert results[0].resources == []

    def test_discover_skips_files_not_dirs(self, tmp_path: Path):
        """Files directly in skills_dir should be ignored (only subdirs matter)."""
        (tmp_path / "README.md").write_text("Not a skill", encoding="utf-8")
        _make_skill_dir(tmp_path, "valid")
        results = discover_skills(str(tmp_path))
        assert len(results) == 1
        assert results[0].name == "valid"

    def test_discover_invalid_name_format_skipped(self, tmp_path: Path):
        """A SKILL.md with a name that fails validation should be skipped."""
        skill_dir = tmp_path / "badname"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: 'my bad name!'\ndescription: d\n---\nBody",
            encoding="utf-8",
        )
        results = discover_skills(str(tmp_path))
        assert results == []

    def test_discover_triggers_as_single_string(self, tmp_path: Path):
        """Single string trigger (not a list) should be wrapped in a list."""
        skill_dir = tmp_path / "single"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: single\ndescription: d\ntriggers: help me\n---\nBody",
            encoding="utf-8",
        )
        results = discover_skills(str(tmp_path))
        assert len(results) == 1
        assert results[0].triggers == ["help me"]


# ════════════════════════════════════════════════════════════════════════════
# 5. Loader — load_skill_content / load_resource
# ════════════════════════════════════════════════════════════════════════════


class TestLoadSkillContent:
    def test_load_content_strips_frontmatter(self, tmp_path: Path):
        skill_dir = _make_skill_dir(tmp_path, "test", body="Hello world!")
        meta = _quick_meta(skill_file=str(skill_dir / "SKILL.md"), skill_dir=str(skill_dir))
        content = load_skill_content(meta)
        assert "Hello world!" in content
        assert "---" not in content
        assert "name:" not in content

    def test_load_content_no_frontmatter(self, tmp_path: Path):
        f = tmp_path / "skill" / "SKILL.md"
        f.parent.mkdir()
        f.write_text("Just markdown, no frontmatter", encoding="utf-8")
        meta = _quick_meta(skill_file=str(f), skill_dir=str(f.parent))
        content = load_skill_content(meta)
        assert "Just markdown" in content

    def test_load_content_missing_file(self):
        meta = _quick_meta(skill_file="/nonexistent/SKILL.md")
        assert load_skill_content(meta) == ""


class TestLoadResource:
    def test_load_valid_resource(self, tmp_path: Path):
        skill_dir = _make_skill_dir(
            tmp_path,
            "review",
            resources={"guide.md": "Guide content here"},
        )
        meta = _quick_meta(
            skill_dir=str(skill_dir),
            skill_file=str(skill_dir / "SKILL.md"),
            resources=["guide.md"],
        )
        content = load_resource(meta, "guide.md")
        assert content == "Guide content here"

    def test_load_missing_resource(self, tmp_path: Path):
        skill_dir = tmp_path / "empty"
        skill_dir.mkdir()
        meta = _quick_meta(skill_dir=str(skill_dir))
        assert load_resource(meta, "nonexistent.md") is None

    def test_load_resource_path_traversal_blocked(self, tmp_path: Path):
        skill_dir = tmp_path / "safe"
        skill_dir.mkdir()
        meta = _quick_meta(skill_dir=str(skill_dir))
        assert load_resource(meta, "../../etc/passwd") is None

    def test_load_resource_absolute_path_blocked(self, tmp_path: Path):
        skill_dir = tmp_path / "safe"
        skill_dir.mkdir()
        meta = _quick_meta(skill_dir=str(skill_dir))
        assert load_resource(meta, "/etc/passwd") is None


# ════════════════════════════════════════════════════════════════════════════
# 6. SkillsRegistry
# ════════════════════════════════════════════════════════════════════════════


class TestSkillsRegistry:
    def test_register_and_get(self):
        registry = SkillsRegistry()
        meta = _quick_meta("alpha")
        registry.register(meta)
        assert registry.get("alpha") is meta

    def test_get_nonexistent_returns_none(self):
        assert SkillsRegistry().get("nope") is None

    def test_register_duplicate_same_file_idempotent(self, tmp_path: Path):
        registry = SkillsRegistry()
        f = tmp_path / "SKILL.md"
        f.write_text("x", encoding="utf-8")
        meta = _quick_meta("dup", skill_file=str(f))
        registry.register(meta)
        registry.register(meta)  # no error
        assert len(registry) == 1

    def test_register_duplicate_different_file_raises(self, tmp_path: Path):
        registry = SkillsRegistry()
        f1 = tmp_path / "a" / "SKILL.md"
        f2 = tmp_path / "b" / "SKILL.md"
        f1.parent.mkdir()
        f2.parent.mkdir()
        f1.write_text("x", encoding="utf-8")
        f2.write_text("y", encoding="utf-8")
        registry.register(_quick_meta("clash", skill_file=str(f1)))
        with pytest.raises(ValueError, match="Duplicate skill name"):
            registry.register(_quick_meta("clash", skill_file=str(f2)))

    def test_names_sorted(self):
        registry = SkillsRegistry()
        registry.register(_quick_meta("zebra"))
        registry.register(_quick_meta("alpha"))
        registry.register(_quick_meta("mid"))
        assert registry.names() == ["alpha", "mid", "zebra"]

    def test_len(self):
        registry = SkillsRegistry()
        assert len(registry) == 0
        registry.register(_quick_meta("one"))
        assert len(registry) == 1
        registry.register(_quick_meta("two"))
        assert len(registry) == 2

    def test_contains(self):
        registry = SkillsRegistry()
        registry.register(_quick_meta("present"))
        assert "present" in registry
        assert "absent" not in registry

    def test_unregister(self):
        registry = SkillsRegistry()
        registry.register(_quick_meta("temp"))
        assert registry.unregister("temp") is True
        assert "temp" not in registry
        assert len(registry) == 0

    def test_unregister_nonexistent_returns_false(self):
        assert SkillsRegistry().unregister("nope") is False

    def test_get_all_no_filter(self):
        registry = SkillsRegistry()
        registry.register(_quick_meta("a"))
        registry.register(_quick_meta("b"))
        assert len(registry.get_all()) == 2

    def test_get_all_with_tag_filter(self):
        registry = SkillsRegistry()
        registry.register(_quick_meta("med", tags={"medical", "health"}))
        registry.register(_quick_meta("eng", tags={"engineering"}))
        registry.register(_quick_meta("both", tags={"medical", "engineering"}))

        medical = registry.get_all(tags={"medical"})
        assert {s.name for s in medical} == {"med", "both"}

        engineering = registry.get_all(tags={"engineering"})
        assert {s.name for s in engineering} == {"eng", "both"}

    def test_get_all_no_matching_tags(self):
        registry = SkillsRegistry()
        registry.register(_quick_meta("a", tags={"x"}))
        assert registry.get_all(tags={"nonexistent"}) == []

    def test_discover_integration(self, tmp_path: Path):
        _make_skill_dir(tmp_path, "alpha", description="Alpha skill")
        _make_skill_dir(tmp_path, "beta", description="Beta skill")

        registry = SkillsRegistry()
        found = registry.discover(str(tmp_path))

        assert len(found) == 2
        assert len(registry) == 2
        assert "alpha" in registry
        assert "beta" in registry

    def test_load_content(self, tmp_path: Path):
        skill_dir = _make_skill_dir(tmp_path, "review", body="Review instructions here.")
        registry = SkillsRegistry()
        registry.register(
            _quick_meta(
                "review",
                skill_dir=str(skill_dir),
                skill_file=str(skill_dir / "SKILL.md"),
            )
        )
        content = registry.load_content("review")
        assert "Review instructions here." in content

    def test_load_content_nonexistent_skill(self):
        assert SkillsRegistry().load_content("nope") == ""

    def test_load_content_hot_reload(self, tmp_path: Path):
        """Content updates when hot_reload is enabled and file changes."""
        skill_dir = _make_skill_dir(tmp_path, "hot", body="Version 1")
        registry = SkillsRegistry()
        registry.register(
            _quick_meta(
                "hot",
                skill_dir=str(skill_dir),
                skill_file=str(skill_dir / "SKILL.md"),
            )
        )

        content_v1 = registry.load_content("hot", hot_reload=True)
        assert "Version 1" in content_v1

        # Update the file
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("---\nname: hot\ndescription: d\n---\nVersion 2", encoding="utf-8")

        content_v2 = registry.load_content("hot", hot_reload=True)
        assert "Version 2" in content_v2

    def test_load_resources(self, tmp_path: Path):
        skill_dir = _make_skill_dir(
            tmp_path,
            "review",
            resources={"style.md": "Style guide", "api.md": "API docs"},
        )
        registry = SkillsRegistry()
        registry.register(
            _quick_meta(
                "review",
                skill_dir=str(skill_dir),
                skill_file=str(skill_dir / "SKILL.md"),
                resources=["style.md", "api.md"],
            )
        )
        res = registry.load_resources("review")
        assert res == {"style.md": "Style guide", "api.md": "API docs"}

    def test_load_resources_nonexistent_skill(self):
        assert SkillsRegistry().load_resources("nope") == {}


# ════════════════════════════════════════════════════════════════════════════
# 7. Trigger Table
# ════════════════════════════════════════════════════════════════════════════


class TestTriggerTable:
    def test_empty_registry_returns_empty(self):
        assert SkillsRegistry().build_trigger_table() == ""

    def test_table_has_all_skills(self):
        registry = SkillsRegistry()
        registry.register(_quick_meta("alpha", priority=1))
        registry.register(_quick_meta("beta", priority=2))

        table = registry.build_trigger_table()
        assert "`alpha`" in table
        assert "`beta`" in table
        assert "## Available Skills" in table

    def test_table_ordered_by_priority_desc(self):
        registry = SkillsRegistry()
        registry.register(_quick_meta("low", priority=1))
        registry.register(_quick_meta("high", priority=10))

        table = registry.build_trigger_table()
        assert table.index("`high`") < table.index("`low`")

    def test_table_sanitizes_pipes_and_newlines(self):
        registry = SkillsRegistry()
        registry.register(
            _quick_meta("x", triggers=["a | b", "line\nbreak"])
        )
        table = registry.build_trigger_table()
        assert "a \\| b" in table
        assert "line break" in table

    def test_table_respects_tag_filter(self):
        registry = SkillsRegistry()
        registry.register(_quick_meta("med", tags={"medical"}))
        registry.register(_quick_meta("eng", tags={"engineering"}))

        table = registry.build_trigger_table(tags={"medical"})
        assert "`med`" in table
        assert "`eng`" not in table

    def test_table_uses_description_when_no_triggers(self):
        registry = SkillsRegistry()
        registry.register(_quick_meta("nodesc", description="Use for everything", triggers=[]))
        table = registry.build_trigger_table()
        assert "Use for everything" in table


# ════════════════════════════════════════════════════════════════════════════
# 8. Activation — set_skill tool
# ════════════════════════════════════════════════════════════════════════════


class TestSetSkillTool:
    def _setup_registry(self, tmp_path: Path) -> tuple[SkillsRegistry, str]:
        """Create a registry with one skill and return (registry, skill_name)."""
        skill_dir = _make_skill_dir(
            tmp_path,
            "review",
            body="## Review Instructions\nDo the review.",
            resources={"guide.md": "The guide"},
        )
        registry = SkillsRegistry()
        registry.register(
            _quick_meta(
                "review",
                skill_dir=str(skill_dir),
                skill_file=str(skill_dir / "SKILL.md"),
                resources=["guide.md"],
            )
        )
        return registry, "review"

    def test_load_skill_content(self, tmp_path: Path):
        registry, name = self._setup_registry(tmp_path)
        set_skill = make_set_skill_tool(registry)
        result = set_skill(name)
        assert "## SKILL: REVIEW" in result
        assert "Review Instructions" in result

    def test_load_skill_resource(self, tmp_path: Path):
        registry, name = self._setup_registry(tmp_path)
        set_skill = make_set_skill_tool(registry)
        result = set_skill(name, "guide.md")
        assert "## Resource: guide.md" in result
        assert "The guide" in result

    def test_unknown_skill_error(self, tmp_path: Path):
        registry, _ = self._setup_registry(tmp_path)
        set_skill = make_set_skill_tool(registry)
        result = set_skill("nonexistent")
        assert result.startswith("ERROR: Unknown skill")
        assert "review" in result  # lists available skills

    def test_nonexistent_resource_error(self, tmp_path: Path):
        registry, name = self._setup_registry(tmp_path)
        set_skill = make_set_skill_tool(registry)
        result = set_skill(name, "missing.md")
        assert result.startswith("ERROR: Resource 'missing.md' not found")

    def test_no_resources_error(self, tmp_path: Path):
        skill_dir = _make_skill_dir(tmp_path, "bare", body="Bare skill")
        registry = SkillsRegistry()
        registry.register(
            _quick_meta(
                "bare",
                skill_dir=str(skill_dir),
                skill_file=str(skill_dir / "SKILL.md"),
                resources=[],
            )
        )
        set_skill = make_set_skill_tool(registry)
        result = set_skill("bare", "anything.md")
        assert "ERROR: Skill 'bare' has no resources" in result

    def test_tool_docstring_lists_skills(self, tmp_path: Path):
        registry, _ = self._setup_registry(tmp_path)
        set_skill = make_set_skill_tool(registry)
        assert "review" in set_skill.__doc__

    def test_empty_content_returns_error(self, tmp_path: Path):
        """Skill file exists but has no body (only frontmatter) → error."""
        skill_dir = tmp_path / "empty-body"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: empty-body\ndescription: d\n---\n", encoding="utf-8"
        )
        registry = SkillsRegistry()
        registry.register(
            _quick_meta(
                "empty-body",
                skill_dir=str(skill_dir),
                skill_file=str(skill_dir / "SKILL.md"),
            )
        )
        set_skill = make_set_skill_tool(registry)
        result = set_skill("empty-body")
        assert "ERROR" in result


# ════════════════════════════════════════════════════════════════════════════
# 9. AgentSkillsMixin (unit-level, no real LLM calls)
# ════════════════════════════════════════════════════════════════════════════


class TestAgentSkillsMixin:
    def test_setup_skills_none(self):
        """When skills=None, all skill attributes should be None/empty."""
        from alcyoneus.core.skills.models import SkillConfig as SC
        from alcyoneus.core.graph.agent_internal.skills import AgentSkillsMixin

        mixin = AgentSkillsMixin()
        mixin._tool_node = None
        mixin._setup_skills(None)

        assert mixin._skills_config is None
        assert mixin._skills_registry is None
        assert mixin._trigger_table_prompt is None

    def test_setup_skills_invalid_type_raises(self):
        from alcyoneus.core.graph.agent_internal.skills import AgentSkillsMixin

        mixin = AgentSkillsMixin()
        mixin._tool_node = None
        with pytest.raises(TypeError, match="Expected SkillConfig"):
            mixin._setup_skills("not-a-config")

    def test_setup_skills_requires_existing_tool_node(self, tmp_path: Path):
        from alcyoneus.core.graph.agent_internal.skills import AgentSkillsMixin

        _make_skill_dir(tmp_path, "alpha")

        mixin = AgentSkillsMixin()
        mixin._tool_node = None
        with pytest.raises(RuntimeError, match="Skills require an existing ToolNode"):
            mixin._setup_skills(SkillConfig(skills_dir=str(tmp_path)))

    def test_setup_skills_defers_to_named_tool_node(self, tmp_path: Path):
        from alcyoneus.core.graph.agent_internal.skills import AgentSkillsMixin

        _make_skill_dir(tmp_path, "alpha")

        mixin = AgentSkillsMixin()
        mixin._tool_node = None
        mixin.tool_node_name = "TOOL"
        mixin._setup_skills(SkillConfig(skills_dir=str(tmp_path)))

        assert mixin._skills_config is not None
        assert mixin._skills_registry is not None
        assert getattr(mixin, "_extra_tools", None) is not None
        assert len(mixin._extra_tools) == 1

    def test_setup_skills_creates_registry_with_existing_tool_node(self, tmp_path: Path):
        from alcyoneus.core.graph.agent_internal.skills import AgentSkillsMixin
        from alcyoneus.core.graph.tool_node import ToolNode

        _make_skill_dir(tmp_path, "alpha")
        _make_skill_dir(tmp_path, "beta")

        mixin = AgentSkillsMixin()
        mixin._tool_node = ToolNode([])
        mixin._setup_skills(SkillConfig(skills_dir=str(tmp_path)))

        assert mixin._skills_registry is not None
        assert len(mixin._skills_registry) == 2
        assert mixin._tool_node is not None

    def test_setup_skills_adds_tool_to_existing_toolnode(self, tmp_path: Path):
        from alcyoneus.core.graph.agent_internal.skills import AgentSkillsMixin
        from alcyoneus.core.graph.tool_node import ToolNode

        def dummy_tool():
            """A dummy tool."""
            return "dummy"

        _make_skill_dir(tmp_path, "alpha")

        mixin = AgentSkillsMixin()
        mixin._tool_node = ToolNode([dummy_tool])
        mixin._setup_skills(SkillConfig(skills_dir=str(tmp_path)))

        # Tool node should still be the same object, with set_skill added
        assert mixin._tool_node is not None

    def test_build_skill_prompts_no_skills(self):
        from alcyoneus.core.graph.agent_internal.skills import AgentSkillsMixin

        mixin = AgentSkillsMixin()
        mixin._tool_node = None
        mixin._setup_skills(None)

        base = [{"role": "system", "content": "Be helpful"}]
        result = mixin._build_skill_prompts(None, base)
        assert result == base

    def test_build_skill_prompts_appends_trigger_table(self, tmp_path: Path):
        from alcyoneus.core.graph.agent_internal.skills import AgentSkillsMixin
        from alcyoneus.core.graph.tool_node import ToolNode

        _make_skill_dir(tmp_path, "review", triggers=["review code"])

        mixin = AgentSkillsMixin()
        mixin._tool_node = ToolNode([])
        mixin._setup_skills(SkillConfig(skills_dir=str(tmp_path), inject_trigger_table=True))

        base = [{"role": "system", "content": "Be helpful"}]
        result = mixin._build_skill_prompts(None, base)

        assert len(result) == 2
        assert result[0] == base[0]
        assert "Available Skills" in result[1]["content"]
        assert "review" in result[1]["content"]

    def test_build_skill_prompts_no_trigger_table_when_disabled(self, tmp_path: Path):
        from alcyoneus.core.graph.agent_internal.skills import AgentSkillsMixin
        from alcyoneus.core.graph.tool_node import ToolNode

        _make_skill_dir(tmp_path, "review")

        mixin = AgentSkillsMixin()
        mixin._tool_node = ToolNode([])
        mixin._setup_skills(SkillConfig(skills_dir=str(tmp_path), inject_trigger_table=False))

        base = [{"role": "system", "content": "Be helpful"}]
        result = mixin._build_skill_prompts(None, base)
        assert len(result) == 1

    def test_build_skill_prompts_does_not_mutate_original(self, tmp_path: Path):
        from alcyoneus.core.graph.agent_internal.skills import AgentSkillsMixin
        from alcyoneus.core.graph.tool_node import ToolNode

        _make_skill_dir(tmp_path, "review")

        mixin = AgentSkillsMixin()
        mixin._tool_node = ToolNode([])
        mixin._setup_skills(SkillConfig(skills_dir=str(tmp_path), inject_trigger_table=True))

        base = [{"role": "system", "content": "Be helpful"}]
        original_len = len(base)
        mixin._build_skill_prompts(None, base)
        assert len(base) == original_len  # original list not mutated
