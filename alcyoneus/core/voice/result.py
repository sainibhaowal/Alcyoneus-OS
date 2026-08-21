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

"""Result container for streaming audio output in voice workflows."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from .events import VoiceStreamEvent, VoiceStreamEventAudio, VoiceStreamEventLifecycle


class StreamedAudioResult:
    """Async iterator container yielding stream events and accumulated audio/transcript."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[VoiceStreamEvent | None] = asyncio.Queue()
        self.transcript: str = ""
        self.accumulated_audio: bytearray = bytearray()

    async def emit_audio(self, chunk: bytes, format: str = "mp3") -> None:  # noqa: A002
        self.accumulated_audio.extend(chunk)
        await self._queue.put(VoiceStreamEventAudio(audio_chunk=chunk, format=format))

    async def emit_lifecycle(self, event_type: str, data: dict | None = None) -> None:
        await self._queue.put(VoiceStreamEventLifecycle(event_type=event_type, data=data))

    async def finish(self) -> None:
        await self._queue.put(None)

    async def __aiter__(self) -> AsyncIterator[VoiceStreamEvent]:
        while True:
            evt = await self._queue.get()
            if evt is None:
                break
            yield evt


__all__ = ["StreamedAudioResult"]
