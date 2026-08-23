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

"""Human-In-The-Loop (HITL) interaction specifications and callbacks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class InteractionSpec:
    """Specification of an interactive request to a human user."""

    prompt: str
    options: list[str] | None = None
    default_response: str | None = None


@dataclass
class InteractionResult:
    """Outcome of a human user interaction."""

    user_response: str
    approved: bool = True


OnInteractionHook = Callable[[InteractionSpec], InteractionResult]


def on_interaction(func: OnInteractionHook) -> OnInteractionHook:
    """Decorator marking a function as an interaction hook callback."""
    return func


__all__ = [
    "InteractionResult",
    "InteractionSpec",
    "OnInteractionHook",
    "on_interaction",
]
