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

"""OpenAI Text-to-Speech (TTS) model implementation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ..models import TTSModel, TTSModelSettings


class OpenAITTSModel(TTSModel):
    """Text-to-Speech provider using OpenAI TTS API."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    async def synthesize(self, text: str, settings: TTSModelSettings | None = None) -> bytes:
        s = settings or TTSModelSettings()
        if self._client is not None and hasattr(self._client, "audio"):
            res = await self._client.audio.speech.create(
                model=s.model,
                voice=s.voice,
                input=text,
                speed=s.speed,
                response_format=s.response_format,
            )
            return getattr(res, "content", b"")
        return b"[synthesized audio bytes from OpenAI TTS]"

    async def synthesize_stream(
        self, text: str, settings: TTSModelSettings | None = None
    ) -> AsyncIterator[bytes]:
        audio_bytes = await self.synthesize(text, settings)
        chunk_size = 1024
        for i in range(0, len(audio_bytes), chunk_size):
            yield audio_bytes[i : i + chunk_size]


__all__ = ["OpenAITTSModel"]
