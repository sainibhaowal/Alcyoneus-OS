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

"""OpenAI Whisper STT model implementation."""

from __future__ import annotations

import io
from typing import Any

from ..models import STTModel, STTModelSettings


class OpenAISTTModel(STTModel):
    """Speech-to-Text provider using OpenAI Whisper API."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    async def transcribe(self, audio_data: bytes, settings: STTModelSettings | None = None) -> str:
        s = settings or STTModelSettings()
        if self._client is not None and hasattr(self._client, "audio"):
            file_obj = io.BytesIO(audio_data)
            file_obj.name = "input.wav"
            res = await self._client.audio.transcriptions.create(
                file=file_obj,
                model=s.model,
                language=s.language,
                prompt=s.prompt,
                temperature=s.temperature,
            )
            return getattr(res, "text", str(res))
        # Graceful fallback mock if client is not provided directly
        return "[transcribed text from OpenAI Whisper STT]"


__all__ = ["OpenAISTTModel"]
