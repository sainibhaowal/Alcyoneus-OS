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

"""InjectedState and InjectedStore type markers for tool schema protection."""

from __future__ import annotations

import inspect
from typing import get_args, get_origin


class InjectedState:
    """Type marker indicating a tool parameter should be injected with graph state and stripped from LLM JSON schema."""  # noqa: E501


class InjectedStore:
    """Type marker indicating a tool parameter should be injected with memory store and stripped from LLM JSON schema."""  # noqa: E501


def is_injected_param(param: inspect.Parameter) -> bool:
    """Check if a function parameter is typed or annotated with InjectedState or InjectedStore."""
    annotation = param.annotation
    if annotation is inspect.Parameter.empty:
        return False

    if annotation in (InjectedState, InjectedStore):
        return True

    # Check typing.Annotated[T, InjectedState]
    origin = get_origin(annotation)
    if origin is not None:
        args = get_args(annotation)
        for arg in args:
            if arg in (InjectedState, InjectedStore) or (
                isinstance(arg, type) and issubclass(arg, (InjectedState, InjectedStore))
            ):
                return True

    return False


__all__ = [
    "InjectedState",
    "InjectedStore",
    "is_injected_param",
]
