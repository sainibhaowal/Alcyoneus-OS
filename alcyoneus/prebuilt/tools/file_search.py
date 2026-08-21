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

"""File Search (RAG) Tool for Alcyoneus OS.

Provides semantic and keyword search across workspace files and documents.
Features: semantic index build, incremental updates, multi-repo workspace.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import pickle
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from alcyoneus.utils.decorators import tool


@dataclass
class FileIndex:
    """Semantic search index for a workspace."""

    root: pathlib.Path
    chunk_size: int = 500
    overlap: int = 100
    embeddings_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    _chunks: dict[str, list[dict]] = field(default_factory=dict, repr=False)
    _embeddings: dict[str, list[list[float]]] = field(default_factory=dict, repr=False)
    _file_hashes: dict[str, str] = field(default_factory=dict, repr=False)
    _model = None

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.embeddings_model)
            except ImportError:
                raise RuntimeError(
                    "sentence-transformers required: pip install sentence-transformers"
                )
        return self._model

    def _file_hash(self, path: pathlib.Path) -> str:
        return hashlib.md5(path.read_bytes()).hexdigest()  # noqa: S324

    def _chunk_text(self, text: str) -> list[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunks.append(text[start:end])
            start += self.chunk_size - self.overlap
        return chunks

    def index_path(self, path: pathlib.Path, extensions: set[str]) -> int:
        """Index a single file, return number of chunks added."""
        if not path.is_file() or path.suffix.lower() not in extensions:
            return 0
        if any(
            part.startswith(".") or part in ("__pycache__", "node_modules", "venv", ".venv")
            for part in path.parts
        ):
            return 0
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return 0

        file_hash = self._file_hash(path)
        if self._file_hashes.get(str(path)) == file_hash:
            return 0  # Unchanged

        chunks = self._chunk_text(content)
        rel = str(path.relative_to(self.root))
        self._chunks[rel] = [
            {"text": c, "line": content.count("\n", 0, i * (self.chunk_size - self.overlap)) + 1}
            for i, c in enumerate(chunks)
        ]
        model = self._get_model()
        self._embeddings[rel] = model.encode([c["text"] for c in self._chunks[rel]]).tolist()
        self._file_hashes[str(path)] = file_hash
        return len(chunks)

    async def build_index(self, extensions: set[str] | None = None, progress_cb=None) -> dict:
        """Build full index for workspace."""
        ext = extensions or {
            ".py",
            ".md",
            ".txt",
            ".json",
            ".yaml",
            ".yml",
            ".rst",
            ".html",
            ".js",
            ".ts",
            ".go",
            ".rs",
            ".java",
        }
        self._chunks.clear()
        self._embeddings.clear()
        self._file_hashes.clear()
        total_chunks = 0
        files = [p for p in self.root.rglob("*") if p.is_file()]
        for i, f in enumerate(files):
            n = self.index_path(f, ext)
            total_chunks += n
            if progress_cb:
                await progress_cb(i + 1, len(files), f)
        return {"files_indexed": len(self._chunks), "total_chunks": total_chunks}

    async def incremental_update(
        self, changed_files: list[pathlib.Path], extensions: set[str] | None = None
    ) -> dict:
        """Update index for changed files only."""
        ext = extensions or {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".rst", ".html"}
        updated = 0
        removed = 0
        for f in changed_files:
            if f.exists():
                self.index_path(f, ext)
                updated += 1
            else:
                # File deleted - remove from index
                rel = str(f.relative_to(self.root)) if f.is_relative_to(self.root) else str(f)
                self._chunks.pop(rel, None)
                self._embeddings.pop(rel, None)
                self._file_hashes.pop(str(f), None)
                removed += 1
        return {"updated": updated, "removed": removed}

    def search(self, query: str, top_k: int = 5, threshold: float = 0.3) -> list[dict]:
        """Semantic search using embeddings."""
        if not self._embeddings:
            return []
        model = self._get_model()
        q_emb = model.encode([query])[0]
        results = []
        for rel, embs in self._embeddings.items():
            import numpy as np

            sims = np.dot(embs, q_emb) / (
                np.linalg.norm(embs, axis=1) * np.linalg.norm(q_emb) + 1e-8
            )
            for i, score in enumerate(sims):
                if score >= threshold:
                    chunk = self._chunks[rel][i]
                    results.append(
                        {
                            "path": rel,
                            "chunk_index": i,
                            "line": chunk["line"],
                            "score": float(score),
                            "snippet": chunk["text"][:200],
                        }
                    )
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]

    def keyword_search(self, query: str, top_k: int = 5) -> list[dict]:
        """Fallback keyword search."""
        query_terms = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 2]
        if not query_terms:
            query_terms = [query.lower()]
        results = []
        for rel, chunks in self._chunks.items():
            for i, chunk in enumerate(chunks):
                text = chunk["text"].lower()
                score = sum(text.count(t) for t in query_terms)
                if score > 0:
                    results.append(
                        {
                            "path": rel,
                            "chunk_index": i,
                            "line": chunk["line"],
                            "score": score,
                            "snippet": chunk["text"][:200],
                        }
                    )
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]

    def save(self, path: pathlib.Path) -> None:
        """Persist index to disk."""
        data = {
            "chunks": self._chunks,
            "embeddings": self._embeddings,
            "file_hashes": self._file_hashes,
            "chunk_size": self.chunk_size,
            "overlap": self.overlap,
            "embeddings_model": self.embeddings_model,
        }
        path.write_bytes(pickle.dumps(data))

    @classmethod
    def load(cls, path: pathlib.Path, root: pathlib.Path) -> FileIndex:
        """Load index from disk."""
        data = pickle.loads(path.read_bytes())  # noqa: S301
        idx = cls(
            root=root,
            chunk_size=data["chunk_size"],
            overlap=data["overlap"],
            embeddings_model=data["embeddings_model"],
        )
        idx._chunks = data["chunks"]
        idx._embeddings = data["embeddings"]
        idx._file_hashes = data["file_hashes"]
        return idx


# Global index cache per workspace root
_INDEX_CACHE: dict[str, FileIndex] = {}


def _get_index(root: pathlib.Path, chunk_size: int = 500, overlap: int = 100) -> FileIndex:
    key = str(root.resolve())
    if key not in _INDEX_CACHE:
        _INDEX_CACHE[key] = FileIndex(root=root, chunk_size=chunk_size, overlap=overlap)
    return _INDEX_CACHE[key]


@tool(
    name="file_search", description="Search workspace files with semantic or keyword search (RAG)."
)
def file_search(
    query: str,
    path: str = ".",
    search_path: str | None = None,
    file_extensions: Sequence[str] | None = None,
    top_k: int = 5,
    use_semantic: bool = True,
    config: dict[str, Any] | None = None,
) -> str:
    """Searches workspace files for relevant snippets.

    Args:
        query: Search query or keywords.
        path: Directory path to search within. Defaults to current directory.
        search_path: Directory path to search within (preferred name).
        file_extensions: Optional list of extensions to include.
        top_k: Maximum number of search results to return.
        use_semantic: Use semantic embeddings search (requires sentence-transformers).
        config: Optional execution config with file_tool_root, index_cache_path.

    Returns:
        JSON string containing matching file snippets with relevance scores.
    """
    import asyncio

    async def _async_search() -> str:
        search_dir = search_path if search_path is not None else path
        workspace_root: pathlib.Path | None = None
        if config and config.get("file_tool_root"):
            workspace_root = pathlib.Path(config["file_tool_root"]).resolve()
            search_dir = (
                str(workspace_root / search_dir)
                if not pathlib.Path(search_dir).is_absolute()
                else search_dir
            )
        root_dir = pathlib.Path(search_dir).resolve()
        if not root_dir.exists():
            return json.dumps({"error": f"Search path does not exist: {search_dir}", "results": []})

        # Use workspace_root as the base for relative paths (for consistency with file_read/file_write)  # noqa: E501
        base_dir = workspace_root if workspace_root else root_dir

        extensions = (
            set(file_extensions)
            if file_extensions
            else {
                ".py",
                ".md",
                ".txt",
                ".json",
                ".yaml",
                ".yml",
                ".rst",
                ".html",
                ".js",
                ".ts",
                ".go",
                ".rs",
                ".java",
            }
        )

        index = _get_index(base_dir)

        # Check if index needs building/updating
        index_cache_path = config.get("index_cache_path") if config else None
        if index_cache_path:
            cache_file = pathlib.Path(index_cache_path)
            if cache_file.exists():
                try:
                    index = FileIndex.load(cache_file, base_dir)
                    _INDEX_CACHE[str(base_dir.resolve())] = index
                except Exception:  # noqa: S110
                    pass

        # Build index if empty
        if not index._chunks:
            await index.build_index(extensions)
            if index_cache_path:
                index.save(cache_file)

        if use_semantic:
            results = index.search(query, top_k=top_k)
        else:
            results = index.keyword_search(query, top_k=top_k)

        # Convert paths to be relative to search_dir for consistency
        search_path_obj = pathlib.Path(search_dir).resolve()
        for result in results:
            if "path" in result:
                try:
                    result["path"] = str(pathlib.Path(result["path"]).relative_to(search_path_obj))
                except ValueError:
                    pass  # Keep original path if not relative

        return json.dumps(
            {
                "query": query,
                "total_matches": len(results),
                "results": results,
            },
            ensure_ascii=False,
        )

    # Run async function in sync context
    try:
        loop = asyncio.get_running_loop()
        # We're in an async context, create a task
        return asyncio.run_coroutine_threadsafe(_async_search(), loop).result()
    except RuntimeError:
        # No running loop, safe to use asyncio.run
        return asyncio.run(_async_search())


@tool(
    name="file_search_build_index",
    description="Build or rebuild semantic search index for workspace.",
)
async def file_search_build_index(
    search_path: str = ".",
    chunk_size: int = 500,
    overlap: int = 100,
    config: dict[str, Any] | None = None,
) -> str:
    """Build semantic search index for workspace."""
    root_dir = pathlib.Path(search_path).resolve()
    if config and config.get("file_tool_root"):
        root_dir = pathlib.Path(config["file_tool_root"]).resolve() / root_dir.relative_to(
            pathlib.Path.cwd()
        )
    if not root_dir.exists():
        return json.dumps({"error": f"Path does not exist: {search_path}"})

    index = _get_index(root_dir, chunk_size=chunk_size, overlap=overlap)
    result = await index.build_index()
    if config and config.get("index_cache_path"):
        index.save(pathlib.Path(config["index_cache_path"]))
    return json.dumps({"status": "built", **result})


@tool(
    name="file_search_update_index",
    description="Incrementally update search index for changed files.",
)
async def file_search_update_index(
    changed_files: list[str],
    search_path: str = ".",
    config: dict[str, Any] | None = None,
) -> str:
    """Update index incrementally for changed files."""
    root_dir = pathlib.Path(search_path).resolve()
    if config and config.get("file_tool_root"):
        root_dir = pathlib.Path(config["file_tool_root"]).resolve() / root_dir.relative_to(
            pathlib.Path.cwd()
        )
    index = _get_index(root_dir)
    changed = [pathlib.Path(f) for f in changed_files]
    result = await index.incremental_update(changed)
    if config and config.get("index_cache_path"):
        index.save(pathlib.Path(config["index_cache_path"]))
    return json.dumps({"status": "updated", **result})


@tool(name="file_search_multi_repo", description="Search across multiple repositories/workspaces.")
async def file_search_multi_repo(
    query: str,
    repos: list[str],
    top_k: int = 5,
    use_semantic: bool = True,
) -> str:
    """Search across multiple repositories."""
    all_results = []
    for repo in repos:
        root = pathlib.Path(repo).resolve()
        if not root.exists():
            continue
        index = _get_index(root)
        if not index._chunks:
            await index.build_index()
        if use_semantic:
            results = index.search(query, top_k=top_k)
        else:
            results = index.keyword_search(query, top_k=top_k)
        for r in results:
            r["repo"] = str(root)
        all_results.extend(results)
    all_results.sort(key=lambda r: r["score"], reverse=True)
    return json.dumps(
        {"query": query, "total_matches": len(all_results), "results": all_results[:top_k]}
    )


class FileSearchTool:
    """Class wrapper for File Search (RAG) tool."""

    def __init__(self, search_path: str = ".") -> None:
        self.search_path = search_path

    def __call__(self, query: str, top_k: int = 5) -> dict[str, Any]:
        return file_search(query=query, search_path=self.search_path, top_k=top_k)


__all__ = [
    "FileIndex",
    "FileSearchTool",
    "file_search",
    "file_search_build_index",
    "file_search_multi_repo",
    "file_search_update_index",
]
