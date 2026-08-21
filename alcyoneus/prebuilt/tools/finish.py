"""Explicit structured completion tool."""

from __future__ import annotations

import json
from typing import Any

from alcyoneus.utils.decorators import tool


@tool(
    name="finish",
    description="Explicitly finish a run with a structured result.",
    tags=["control", "output"],
    capabilities=["complete_run"],
)
def finish(
    result: Any = None, status: str = "completed", config: dict[str, Any] | None = None
) -> str:
    """Return a structured completion payload for the host/graph controller."""
    payload = {"status": status, "result": result}
    callback = (config or {}).get("finish_callback")
    if callback:
        callback(payload)
    return json.dumps(payload, default=str)
