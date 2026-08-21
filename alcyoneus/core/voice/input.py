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

"""Audio input representations for voice pipeline processing."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class AudioInput:
    """Static single-buffer audio input container."""

    data: bytes
    format: str = "wav"
    sample_rate: int = 16000


class StreamedAudioInput:
    """Asynchronous queue-backed streaming audio input."""

    def __init__(self, format: str = "pcm", sample_rate: int = 24000) -> None:  # noqa: A002
        self.format = format
        self.sample_rate = sample_rate
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def push_chunk(self, chunk: bytes) -> None:
        """Push an audio chunk into the streaming queue."""
        await self._queue.put(chunk)

    async def finish(self) -> None:
        """Signal end of stream."""
        await self._queue.put(None)

    async def __aiter__(self) -> AsyncIterator[bytes]:
        while True:
            chunk = await self._queue.get()
            if chunk is None:
                break
            yield chunk


__all__ = ["AudioInput", "StreamedAudioInput"]
