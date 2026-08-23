"""Metadata registry for built-in and user-provided Alcyoneus OS tools."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from alcyoneus.utils.decorators import get_tool_metadata


@dataclass(frozen=True)
class ToolDescriptor:
    name: str
    description: str
    schema: dict[str, Any]
    capabilities: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    provider: str = "local"
    safety_level: str = "normal"
    supports_cancellation: bool = True
    supports_streaming: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """Explicit registry that preserves callable compatibility with ToolNode."""

    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}
        self._descriptors: dict[str, ToolDescriptor] = {}

    def register(
        self, tool: Callable[..., Any], *, safety_level: str = "normal", provider: str | None = None
    ) -> Callable[..., Any]:
        metadata = get_tool_metadata(tool)
        name = metadata["name"] or tool.__name__
        signature = inspect.signature(tool)
        schema = {"type": "object", "properties": {}}
        required: list[str] = []
        for parameter in signature.parameters.values():
            if parameter.name in {"config", "state", "emit", "tool_call_id"} or parameter.kind in (
                parameter.VAR_POSITIONAL,
                parameter.VAR_KEYWORD,
            ):
                continue
            schema["properties"][parameter.name] = {"type": "string"}
            if parameter.default is parameter.empty:
                required.append(parameter.name)
        if required:
            schema["required"] = required
        self._tools[name] = tool
        self._descriptors[name] = ToolDescriptor(
            name=name,
            description=metadata["description"] or inspect.getdoc(tool) or "",
            schema=schema,
            capabilities=tuple(metadata["capabilities"] or ()),
            tags=tuple(sorted(metadata["tags"] or ())),
            provider=provider or metadata["provider"] or "local",
            safety_level=safety_level,
            supports_cancellation=not inspect.iscoroutinefunction(tool) or True,
            metadata=dict(metadata["metadata"] or {}),
        )
        return tool

    def get(self, name: str) -> Callable[..., Any]:
        return self._tools[name]

    def descriptor(self, name: str) -> ToolDescriptor:
        return self._descriptors[name]

    def descriptors(self) -> list[ToolDescriptor]:
        return list(self._descriptors.values())

    def tools(self) -> list[Callable[..., Any]]:
        return list(self._tools.values())
