"""Filesystem-based skill loader for Alcyoneus OS.

Scans a directory for SKILL.md files with YAML frontmatter, parses them
into SkillMeta objects, and provides content loading utilities.

Directory structure:
    skills/
    +-- triage/
    |   +-- SKILL.md          # YAML frontmatter + markdown body
    |   +-- protocols.md      # resource file referenced in frontmatter
    +-- prescription/
        +-- SKILL.md
        +-- formulary.md
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .models import SkillMeta


logger = logging.getLogger("alcyoneus.skills.loader")


def discover_skills(skills_dir: str) -> list[SkillMeta]:
    """Scan *skills_dir* for subdirectories containing a ``SKILL.md`` with
    valid YAML frontmatter and return a list of :class:`SkillMeta`.

    Each subdirectory that contains a ``SKILL.md`` with at least ``name``
    and ``description`` in its frontmatter is registered.  ``triggers``,
    ``resources``, ``tags``, and ``priority`` are optional and can be placed
    either at the top level **or** inside a ``metadata`` block (preferred —
    avoids IDE schema warnings)::

        ---
        name: skill-name
        description: When to use this skill (1-3 sentences)
        metadata:
          triggers:
            - user says X
            - user says Y
          resources:
            - protocols.md
          tags:
            - domain
          priority: 5
        ---
    """
    results: list[SkillMeta] = []

    skills_path = Path(skills_dir)
    if not skills_path.is_dir():
        logger.warning("Skills directory not found: %s", skills_dir)
        return results

    for entry in sorted(p.name for p in skills_path.iterdir()):
        skill_meta = _discover_skill(skills_path, entry)
        if skill_meta is None:
            continue

        results.append(skill_meta)
        logger.info(
            "Discovered skill: '%s' (%d resource(s))",
            skill_meta.name,
            len(skill_meta.resources),
        )

    return results


def load_skill_content(meta: SkillMeta) -> str:
    """Read and return the body of a SKILL.md (stripping YAML frontmatter)."""
    try:
        content = Path(meta.skill_file).read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Cannot read %s: %s", meta.skill_file, exc)
        return ""

    # Strip frontmatter
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            content = content[end + 4 :].lstrip("\n")

    return content


def load_resource(meta: SkillMeta, rel_path: str) -> str | None:
    """Read a resource file relative to the skill directory."""
    if ".." in rel_path or rel_path.startswith(("/", "\\")):
        logger.warning("Blocked unsafe resource path: %s", rel_path)
        return None
    skill_root = Path(meta.skill_dir).resolve()
    abs_path = (Path(meta.skill_dir) / rel_path).resolve()
    # Ensure the resolved path stays within the skill directory
    try:
        abs_path.relative_to(skill_root)
    except ValueError:
        logger.warning("Resource path escapes skill directory: %s", abs_path)
        return None
    try:
        return abs_path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Could not read resource: %s", abs_path)
        return None


# -- internal ---------------------------------------------------------------


def _parse_frontmatter(skill_file: str) -> dict[str, Any] | None:
    """Extract and parse YAML frontmatter from a SKILL.md file."""
    try:
        content = Path(skill_file).read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Cannot read %s: %s", skill_file, exc)
        return None

    raw_yaml = _extract_frontmatter_yaml(content)
    if raw_yaml is None:
        return None

    try:
        parsed = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        logger.error("YAML parse error in %s: %s", skill_file, exc)
        return None

    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        logger.error(
            "Frontmatter in %s is not a mapping (got %s)", skill_file, type(parsed).__name__
        )
        return None
    return parsed


def _discover_skill(skills_path: Path, entry: str) -> SkillMeta | None:
    """Parse and validate a single skill directory entry."""
    skill_dir = skills_path / entry
    skill_file = skill_dir / "SKILL.md"

    if not skill_dir.is_dir() or not skill_file.is_file():
        return None

    frontmatter = _parse_frontmatter(str(skill_file))
    if frontmatter is None:
        logger.warning("Skipping '%s': no valid YAML frontmatter in SKILL.md", entry)
        return None

    name, description = _extract_identity(frontmatter)
    if not name or not description:
        logger.warning("Skipping '%s': frontmatter missing 'name' or 'description'", entry)
        return None

    meta_block = _metadata_block(frontmatter)
    try:
        return SkillMeta(
            name=name,
            description=description,
            triggers=_normalize_text_list(
                meta_block.get("triggers") or frontmatter.get("triggers", [])
            ),
            resources=_resolve_resources(
                skill_dir,
                name,
                meta_block.get("resources") or frontmatter.get("resources", []),
            ),
            tags=_normalize_tags(meta_block.get("tags") or frontmatter.get("tags", [])),
            priority=_parse_priority(
                name, meta_block.get("priority", frontmatter.get("priority", 0))
            ),
            skill_dir=str(skill_dir),
            skill_file=str(skill_file),
        )
    except (ValueError, Exception) as exc:
        logger.warning("Skipping '%s': validation failed: %s", entry, exc)
        return None


def _extract_identity(frontmatter: dict[str, Any]) -> tuple[str, str]:
    """Return normalized required skill metadata fields."""
    return (
        str(frontmatter.get("name", "")).strip(),
        str(frontmatter.get("description", "")).strip(),
    )


def _metadata_block(frontmatter: dict[str, Any]) -> dict[str, Any]:
    """Return the optional metadata mapping if present and valid."""
    metadata = frontmatter.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _normalize_text_list(value: Any) -> list[str]:
    """Coerce a single string or list into a cleaned list of strings."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := str(item).strip())]


def _resolve_resources(skill_dir: Path, skill_name: str, raw_resources: Any) -> list[str]:
    """Validate resource paths and keep only existing files within the skill dir."""
    if not isinstance(raw_resources, list):
        return []

    skill_root = skill_dir.resolve()
    resources: list[str] = []
    for raw_resource in raw_resources:
        rel_path = str(raw_resource).strip()
        if not rel_path:
            continue
        if ".." in rel_path or rel_path.startswith(("/", "\\")):
            logger.warning("Skipping unsafe resource path for skill '%s': %s", skill_name, rel_path)
            continue

        abs_path = (skill_dir / rel_path).resolve()
        try:
            abs_path.relative_to(skill_root)
        except ValueError:
            logger.warning(
                "Resource path escapes skill directory for '%s': %s", skill_name, rel_path
            )
            continue

        if abs_path.is_file():
            resources.append(rel_path)
        else:
            logger.warning("Resource not found for skill '%s': %s", skill_name, rel_path)
    return resources


def _normalize_tags(raw_tags: Any) -> set[str]:
    """Coerce optional tags into a cleaned set of strings."""
    if not isinstance(raw_tags, list):
        return set()
    return {text for item in raw_tags if (text := str(item).strip())}


def _parse_priority(skill_name: str, raw_priority: Any) -> int:
    """Parse skill priority, falling back to zero for invalid values."""
    try:
        return int(raw_priority)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid priority for skill '%s': %r (defaulting to 0)",
            skill_name,
            raw_priority,
        )
        return 0


def _extract_frontmatter_yaml(content: str) -> str | None:
    """Return the YAML frontmatter section from markdown content."""
    if not content.startswith("---"):
        return None

    end = content.find("\n---", 3)
    if end == -1:
        return None

    return content[3:end].strip()
