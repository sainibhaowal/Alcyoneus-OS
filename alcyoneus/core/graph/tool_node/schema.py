"""Schema utilities and local tool description building for ToolNode.

This module provides the SchemaMixin class which handles automatic schema generation
for local Python functions, converting their type annotations and signatures into
OpenAI-compatible function schemas. It supports various Python types including
primitives, Optional types, List types, and Literal enums.

The schema generation process inspects function signatures and converts them to
JSON Schema format suitable for use with language models and function calling APIs.
"""

from __future__ import annotations

import inspect
import typing as t

from .constants import is_injected_param


class SchemaMixin:
    """Mixin providing schema generation and local tool description building.

    This mixin provides functionality to automatically generate JSON Schema definitions
    from Python function signatures. It handles type annotation conversion, parameter
    analysis, and OpenAI-compatible function schema generation for local tools.

    The mixin is designed to be used with ToolNode to automatically generate tool
    schemas without requiring manual schema definition for Python functions.

    Attributes:
        _funcs: Dictionary mapping function names to callable functions. This
            attribute is expected to be provided by the mixing class.
    """

    _funcs: dict[str, t.Callable]

    @staticmethod
    def _handle_optional_annotation(annotation: t.Any, default: t.Any) -> dict | None:
        """Handle Optional type annotations and convert them to appropriate schemas.

        Processes Optional[T] type annotations (Union[T, None]) and generates
        schema for the non-None type. This method handles the common pattern
        of optional parameters in function signatures.

        Args:
            annotation: The type annotation to process, potentially an Optional type.
            default: The default value for the parameter, used for schema generation.

        Returns:
            Dictionary containing the JSON schema for the non-None type if the
            annotation is Optional, None otherwise.

        Example:
            Optional[str] -> {"type": "string"}
            Optional[int] -> {"type": "integer"}
        """
        args = getattr(annotation, "__args__", None)
        if args and any(a is type(None) for a in args):
            non_none = [a for a in args if a is not type(None)]
            if non_none:
                return SchemaMixin._annotation_to_schema(non_none[0], default)
        return None

    @staticmethod
    def _handle_complex_annotation(annotation: t.Any) -> dict:
        """Handle complex type annotations like List, Literal, and generic types.

        Processes generic type annotations that aren't simple primitive types,
        including container types like List and special types like Literal enums.
        Falls back to string type for unrecognized complex types.

        Args:
            annotation: The complex type annotation to process (e.g., List[str],
                Literal["a", "b", "c"]).

        Returns:
            Dictionary containing the appropriate JSON schema for the complex type.
            For List types, returns array schema with item type.
            For Literal types, returns enum schema with allowed values.
            For unknown types, returns string type as fallback.

        Example:
            List[str] -> {"type": "array", "items": {"type": "string"}}
            Literal["red", "green"] -> {"type": "string", "enum": ["red", "green"]}
        """
        origin = getattr(annotation, "__origin__", None)
        if origin is list:
            item_type = getattr(annotation, "__args__", (str,))[0]
            item_schema = SchemaMixin._annotation_to_schema(item_type, None)
            return {"type": "array", "items": item_schema}

        Literal = getattr(t, "Literal", None)
        if Literal is not None and origin is Literal:
            literals = list(getattr(annotation, "__args__", ()))
            if all(isinstance(literal, str) for literal in literals):
                return {"type": "string", "enum": literals}
            return {"enum": literals}

        return {"type": "string"}

    @staticmethod
    def _annotation_to_schema(annotation: t.Any, default: t.Any) -> dict:
        """Convert a Python type annotation to JSON Schema format.

        Main entry point for type annotation conversion. Handles both simple
        and complex types by delegating to appropriate helper methods.
        Includes default value handling when present.

        Args:
            annotation: The Python type annotation to convert (e.g., str, int,
                Optional[str], List[int]).
            default: The default value for the parameter, included in schema
                if not inspect._empty.

        Returns:
            Dictionary containing the JSON schema representation of the type
            annotation, including default values where applicable.

        Example:
            str -> {"type": "string"}
            int -> {"type": "integer"}
            str with default "hello" -> {"type": "string", "default": "hello"}
        """
        schema = SchemaMixin._handle_optional_annotation(annotation, default)
        if schema:
            return schema

        primitive_mappings = {
            str: {"type": "string"},
            int: {"type": "integer"},
            float: {"type": "number"},
            bool: {"type": "boolean"},
        }

        if annotation in primitive_mappings:
            schema = primitive_mappings[annotation]
        else:
            schema = SchemaMixin._handle_complex_annotation(annotation)

        if default is not inspect._empty:
            schema["default"] = default

        return schema

    def get_local_tool(
        self,
        tags: set[str] | None = None,
    ) -> list[dict]:
        """Generate OpenAI-compatible tool definitions for all registered local functions.

        Inspects all registered functions in _funcs and automatically generates
        tool schemas by analyzing function signatures, type annotations, and docstrings.
        Excludes injectable parameters that are provided by the framework.

        Returns:
            List of tool definitions in OpenAI function calling format. Each
            definition includes the function name, description (from docstring),
            and complete parameter schema with types and required fields.

        Example:
            For a function:
            ```python
            def calculate(a: int, b: int, operation: str = "add") -> int:
                '''Perform arithmetic calculation.'''
                return a + b if operation == "add" else a - b
            ```

            Returns:
            ```python
            [
                {
                    "type": "function",
                    "function": {
                        "name": "calculate",
                        "description": "Perform arithmetic calculation.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "a": {"type": "integer"},
                                "b": {"type": "integer"},
                                "operation": {"type": "string", "default": "add"},
                            },
                            "required": ["a", "b"],
                        },
                    },
                }
            ]
            ```

        Note:
            Parameters listed in INJECTABLE_PARAMS (like 'state', 'config',
            'tool_call_id') are automatically excluded from the generated schema
            as they are provided by the framework during execution.
        """
        tools: list[dict] = []
        for name, fn in self._funcs.items():
            sig = inspect.signature(fn)
            params_schema: dict = {"type": "object", "properties": {}, "required": []}

            for p_name, p in sig.parameters.items():
                if p.kind in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ):
                    continue

                if is_injected_param(p_name, p):
                    continue

                annotation = p.annotation if p.annotation is not inspect._empty else str
                prop = SchemaMixin._annotation_to_schema(annotation, p.default)
                params_schema["properties"][p_name] = prop

                if p.default is inspect._empty:
                    params_schema["required"].append(p_name)

            if not params_schema["required"]:
                params_schema.pop("required")

            # Use decorator metadata if available, otherwise fall back to defaults
            tool_name = getattr(fn, "_py_tool_name", name)
            description = getattr(fn, "_py_tool_description", None)
            if description is None:
                description = inspect.getdoc(fn) or "No description provided."

            # provider = getattr(fn, "_py_tool_provider", None)
            fun_tags = getattr(fn, "_py_tool_tags", None)
            capabilities = getattr(fn, "_py_tool_capabilities", None)
            if tags and fun_tags and tags.isdisjoint(fun_tags):
                continue

            entry = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": description,
                    "parameters": params_schema,
                },
            }
            if capabilities is not None:
                entry["function"]["x-function-capabilities"] = capabilities
            # meta: dict[str, t.Any] = {}
            # if provider:
            #     meta["provider"] = provider
            # if tags:
            #     meta["tags"] = tags
            # if capabilities:
            #     meta["capabilities"] = capabilities
            # if meta:
            #     entry["x-alcyoneus"] = meta

            tools.append(entry)

        return tools
