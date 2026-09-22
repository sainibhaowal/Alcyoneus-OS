"""OpenAI Realtime provider client.

Implements the RealtimeClient protocol for OpenAI's Realtime API (WebSocket).
"""

from __future__ import annotations

import base64
import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import aiohttp

from alcyoneus.core.realtime.base import (
    AudioDeltaEvent,
    InputTranscriptEvent,
    InterruptedEvent,
    OutputTranscriptEvent,
    RealtimeConfig,
    RealtimeEvent,
    SessionUpdateEvent,
    ToolCallEvent,
    TurnCompleteEvent,
)


logger = logging.getLogger(__name__)

OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime?model={model}"
OPENAI_AZURE_URL = "wss://{resource}.openai.azure.com/openai/realtime?api-version={api_version}&deployment={deployment}"


class OpenAIRealtimeClient:
    """RealtimeClient implementation for OpenAI Realtime API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        organization: str | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._base_url = base_url
        self._organization = organization or os.getenv("OPENAI_ORGANIZATION")
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._config: RealtimeConfig | None = None
        self._session_id: str | None = None

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    async def connect(self, config: RealtimeConfig, resume_handle: str | None = None) -> None:
        if not self._api_key:
            raise ValueError("OpenAI API key required: set OPENAI_API_KEY or pass api_key")

        self._config = config
        model = config.model
        url = self._base_url or OPENAI_REALTIME_URL.format(model=model)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        if self._organization:
            headers["OpenAI-Organization"] = self._organization

        self._ws = await aiohttp.ClientSession().ws_connect(url, headers=headers)

        # Send session.update
        await self._send_session_update(resume_handle)
        logger.info("OpenAI Realtime connected: %s", model)

    def _build_session_config(self, resume_handle: str | None = None) -> dict[str, Any]:
        cfg = self._config
        session_cfg = {
            "modalities": cfg.response_modalities,  # type: ignore[union-attr]
            "voice": cfg.voice or "alloy",  # type: ignore[union-attr]
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {"model": "whisper-1"}
            if cfg.input_audio_transcription  # type: ignore[union-attr]
            else None,
            "output_audio_transcription": {"model": "whisper-1"}
            if cfg.output_audio_transcription  # type: ignore[union-attr]
            else None,
            "turn_detection": None
            if not cfg.vad.enabled  # type: ignore[union-attr]
            else {
                "type": "server_vad",
                "threshold": float(cfg.vad.start_sensitivity or 0.5),  # type: ignore[union-attr]
                "prefix_padding_ms": cfg.vad.prefix_padding_ms or 300,  # type: ignore[union-attr]
                "silence_duration_ms": cfg.vad.silence_duration_ms or 500,  # type: ignore[union-attr]
            },
            "tools": self._convert_tools(cfg.tools) if cfg.tools else [],  # type: ignore[union-attr]
            "tool_choice": "auto" if cfg.tools else "none",  # type: ignore[union-attr]
        }
        if cfg.system_instruction:  # type: ignore[union-attr]
            session_cfg["instructions"] = cfg.system_instruction  # type: ignore[union-attr]
        if resume_handle:
            session_cfg["session_id"] = resume_handle
        if cfg.context_window_compression:  # type: ignore[union-attr]
            session_cfg["context_window"] = {"type": "sliding", "max_messages": 100}
        return {k: v for k, v in session_cfg.items() if v is not None}

    def _convert_tools(self, tools: list[Any]) -> list[dict]:
        """Convert provider-neutral tools to OpenAI format."""
        result = []
        for t in tools:
            if isinstance(t, dict) and t.get("type") == "function":
                fn = t["function"]
                result.append(
                    {
                        "type": "function",
                        "name": fn["name"],
                        "description": fn.get("description", ""),
                        "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
                    }
                )
            elif callable(t):
                # Try to extract function schema from callable
                import inspect

                sig = inspect.signature(t)
                params = {"type": "object", "properties": {}}
                for name, _ in sig.parameters.items():
                    params["properties"][name] = {"type": "string"}  # type: ignore[index]
                result.append({"type": "function", "name": t.__name__, "parameters": params})
        return result

    async def _send_session_update(self, resume_handle: str | None = None) -> None:
        await self._ws.send_json(  # type: ignore[union-attr]
            {"type": "session.update", "session": self._build_session_config(resume_handle)}
        )

    async def send_audio(self, pcm: bytes, sample_rate: int = 24000) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        # OpenAI expects base64 encoded audio
        audio_b64 = base64.b64encode(pcm).decode()
        await self._ws.send_json({"type": "input_audio_buffer.append", "audio": audio_b64})  # type: ignore[union-attr]

    async def send_text(self, text: str) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        await self._ws.send_json(  # type: ignore[union-attr]
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        )
        await self._ws.send_json({"type": "response.create"})  # type: ignore[union-attr]

    async def send_image(self, data: bytes, mime_type: str = "image/jpeg") -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        b64 = base64.b64encode(data).decode()
        await self._ws.send_json(  # type: ignore[union-attr]
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_image", "image_url": f"data:{mime_type};base64,{b64}"}
                    ],
                },
            }
        )

    async def send_activity_start(self) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        await self._ws.send_json({"type": "input_audio_buffer.commit"})  # type: ignore[union-attr]

    async def send_activity_end(self) -> None:
        # OpenAI doesn't have explicit activity end; just commit
        pass

    async def send_tool_response(self, call_id: str, name: str, result: Any) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        await self._ws.send_json(  # type: ignore[union-attr]
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result),
                },
            }
        )
        await self._ws.send_json({"type": "response.create"})  # type: ignore[union-attr]

    async def reseed_history(self, messages: list[Any]) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        for msg in messages:
            role = getattr(msg, "role", "user")
            if role not in ("user", "assistant"):
                continue
            text = "".join(getattr(b, "text", "") or "" for b in getattr(msg, "content", []) or [])
            if not text:
                continue
            await self._ws.send_json(  # type: ignore[union-attr]
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": role,
                        "content": [{"type": "text", "text": text}],
                    },
                }
            )

    async def receive(self) -> AsyncIterator[RealtimeEvent]:
        if not self.connected:
            raise RuntimeError("Not connected")
        async for msg in self._ws:  # type: ignore[union-attr]
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                for event in self._normalize_message(data):
                    yield event
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error("WebSocket error: %s", self._ws.exception())  # type: ignore[union-attr]
                break

    def _normalize_message(self, data: dict) -> list[RealtimeEvent]:
        events = []
        msg_type = data.get("type")

        if msg_type == "response.audio.delta":
            audio_b64 = data.get("delta", "")
            if audio_b64:
                pcm = base64.b64decode(audio_b64)
                events.append(AudioDeltaEvent(data=pcm, sample_rate=24000))

        elif msg_type == "conversation.item.input_audio_transcription.completed":
            events.append(InputTranscriptEvent(text=data.get("transcript", ""), finished=True))  # type: ignore[arg-type]
        elif msg_type == "conversation.item.input_audio_transcription.delta":
            events.append(InputTranscriptEvent(text=data.get("delta", ""), finished=False))  # type: ignore[arg-type]

        elif msg_type == "response.audio_transcript.delta":
            events.append(OutputTranscriptEvent(text=data.get("delta", ""), finished=False))  # type: ignore[arg-type]
        elif msg_type == "response.audio_transcript.done":
            events.append(OutputTranscriptEvent(text=data.get("transcript", ""), finished=True))  # type: ignore[arg-type]

        elif msg_type == "response.function_call_arguments.done":
            events.append(
                ToolCallEvent(  # type: ignore[arg-type]
                    id=data.get("call_id", uuid4().hex),
                    name=data.get("name", ""),
                    args=json.loads(data.get("arguments", "{}")),
                )
            )

        elif msg_type == "response.done":
            events.append(TurnCompleteEvent())  # type: ignore[arg-type]
            if data.get("response", {}).get("status") == "incomplete":
                events.append(InterruptedEvent())  # type: ignore[arg-type]

        elif msg_type == "error":
            err = data.get("error", {})
            events.append(
                RealtimeEvent.__dict__["__args__"][-1](  # ErrorEvent
                    code=err.get("code"),
                    message=err.get("message", ""),
                    fatal=err.get("fatal", False),
                )
            )

        elif msg_type == "session.updated":
            events.append(SessionUpdateEvent(resumption_handle=data.get("session", {}).get("id")))  # type: ignore[arg-type]

        return events  # type: ignore[return-value]

    async def close(self) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.close()
        self._ws = None
        self._config = None


__all__ = ["OpenAIRealtimeClient"]
