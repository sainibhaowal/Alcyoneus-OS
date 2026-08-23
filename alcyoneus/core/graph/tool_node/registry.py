"""Unified metadata registry used by ToolNode."""

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
    """Registry of callables and metadata without changing ToolNode execution."""

    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}
        self._descriptors: dict[str, ToolDescriptor] = {}

    def register(self, function: Callable[..., Any], *, safety_level: str = "normal") -> None:
        metadata = get_tool_metadata(function)
        name = metadata["name"] or function.__name__
        properties: dict[str, Any] = {}
        required: list[str] = []
        for parameter in inspect.signature(function).parameters.values():
            if parameter.name in {"config", "state", "emit", "tool_call_id"} or parameter.kind in (
                parameter.VAR_POSITIONAL,
                parameter.VAR_KEYWORD,
            ):
                continue
            properties[parameter.name] = {"type": "string"}
            if parameter.default is parameter.empty:
                required.append(parameter.name)
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        self._tools[name] = function
        self._descriptors[name] = ToolDescriptor(
            name=name,
            description=metadata["description"] or inspect.getdoc(function) or "",
            schema=schema,
            capabilities=tuple(metadata["capabilities"] or ()),
            tags=tuple(sorted(metadata["tags"] or ())),
            provider=metadata["provider"] or "local",
            safety_level=safety_level,
            supports_cancellation=True,
            supports_streaming=bool((metadata["metadata"] or {}).get("streaming")),
            metadata=dict(metadata["metadata"] or {}),
        )

    def descriptors(self) -> list[ToolDescriptor]:
        return list(self._descriptors.values())

    def descriptor(self, name: str) -> ToolDescriptor:
        return self._descriptors[name]

    def get(self, name: str) -> Callable[..., Any]:
        return self._tools[name]
