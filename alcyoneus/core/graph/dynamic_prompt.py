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

"""Dynamic prompt functions and types for runtime prompt rendering with Jinja2 templating.

This module provides a powerful Prompt class with full Jinja2 templating support
including conditionals, loops, filters, and custom extensions.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeAlias


try:
    import jinja2

    JINJA2_AVAILABLE = True
except ImportError:
    jinja2 = None  # type: ignore
    JINJA2_AVAILABLE = False


@dataclass
class GenerateDynamicPromptData:
    """Input payload passed to dynamic prompt generator functions.

    Attributes:
        agent_name: Name of the agent generating the prompt.
        context: Graph state context with messages, variables, etc.
        metadata: Additional metadata for prompt rendering.
    """

    agent_name: str
    context: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


DynamicPromptFunction: TypeAlias = Callable[[GenerateDynamicPromptData], str | Awaitable[str]]


class PromptTemplate:
    """Jinja2 template wrapper with sandboxed execution and custom filters."""

    def __init__(
        self,
        template: str,
        *,
        autoescape: bool = True,
        enable_async: bool = True,
        auto_reload: bool = False,
        cache_size: int = 400,
        custom_filters: dict[str, Callable] | None = None,
        custom_tests: dict[str, Callable] | None = None,
        custom_globals: dict[str, Any] | None = None,
        undefined: type = jinja2.StrictUndefined if JINJA2_AVAILABLE else None,
        lstrip_blocks: bool = True,
        trim_blocks: bool = True,
    ):
        if not JINJA2_AVAILABLE:
            raise RuntimeError(
                "Jinja2 is required for PromptTemplate. Install with: pip install jinja2"
            )

        self._template = template
        self._environment = jinja2.Environment(
            autoescape=jinja2.select_autoescape() if autoescape else False,
            enable_async=enable_async,
            auto_reload=auto_reload,
            cache_size=cache_size,
            lstrip_blocks=lstrip_blocks,
            trim_blocks=trim_blocks,
            undefined=undefined,
        )

        # Add custom filters
        default_filters = {
            "truncate": lambda s, length=100, suffix="...": (
                (s[:length] + suffix) if len(s) > length else s
            ),
            "word_count": lambda s: len(s.split()),
            "char_count": lambda s: len(s),
            "uppercase": str.upper,
            "lowercase": str.lower,
            "title_case": str.title,
            "slugify": lambda s: s.lower().replace(" ", "-").replace("_", "-"),
            "json_dumps": json.dumps,
            "json_loads": json.loads,
            "now": lambda fmt="%Y-%m-%d %H:%M:%S": datetime.now().strftime(fmt),
            "today": lambda fmt="%Y-%m-%d": datetime.now().strftime(fmt),
        }
        if custom_filters:
            default_filters.update(custom_filters)
        self._environment.filters.update(default_filters)

        # Add custom tests
        default_tests = {
            "empty": lambda v: not v,
            "blank": lambda v: not v or not str(v).strip(),
            "number": lambda v: isinstance(v, (int, float)),
            "string": lambda v: isinstance(v, str),
            "list": lambda v: isinstance(v, list),
            "dict": lambda v: isinstance(v, dict),
            "defined": lambda v: v is not None,
        }
        if custom_tests:
            default_tests.update(custom_tests)
        self._environment.tests.update(default_tests)

        # Add custom globals
        default_globals = {
            "now": datetime.now,
            "datetime": datetime,
            "date": datetime.now().date,
            "time": datetime.now().time,
            "len": len,
            "min": min,
            "max": max,
            "sum": sum,
            "sorted": sorted,
            "enumerate": enumerate,
            "range": range,
            "zip": zip,
        }
        if custom_globals:
            default_globals.update(custom_globals)
        self._environment.globals.update(default_globals)

        self._compiled = self._environment.from_string(template)

    def render(self, context: dict[str, Any], **kwargs) -> str:
        """Render the template synchronously."""
        merged = {**context, **kwargs}
        return self._compiled.render(merged)

    async def render_async(self, context: dict[str, Any], **kwargs) -> str:
        """Render the template asynchronously."""
        if not JINJA2_AVAILABLE:
            raise RuntimeError("Jinja2 not available")
        merged = {**context, **kwargs}
        return await self._compiled.render_async(merged)

    @property
    def template_source(self) -> str:
        return self._template


class Prompt:
    """A system prompt with full Jinja2 templating support.

    ``Prompt`` wraps either a plain string, a Jinja2 template string,
    or a ``DynamicPromptFunction`` callable. It supports:
    - Static strings (passed through as-is)
    - Jinja2 templates with conditionals, loops, filters, macros
    - Dynamic callable prompts that receive runtime context

    Attributes:
        content: The raw string, template string, or dynamic render function.
        template: Compiled PromptTemplate if using Jinja2, else None.

    Example:
        >>> from alcyoneus.core.graph import Prompt, GenerateDynamicPromptData
        >>> static = Prompt("You are a helpful assistant.")
        >>> template = Prompt("Hello {{ name }}! You have {{ messages|length }} messages.")
        >>> dynamic = Prompt(lambda d: f"Hi {d.context['user']}!")
        >>> async def render(p: Prompt, data: GenerateDynamicPromptData) -> str:
        ...     return await p.render(data)
    """

    def __init__(
        self,
        content: str | DynamicPromptFunction,
        *,
        jinja2_options: dict[str, Any] | None = None,
    ):
        if not (isinstance(content, str) or callable(content)):
            raise TypeError(
                "Prompt content must be a str or a DynamicPromptFunction callable; "
                f"got {type(content).__name__}."
            )

        self._content: str | DynamicPromptFunction = content
        self._jinja2_options = jinja2_options or {}
        self._template: PromptTemplate | None = None

        # Detect if string content is a Jinja2 template
        if isinstance(content, str) and JINJA2_AVAILABLE:
            # Check for Jinja2 syntax
            if any(marker in content for marker in ("{{", "{%", "{#")):
                self._template = PromptTemplate(content, **(self._jinja2_options or {}))
            else:
                # Plain string, no template compilation needed
                pass

    @property
    def content(self) -> str | DynamicPromptFunction:
        """The raw content (string or callable)."""
        return self._content

    @property
    def template(self) -> PromptTemplate | None:
        """The compiled Jinja2 template, if applicable."""
        return self._template

    @property
    def is_dynamic(self) -> bool:
        """Return True if this prompt is rendered at runtime from state context."""
        return callable(self._content) or self._template is not None

    @property
    def is_template(self) -> bool:
        """Return True if this prompt uses Jinja2 templating."""
        return self._template is not None

    @property
    def is_callable(self) -> bool:
        """Return True if this prompt is a callable."""
        return callable(self._content)

    async def render(self, data: GenerateDynamicPromptData) -> str:
        """Render the prompt to a string for the given context.

        Args:
            data: Runtime context (agent name + graph state + metadata).

        Returns:
            str: The rendered prompt text.

        Example:
            >>> prompt = Prompt("Hello {{ context.user }}!")
            >>> text = await prompt.render(GenerateDynamicPromptData("a", {"user": "Ravi"}))
            'Hello Ravi!'
        """
        if callable(self._content):
            # Callable prompt function
            result = self._content(data)
            if isinstance(result, Awaitable):
                return await result
            return result

        if self._template is not None:
            # Jinja2 template
            return await self._template.render_async(
                {
                    "agent_name": data.agent_name,
                    "context": data.context,
                    "metadata": data.metadata,
                }
            )

        # Static string
        return self._content

    def render_sync(self, data: GenerateDynamicPromptData) -> str:
        """Synchronous render (for non-async contexts)."""
        if callable(self._content):
            result = self._content(data)
            if isinstance(result, Awaitable):
                import asyncio

                return asyncio.run(result)
            return result

        if self._template is not None:
            return self._template.render(
                {
                    "agent_name": data.agent_name,
                    "context": data.context,
                    "metadata": data.metadata,
                }
            )

        return self._content

    def __str__(self) -> str:
        if isinstance(self._content, str):
            if self._template:
                return f"<template: {self._content[:50]}...>"
            return self._content
        return "<dynamic prompt>"

    def __repr__(self) -> str:
        if isinstance(self._content, str):
            return f"Prompt(template={self._content!r})"
        return f"Prompt(callable={self._content!r})"


def is_dynamic_prompt_function(value: Any) -> bool:
    """Return True if *value* is a DynamicPromptFunction callable (not a str)."""
    return callable(value) and not isinstance(value, str)


def as_prompt(
    value: str | DynamicPromptFunction | Prompt | None,
    *,
    jinja2_options: dict[str, Any] | None = None,
) -> Prompt | None:
    """Coerce a value into a Prompt (or None).

    Accepts a ``str``, a ``DynamicPromptFunction`` callable, an existing
    ``Prompt``, or ``None``.

    Args:
        value: The prompt value to coerce.
        jinja2_options: Optional Jinja2 template options.

    Returns:
        Prompt | None: A Prompt instance, or None when *value* is None.
    """
    if value is None:
        return None
    if isinstance(value, Prompt):
        return value
    return Prompt(value, jinja2_options=jinja2_options)


__all__ = [
    "DynamicPromptFunction",
    "GenerateDynamicPromptData",
    "Prompt",
    "PromptTemplate",
    "as_prompt",
    "is_dynamic_prompt_function",
]
