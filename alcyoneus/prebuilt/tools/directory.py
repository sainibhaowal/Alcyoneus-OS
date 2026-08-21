"""Workspace-scoped directory listing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from alcyoneus.utils.decorators import tool


def _resolve(path: str, config: dict[str, Any] | None) -> tuple[Path, Path]:
    root = Path(str((config or {}).get("workspace_root") or ".")).expanduser().resolve()
    candidate = (root / (path or ".")).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise ValueError(f"path must stay inside workspace root: {root}") from None
    if not candidate.is_dir():
        raise ValueError(f"directory does not exist: {path}")
    return root, candidate


def _entry(path: Path, root: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": path.relative_to(root).as_posix(),
        "name": path.name,
        "type": "directory" if path.is_dir() else "file" if path.is_file() else "other",
        "size_bytes": stat.st_size if path.is_file() else None,
        "modified_at": stat.st_mtime,
    }


@tool(
    name="list_directory",
    description="List files and directories under the configured workspace root.",
    tags=["file", "filesystem", "directory"],
    capabilities=["read_files"],
)
def list_directory(
    path: str = ".",
    recursive: bool = False,
    include_hidden: bool = False,
    config: dict[str, Any] | None = None,
) -> str:
    """Return a bounded, workspace-scoped directory listing."""
    try:
        root, target = _resolve(path, config)
        iterator = target.rglob("*") if recursive else target.iterdir()
        entries = []
        for item in sorted(iterator, key=lambda p: (not p.is_dir(), p.name.lower())):
            if not include_hidden and item.name.startswith("."):
                continue
            try:
                item.resolve().relative_to(root)
            except ValueError:
                continue
            entries.append(_entry(item, root))
        return json.dumps({"root": target.relative_to(root).as_posix() or ".", "entries": entries})
    except Exception as exc:
        return json.dumps({"error": str(exc), "tool": "list_directory"})
