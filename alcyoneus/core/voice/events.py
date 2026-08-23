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

"""Streaming voice events for real-time audio pipeline monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class VoiceStreamEventAudio:
    """Audio data chunk event emitted during TTS synthesis."""

    audio_chunk: bytes
    format: str = "mp3"
    type: Literal["audio"] = "audio"


@dataclass
class VoiceStreamEventLifecycle:
    """Lifecycle state change event (e.g. stt_start, agent_start, tts_start, finished)."""

    event_type: str
    data: dict[str, Any] | None = None
    type: Literal["lifecycle"] = "lifecycle"


VoiceStreamEvent = VoiceStreamEventAudio | VoiceStreamEventLifecycle

__all__ = [
    "VoiceStreamEvent",
    "VoiceStreamEventAudio",
    "VoiceStreamEventLifecycle",
]
