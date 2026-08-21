# Copyright 2026 Alcyoneus Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""ApplyPatch Tool for applying git/unified diff patches to files.

Hardened with a real unified-diff parser and application engine that:
- Parses ``---``/``+++`` file headers and hunks with line counts
- Applies hunks with context-matching (like ``patch``/``git apply``)
- Detects conflicts (context does not match current file content)
- Writes atomically and reports per-file results
"""

from __future__ import annotations

import difflib
import os
import pathlib
import re
import tempfile
from dataclasses import dataclass, field


_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")
_FILE_HEADER = re.compile(r"^(---|\+\+\+) (\S+)")


def _clean_path(path_str: str) -> str:
    """Strip a/, b/, or timestamps from a diff path."""
    path_str = path_str.split("\t", maxsplit=1)[0].split(" ", maxsplit=1)[0]
    for prefix in ("a/", "b/"):
        if path_str.startswith(prefix):
            path_str = path_str[len(prefix) :]
            break
    return path_str


@dataclass
class ApplyPatchOperation:
    """Single hunk operation within a diff patch."""

    file_path: str
    diff: str


@dataclass
class ApplyPatchResult:
    """Result of applying a unified diff patch to target files."""

    success: bool
    modified_files: list[str]
    errors: list[str]
    conflicts: list[str] = field(default_factory=list)


def _parse_patch(patch: str) -> dict[str, list[tuple[int, list[str]]]]:
    """Parse a unified diff into {filename: [(hunk_start_line, hunk_lines)]}.

    Returns:
        A mapping of file path to hunks. Each hunk is ``(start_line, lines)``
        where ``start_line`` is the 1-based new-file line the hunk applies at.
    """
    files: dict[str, list[tuple[int, list[str]]]] = {}
    current_file: str | None = None
    in_hunk = False
    saw_hunk = False
    hunk_start = 0
    hunk_lines: list[str] = []

    def _flush():
        nonlocal in_hunk, saw_hunk, hunk_lines
        if current_file and saw_hunk:
            files.setdefault(current_file, []).append((hunk_start, list(hunk_lines)))
        in_hunk = False
        saw_hunk = False
        hunk_lines = []

    for raw in patch.splitlines():
        line = raw

        header = _FILE_HEADER.match(line)
        if header and header.group(1) == "---":
            # previous hunk flush
            _flush()
            # Parse the target path (skip timestamps)
            rest = line[4:].strip()
            path_str = _clean_path(rest)
            if path_str in ("/dev/null", "a/dev/null", "b/dev/null"):
                current_file = None
            else:
                current_file = path_str
            continue

        if line.startswith("+++ "):
            # New file header: use as target when --- was /dev/null
            if current_file is None:
                rest = line[4:].strip()
                path_str = _clean_path(rest)
                if path_str not in ("/dev/null", "a/dev/null", "b/dev/null"):
                    current_file = path_str
            continue

        hunk_header = _HUNK_HEADER.match(line)
        if hunk_header:
            _flush()
            in_hunk = True
            saw_hunk = True
            # new start line
            hunk_start = int(hunk_header.group(3))
            continue

        if in_hunk:
            hunk_lines.append(line)

    _flush()

    return files


def _apply_hunks(original: str, hunks: list[tuple[int, list[str]]]) -> tuple[str, list[str]]:
    """Apply parsed hunks to file content with conflict detection.

    Returns:
        ``(new_content, conflict_reasons)``. On conflict the original content
        is returned unchanged for the offending hunk range.
    """
    lines = original.splitlines(keepends=True)
    conflicts: list[str] = []

    # Normalize file lines for comparison (hunk lines have no trailing newline).
    content_lines = [line.rstrip("\r\n") for line in lines]

    # Apply hunks in reverse order (bottom-up) so line offsets stay valid.
    for hunk_start, hunk_lines in sorted(hunks, key=lambda h: h[0], reverse=True):
        # Split hunk into -/+ and context
        old_lines: list[str] = []
        new_lines: list[str] = []
        for hl in hunk_lines:
            if hl.startswith("-"):
                old_lines.append(hl[1:])
            elif hl.startswith("+"):
                new_lines.append(hl[1:])
            else:
                old_lines.append(hl[1:])
                new_lines.append(hl[1:])

        # Search for matching context from hunk_start (0-based = start-1)
        idx = hunk_start - 1
        match_idx = None
        window = len(old_lines)
        if window == 0:
            # Pure-addition hunk: insert at the requested position (clamped).
            match_idx = min(max(idx, 0), len(content_lines))
        else:
            # Try exact position first, then scan nearby
            for candidate in range(max(0, idx - window), min(len(content_lines), idx + window + 1)):
                if content_lines[candidate : candidate + window] == old_lines:
                    match_idx = candidate
                    break

        if match_idx is None:
            conflicts.append(f"hunk at line {hunk_start} does not match file content")
            continue

        lines[match_idx : match_idx + window] = [
            line + "\n" if not line.endswith("\n") else line for line in new_lines
        ]
        content_lines[match_idx : match_idx + window] = new_lines

    return "".join(lines), conflicts


def _diff_to_patch(original: str, updated: str, file_path: str) -> str:
    """Generate a unified diff string (for reporting/verification)."""
    original_lines = original.splitlines(keepends=True)
    updated_lines = updated.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            original_lines,
            updated_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )
    )


class ApplyPatchTool:
    """Tool class for editing files via unified diff patch strings."""

    def __init__(self, workspace_dir: str = ".") -> None:
        self.workspace_dir = pathlib.Path(workspace_dir).resolve()

    def _resolve_path(self, file_path: str) -> pathlib.Path:
        """Resolve a patch path safely inside the workspace."""
        p = (self.workspace_dir / file_path).resolve()
        if not p.is_relative_to(self.workspace_dir):
            raise ValueError(f"path escapes workspace: {file_path}")
        return p

    def apply_patch(self, patch: str) -> ApplyPatchResult:
        """Apply a unified diff patch string to files.

        Args:
            patch: A unified diff (git or plain) string.

        Returns:
            An ApplyPatchResult with success flag, modified files, errors,
            and any conflict reports.
        """
        files = _parse_patch(patch)
        if not files:
            return ApplyPatchResult(
                success=False,
                modified_files=[],
                errors=["no valid diff hunks found in patch"],
            )

        modified: list[str] = []
        errors: list[str] = []
        conflicts: list[str] = []

        for file_path, hunks in files.items():
            try:
                resolved = self._resolve_path(file_path)
            except ValueError as err:
                errors.append(str(err))
                continue

            if not resolved.exists():
                # Creating a new file — assume empty base.
                original = ""
            else:
                try:
                    original = resolved.read_text(encoding="utf-8")
                except OSError as err:
                    errors.append(f"{file_path}: {err}")
                    continue

            new_content, file_conflicts = _apply_hunks(original, hunks)
            if file_conflicts:
                conflicts.extend(f"{file_path}: {c}" for c in file_conflicts)
                errors.append(f"{file_path}: patch does not apply cleanly")
                continue

            # Atomic write
            try:
                resolved.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(dir=str(resolved.parent), suffix=".patch-tmp")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as fh:
                        fh.write(new_content)
                    os.replace(tmp, resolved)
                finally:
                    if os.path.exists(tmp):
                        os.unlink(tmp)
            except OSError as err:
                errors.append(f"{file_path}: {err}")
                continue

            modified.append(file_path)

        return ApplyPatchResult(
            success=not errors,
            modified_files=modified,
            errors=errors,
            conflicts=conflicts,
        )

    def create_patch(self, file_path: str, updated_content: str) -> str:
        """Generate a unified diff for a proposed change (no write)."""
        try:
            resolved = self._resolve_path(file_path)
        except ValueError as err:
            raise ValueError(str(err)) from err
        original = resolved.read_text(encoding="utf-8") if resolved.exists() else ""
        return _diff_to_patch(original, updated_content, file_path)


def apply_diff(file_path: str, diff_content: str, workspace_dir: str = ".") -> str:
    """Functional utility to apply a patch diff to a single file.

    Args:
        file_path: Path of the target file (relative to workspace_dir).
        diff_content: Unified diff string.
        workspace_dir: Root directory that file_path is scoped to.

    Returns:
        A JSON string describing the result of the apply.
    """
    import json

    tool = ApplyPatchTool(workspace_dir=workspace_dir)
    result = tool.apply_patch(diff_content)
    return json.dumps(
        {
            "success": result.success,
            "modified_files": result.modified_files,
            "errors": result.errors,
            "conflicts": result.conflicts,
        },
        default=str,
    )


__all__ = [
    "ApplyPatchOperation",
    "ApplyPatchResult",
    "ApplyPatchTool",
    "apply_diff",
]
