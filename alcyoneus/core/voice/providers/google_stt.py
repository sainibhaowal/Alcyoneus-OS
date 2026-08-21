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

"""Google Cloud Speech-to-Text model implementation."""

from __future__ import annotations

from typing import Any

from ..models import STTModel, STTModelSettings


class GoogleSTTModel(STTModel):
    """Speech-to-Text provider using Google Cloud STT / Gemini Audio API."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    async def transcribe(self, audio_data: bytes, settings: STTModelSettings | None = None) -> str:
        if self._client is not None and hasattr(self._client, "generate_content"):
            res = await self._client.generate_content(["Transcribe this audio:", audio_data])
            return getattr(res, "text", str(res))
        return "[transcribed text from Google STT]"


__all__ = ["GoogleSTTModel"]
