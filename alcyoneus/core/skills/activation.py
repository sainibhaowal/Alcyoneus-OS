"""Skill tools for Alcyoneus OS.

Provides a factory function that creates the ``set_skill`` tool the LLM can
call to load skill content and resources on demand.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from alcyoneus.core.skills.registry import SkillsRegistry


logger = logging.getLogger("alcyoneus.skills.activation")


def make_set_skill_tool(
    registry: SkillsRegistry,
    hot_reload: bool = True,
) -> Callable:
    """Factory that returns a ``set_skill`` function whose doc-string
    lists the available skills.

    The tool can load:
    - Skill instructions: set_skill("code-review")
    - Specific resource: set_skill("code-review", "style-guide.md")
    """

    available = registry.get_all()
    skill_list = "\n".join(f"- {m.name}: {m.description}" for m in available)

    def set_skill(skill_name: str, resource: str | None = None) -> str:  # noqa: PLR0911
        """Load a skill's instructions or a specific resource.

        Args:
            skill_name: Name of the skill to load.
            resource: Optional. If provided, loads this specific resource file
                instead of the skill instructions.
        """
        names_str = ", ".join(registry.names())
        meta = registry.get(skill_name)
        if meta is None:
            logger.warning("Unknown skill requested: %r. Available: %s", skill_name, names_str)
            return f"ERROR: Unknown skill '{skill_name}'. Available: {names_str}"

        # If resource is specified, load that specific resource
        if resource:
            if not meta.resources:
                return f"ERROR: Skill '{skill_name}' has no resources."

            # Prefer exact relative-path matches first.
            exact_matches = [res_path for res_path in meta.resources if res_path == resource]
            if exact_matches:
                matching_resource = exact_matches[0]
            else:
                # Support filename-only lookup when uniquely identifiable.
                basename_matches = [
                    res_path for res_path in meta.resources if Path(res_path).name == resource
                ]
                if len(basename_matches) == 1:
                    matching_resource = basename_matches[0]
                elif len(basename_matches) > 1:
                    options = ", ".join(sorted(basename_matches))
                    return (
                        f"ERROR: Resource '{resource}' is ambiguous. "
                        f"Use an exact path. Matches: {options}"
                    )
                else:
                    matching_resource = None

            if matching_resource is None:
                available_res = ", ".join(meta.resources)
                return f"ERROR: Resource '{resource}' not found. Available: {available_res}"

            from alcyoneus.core.skills.loader import load_resource

            content = load_resource(meta, matching_resource)

            if content is None:
                return f"ERROR: Could not load resource '{matching_resource}'."

            logger.info("Resource loaded: '%s' from skill '%s'", matching_resource, skill_name)
            return f"## Resource: {resource}\n\n{content}"

        # Load the skill content
        logger.info("Skill loaded via tool: '%s'", skill_name)

        content = registry.load_content(skill_name, hot_reload=hot_reload)
        if not content:
            return f"ERROR: Skill '{skill_name}' found but content could not be loaded."

        header = skill_name.upper().replace("-", " ")
        return f"## SKILL: {header}\n\n{content}"

    # Patch the docstring so the LLM sees available skills
    set_skill.__doc__ = (
        "Load a skill's instructions or a specific resource.\n\n"
        "Call this tool when the user's request matches a skill domain.\n\n"
        f"Available skills:\n{skill_list}\n\n"
        "Args:\n"
        "    skill_name: Name of the skill to load.\n"
        "    resource: Optional. If provided, loads this specific resource file "
        "instead of the skill instructions."
    )
    return set_skill
