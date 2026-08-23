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

"""Abstract interfaces and settings for Speech-to-Text (STT) and Text-to-Speech (TTS)."""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class STTModelSettings:
    """Configuration settings for STT audio transcription."""

    model: str = "whisper-1"
    language: str | None = None
    prompt: str | None = None
    temperature: float = 0.0


@dataclass
class TTSModelSettings:
    """Configuration settings for TTS audio synthesis."""

    model: str = "tts-1"
    voice: str = "alloy"
    speed: float = 1.0
    response_format: str = "mp3"


class STTModel(abc.ABC):
    """Abstract base interface for Speech-To-Text models."""

    @abc.abstractmethod
    async def transcribe(self, audio_data: bytes, settings: STTModelSettings | None = None) -> str:
        """Transcribe audio bytes to text string."""


class TTSModel(abc.ABC):
    """Abstract base interface for Text-To-Speech models."""

    @abc.abstractmethod
    async def synthesize(self, text: str, settings: TTSModelSettings | None = None) -> bytes:
        """Synthesize text string into audio bytes."""

    @abc.abstractmethod
    async def synthesize_stream(
        self, text: str, settings: TTSModelSettings | None = None
    ) -> AsyncIterator[bytes]:
        """Stream synthesized audio chunks for text."""


class VoiceModelProvider(abc.ABC):
    """Factory interface providing STT and TTS models."""

    @abc.abstractmethod
    def get_stt_model(self) -> STTModel:
        pass

    @abc.abstractmethod
    def get_tts_model(self) -> TTSModel:
        pass


__all__ = [
    "STTModel",
    "STTModelSettings",
    "TTSModel",
    "TTSModelSettings",
    "VoiceModelProvider",
]
