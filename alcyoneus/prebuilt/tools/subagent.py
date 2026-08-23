"""Nested subagent tool boundary."""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from typing import Any

from alcyoneus.core.state.message import Message
from alcyoneus.utils.decorators import tool


@dataclass
class SubagentManager:
    """Bounded child-run manager for applications hosting Alcyoneus OS graphs.

    ``runner_factory`` receives the request plus parent metadata and returns a
    child result. Applications can use it to create a fresh graph/checkpointer
    per child while this manager supplies concurrency and timeout controls.
    """

    runner_factory: Any
    max_concurrency: int = 8

    def __post_init__(self) -> None:
        self._semaphore = asyncio.Semaphore(max(1, self.max_concurrency))

    async def run(self, request: dict[str, Any], timeout: float = 300.0) -> Any:
        async with self._semaphore:
            result = self.runner_factory(request)
            if inspect.isawaitable(result):
                return await asyncio.wait_for(result, timeout=max(0.1, min(timeout, 3600.0)))
            return result


@dataclass
class GraphSubagentManager(SubagentManager):
    """Run child graphs created by a factory with isolated child metadata."""

    async def run(self, request: dict[str, Any], timeout: float = 300.0) -> Any:
        async def invoke() -> Any:
            child = self.runner_factory(request)
            if inspect.isawaitable(child):
                child = await child
            if hasattr(child, "ainvoke"):
                config = {
                    **(request.get("config") or {}),
                    "parent_run_id": request.get("parent_run_id"),
                    "thread_id": request.get("child_thread_id"),
                }
                return await child.ainvoke(
                    {"messages": [Message.text_message(request["task"], role="user")]},
                    config=config,
                )
            if callable(child):
                result = child(request)
                return await result if inspect.isawaitable(result) else result
            return child

        async with self._semaphore:
            return await asyncio.wait_for(invoke(), timeout=max(0.1, min(timeout, 3600.0)))


@tool(
    name="start_subagent",
    description="Start an isolated child Alcyoneus OS run through the configured runner.",
    tags=["multiagent", "subagent", "delegation"],
    capabilities=["spawn_agents"],
)
async def start_subagent(
    task: str,
    agent_name: str | None = None,
    model: str | None = None,
    tools: list[str] | None = None,
    timeout: float = 300.0,
    parallel: bool = False,
    config: dict[str, Any] | None = None,
) -> str:
    """Run a child agent via an injected runner with parent/child metadata."""
    cfg = config or {}
    manager = cfg.get("subagent_manager")
    runner = cfg.get("subagent_runner")
    if manager is not None:
        runner = manager.run
    if runner is None:
        return json.dumps({"error": "no subagent_runner configured", "tool": "start_subagent"})
    request = {
        "task": task,
        "agent_name": agent_name,
        "model": model,
        "tools": tools or [],
        "parallel": parallel,
        "parent_run_id": (config or {}).get("run_id") or (config or {}).get("thread_id"),
        "child_thread_id": f"{(config or {}).get('thread_id', 'run')}:child",
        "config": config or {},
    }
    child = runner(request)
    if inspect.isawaitable(child):
        child = await asyncio.wait_for(child, timeout=max(0.1, min(float(timeout), 3600.0)))
    return json.dumps({"status": "completed", "result": child}, default=str)
