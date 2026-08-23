"""Tests that restored protocol APIs remain importable without optional SDKs."""

from __future__ import annotations

import asyncio

import pytest

from alcyoneus.runtime.protocols.acp import (
    ACPInMemoryTransport,
    ACPMessageType,
    ACPProtocol,
)
from alcyoneus.runtime.protocols.a2a import build_a2a_app, make_agent_card
from alcyoneus.core.state.message import Message


def test_acp_round_trip_and_validation():
    message = ACPProtocol.create_request("sender", "receiver", "ping", {"value": 1})
    assert message.message_type is ACPMessageType.REQUEST
    valid, error = ACPProtocol.validate_message(message)
    assert valid is True
    assert error is None
    restored = message.from_json(message.to_json())
    assert restored.message_id == message.message_id


@pytest.mark.asyncio
async def test_acp_in_memory_transport():
    transport = ACPInMemoryTransport()
    message = ACPProtocol.create_heartbeat("a")
    await transport.send(message)
    received = await asyncio.wait_for(transport.receive(), timeout=1)
    assert received.message_id == message.message_id


def test_a2a_runtime_sdk_card_and_app():
    card = make_agent_card("test-agent", "test", "http://127.0.0.1:9999", streaming=True)

    class FakeGraph:
        async def ainvoke(self, *args, **kwargs):
            return {"messages": []}

    app = build_a2a_app(FakeGraph(), card, streaming=False)
    assert app.routes
    assert card.name == "test-agent"


@pytest.mark.asyncio
async def test_a2a_runtime_jsonrpc_round_trip():
    httpx = pytest.importorskip("httpx")

    class FakeGraph:
        async def ainvoke(self, *args, **kwargs):
            return {"messages": [Message.text_message("hello", role="assistant")]}

    app = build_a2a_app(
        FakeGraph(),
        make_agent_card("test-agent", "test", "http://test"),
    )
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "SendMessage",
        "params": {
            "message": {
                "messageId": "m1",
                "role": "ROLE_USER",
                "parts": [{"text": "hi"}],
                "contextId": "c1",
            }
        },
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/", json=payload, headers={"A2A-Version": "1.0"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["result"]["task"]["status"]["state"] == "TASK_STATE_COMPLETED"
    assert body["result"]["task"]["artifacts"][0]["parts"][0]["text"] == "hello"
