"""Structured human-in-the-loop question tool."""

from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from alcyoneus.utils.decorators import tool


@dataclass
class HumanQuestionBroker:
    """Durable-in-process question broker for UI-backed graph runs.

    ``ask_question`` awaits ``ask``. The application sends the returned
    request to its UI, then calls ``answer(request_id, value)`` from the UI
    callback. Applications may persist ``pending_requests`` in their own
    store before returning from ``ask`` to survive process restarts.
    """

    pending_requests: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._waiters: dict[str, asyncio.Future[Any]] = {}

    async def ask(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = str(request.get("request_id") or uuid.uuid4())
        request = {**request, "request_id": request_id, "status": "waiting_for_user"}
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self.pending_requests[request_id] = request
        self._waiters[request_id] = future
        publish = request.get("publish")
        if publish:
            published = publish(request)
            if inspect.isawaitable(published):
                await published
        answer = await future
        self.pending_requests.pop(request_id, None)
        self._waiters.pop(request_id, None)
        return {"request_id": request_id, "answer": answer}

    def answer(self, request_id: str, answer: Any) -> None:
        future = self._waiters.get(request_id)
        if future is None:
            raise KeyError(f"unknown or expired question request: {request_id}")
        if not future.done():
            future.set_result(answer)

    def cancel(self, request_id: str) -> bool:
        future = self._waiters.get(request_id)
        if future is None:
            return False
        future.cancel()
        return True


@tool(
    name="ask_question",
    description="Ask the user a structured question and wait for the host to provide an answer.",
    tags=["human", "interaction", "approval"],
    capabilities=["human_input"],
)
async def ask_question(
    question: str,
    options: list[str] | None = None,
    allow_freeform: bool = True,
    config: dict[str, Any] | None = None,
) -> str:
    """Delegate the question to a configured async question broker.

    Hosts integrate this with graph checkpoint/resume by supplying
    ``config['question_broker']``.  The broker receives a stable request and
    returns the user's answer; no terminal input is used as a hidden fallback.
    """
    if not question.strip():
        return json.dumps({"error": "question is required", "tool": "ask_question"})
    broker = (config or {}).get("question_broker")
    if broker is None:
        return json.dumps(
            {
                "status": "needs_host_broker",
                "question": question,
                "options": options or [],
                "allow_freeform": allow_freeform,
            }
        )
    request = {
        "request_id": str((config or {}).get("question_id") or ""),
        "question": question,
        "options": options or [],
        "allow_freeform": allow_freeform,
        "run_id": (config or {}).get("run_id") or (config or {}).get("thread_id"),
    }
    if isinstance(broker, HumanQuestionBroker):
        answer = broker.ask(request)
    else:
        answer = broker(request)
    if inspect.isawaitable(answer):
        answer = await answer
    if isinstance(answer, dict):
        payload = answer
    else:
        payload = {"answer": answer}
    payload["status"] = "answered"
    return json.dumps(payload, default=str)
