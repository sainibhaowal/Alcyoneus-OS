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
"""Send primitive for map-reduce fan-out in alcyoneus OS.

The Send class enables fan-out/map-reduce patterns by allowing a node
to send multiple parallel executions to the same or different target nodes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Send:
    """Dynamic routing command for map-reduce/fan-out patterns.

    Send allows a single node to dispatch multiple parallel executions
    to target nodes, each with its own argument payload. This enables
    map-reduce and fan-out patterns within the graph.

    Attributes:
        node: Target node name to send the payload to.
        arg: Argument payload for the target node.
        timeout: Optional timeout for this specific send operation.
    """

    node: str
    arg: Any
    timeout: float | None = None

    def __hash__(self) -> int:
        """Make Send hashable for use in sets/dicts."""
        return hash((self.node, str(self.arg)))

    def __eq__(self, other: object) -> bool:
        """Equality check for Send objects."""
        if not isinstance(other, Send):
            return NotImplemented
        return self.node == other.node and self.arg == other.arg

    def __repr__(self) -> str:
        return f"Send(node={self.node!r}, arg={self.arg!r})"


class Command:
    """Enhanced Command with Send support for dynamic routing.

    Extends the basic Command with goto/update/resume to also support
    Send operations for map-reduce patterns.

    Attributes:
        goto: Target node name or list of node names.
        update: State updates to apply before transitioning.
        resume: Value to resume execution with if interrupting.
        send: List of Send operations for map-reduce fan-out.
    """

    def __init__(
        self,
        *,
        goto: str | list[str] | None = None,
        update: dict[str, Any] | None = None,
        resume: Any | None = None,
        send: list[Send] | None = None,
    ):
        self.goto = goto
        self.update = update or {}
        self.resume = resume
        self.send = send or []

    def __repr__(self) -> str:
        parts = []
        if self.goto:
            parts.append(f"goto={self.goto!r}")
        if self.update:
            parts.append(f"update={self.update!r}")
        if self.resume is not None:
            parts.append(f"resume={self.resume!r}")
        if self.send:
            parts.append(f"send={self.send!r}")
        return f"Command({', '.join(parts)})"


def send(node: str, arg: Any, *, timeout: float | None = None) -> Send:
    """Create a Send operation for map-reduce fan-out.

    Args:
        node: Target node name.
        arg: Argument payload for the target node.
        timeout: Optional timeout for this send operation.

    Returns:
        Send object for use in Command.send list.

    Example:
        ```python
        def map_node(state):
            items = state.get("items", [])
            return Command(send=[send("process_item", item) for item in items])
        ```
    """
    return Send(node=node, arg=arg, timeout=timeout)


__all__ = [
    "Command",
    "Send",
    "send",
]
