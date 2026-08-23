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

"""Pydantic model tool return wrapper for structured data validation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class PydanticToolReturn:
    """Wrapper that validates tool returns against a Pydantic model class."""

    def __init__(self, tool_fn: Callable[..., Any], model_cls: Any) -> None:
        self.tool_fn = tool_fn
        self.model_cls = model_cls
        self.name = getattr(tool_fn, "__name__", "pydantic_tool")

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        res = self.tool_fn(*args, **kwargs)
        if hasattr(res, "__await__"):
            res = await res
        if hasattr(self.model_cls, "model_validate"):
            return self.model_cls.model_validate(res)
        if hasattr(self.model_cls, "parse_obj"):
            return self.model_cls.parse_obj(res)
        if isinstance(res, dict):
            return self.model_cls(**res)
        return res


__all__ = ["PydanticToolReturn"]
