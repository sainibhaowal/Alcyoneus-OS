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

"""JSON Schema validation and strictness enforcement utilities."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any


def ensure_strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Mutate and return a JSON schema enforcing `additionalProperties: false`."""
    strict_schema = dict(schema)
    if strict_schema.get("type") == "object":
        strict_schema["additionalProperties"] = False
        if "properties" in strict_schema and isinstance(strict_schema["properties"], dict):
            for k, prop in list(strict_schema["properties"].items()):
                if isinstance(prop, dict) and prop.get("type") == "object":
                    strict_schema["properties"][k] = ensure_strict_json_schema(prop)
    return strict_schema


def function_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """Auto-generate JSON schema dictionary from function signature."""
    from alcyoneus.prebuilt.tools.injected import is_injected_param

    sig = inspect.signature(func)
    properties = {}
    required = []

    for name, param in sig.parameters.items():
        if name in ("self", "cls") or is_injected_param(param):
            continue
        param_type = "string"
        if param.annotation is int:
            param_type = "integer"
        elif param.annotation is float:
            param_type = "number"
        elif param.annotation is bool:
            param_type = "boolean"
        elif param.annotation is dict:
            param_type = "object"
        elif param.annotation is list:
            param_type = "array"

        properties[name] = {"type": param_type}
        if param.default == inspect.Parameter.empty:
            required.append(name)

    return {
        "name": getattr(func, "__name__", "function"),
        "description": (getattr(func, "__doc__", "") or "").strip(),
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


__all__ = [
    "ensure_strict_json_schema",
    "function_schema",
]
