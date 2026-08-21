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

"""RunErrorHandler callbacks and structures for handling execution errors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class RunErrorData:
    """Error data context passed to error handlers."""

    error: Exception
    agent_name: str
    turn_index: int


@dataclass
class RunErrorHandlerResult:
    """Outcome returned by a run error handler."""

    recovered: bool
    replacement_content: str | None = None


RunErrorHandler = Callable[[RunErrorData], RunErrorHandlerResult]


class RunErrorHandlers:
    """Registry for execution run error handlers."""

    def __init__(self, handlers: list[RunErrorHandler] | None = None) -> None:
        self.handlers = handlers or []

    def add_handler(self, handler: RunErrorHandler) -> None:
        self.handlers.append(handler)


__all__ = [
    "RunErrorData",
    "RunErrorHandler",
    "RunErrorHandlerResult",
    "RunErrorHandlers",
]
