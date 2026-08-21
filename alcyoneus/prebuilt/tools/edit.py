"""Atomic workspace file editing and patch application."""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any, Literal

from alcyoneus.utils.decorators import tool


def _target(path: str, config: dict[str, Any] | None) -> tuple[Path, Path]:
    root = Path(str((config or {}).get("workspace_root") or ".")).expanduser().resolve()
    target = (root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError(f"path must stay inside workspace root: {root}") from None
    return root, target


def _atomic_write(target: Path, text: str) -> None:
    temporary = target.with_name(f".{target.name}.alcyoneus-tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(target)


def _apply_unified_diff(original: str, patch: str) -> str:
    """Apply a standard unified diff and reject context conflicts."""
    source = original.splitlines(keepends=True)
    diff_lines = patch.splitlines(keepends=True)
    hunks = [i for i, line in enumerate(diff_lines) if line.startswith("@@ ")]
    if not hunks:
        raise ValueError("patch contains no unified diff hunks")
    output: list[str] = []
    source_index = 0
    for hunk_index, header_index in enumerate(hunks):
        match = re.match(
            r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", diff_lines[header_index].rstrip("\n")
        )
        if not match:
            raise ValueError("invalid unified diff hunk header")
        old_start = int(match.group(1)) - 1
        output.extend(source[source_index:old_start])
        source_index = old_start
        end = hunks[hunk_index + 1] if hunk_index + 1 < len(hunks) else len(diff_lines)
        for line in diff_lines[header_index + 1 : end]:
            if line.startswith("\\ No newline"):
                continue
            if not line:
                raise ValueError("invalid empty diff line")
            marker, content = line[0], line[1:]
            if marker == " ":
                if source_index >= len(source) or source[source_index] != content:
                    raise ValueError("patch context conflict")
                output.append(source[source_index])
                source_index += 1
            elif marker == "-":
                if source_index >= len(source) or source[source_index] != content:
                    raise ValueError("patch removal conflict")
                source_index += 1
            elif marker == "+":
                output.append(content)
            else:
                raise ValueError("invalid unified diff line")
    output.extend(source[source_index:])
    return "".join(output)


@tool(
    name="edit_file",
    description="Apply an exact replacement or unified diff to a workspace file atomically.",
    tags=["file", "filesystem", "edit"],
    capabilities=["write_files"],
)
def edit_file(
    path: str,
    operation: Literal["replace", "patch"] = "replace",
    old_text: str | None = None,
    new_text: str | None = None,
    patch: str | None = None,
    config: dict[str, Any] | None = None,
) -> str:
    """Edit a text file with conflict checks and atomic replacement."""
    try:
        _, target = _target(path, config)
        if not target.is_file():
            raise FileNotFoundError(path)
        before = target.read_text(encoding="utf-8")
        if operation == "replace":
            if old_text is None or new_text is None:
                raise ValueError("old_text and new_text are required for replace")
            count = before.count(old_text)
            if count != 1:
                raise ValueError(f"expected exactly one match, found {count}")
            after = before.replace(old_text, new_text, 1)
        else:
            if not patch:
                raise ValueError("patch is required for patch operation")
            after = _apply_unified_diff(before, patch)
        _atomic_write(target, after)
        return json.dumps(
            {
                "status": "edited",
                "path": path,
                "diff": "".join(
                    difflib.unified_diff(before.splitlines(True), after.splitlines(True))
                ),
            }
        )
    except Exception as exc:
        return json.dumps({"error": str(exc), "tool": "edit_file"})
