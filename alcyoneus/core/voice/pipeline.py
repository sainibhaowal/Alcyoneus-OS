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

"""End-to-end voice pipeline connecting STT -> Agent -> TTS."""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any

from .input import AudioInput
from .models import STTModel, STTModelSettings, TTSModel, TTSModelSettings
from .result import StreamedAudioResult


logger = logging.getLogger("alcyoneus.voice.pipeline")


@dataclass
class VoicePipelineConfig:
    """Configuration for end-to-end VoicePipeline."""

    stt_settings: STTModelSettings = field(default_factory=STTModelSettings)
    tts_settings: TTSModelSettings = field(default_factory=TTSModelSettings)


class VoicePipeline:
    """Orchestrates an end-to-end audio conversation turn:
    1. STT transcribes input audio bytes to text.
    2. Agent processes the text transcript.
    3. TTS synthesizes agent text response into output audio stream.
    """

    def __init__(
        self,
        stt_model: STTModel,
        tts_model: TTSModel,
        config: VoicePipelineConfig | None = None,
    ) -> None:
        self.stt_model = stt_model
        self.tts_model = tts_model
        self.config = config or VoicePipelineConfig()

    async def run(
        self,
        audio_input: AudioInput | bytes,
        agent: Any,
        context: Any = None,
    ) -> StreamedAudioResult:
        """Run the end-to-end voice pipeline."""
        result = StreamedAudioResult()

        audio_bytes = audio_input.data if isinstance(audio_input, AudioInput) else audio_input

        # 1. Speech to Text
        await result.emit_lifecycle("stt_start")
        user_text = await self.stt_model.transcribe(audio_bytes, self.config.stt_settings)
        await result.emit_lifecycle("stt_complete", {"transcript": user_text})

        # 2. Agent Execution
        await result.emit_lifecycle("agent_start", {"input_text": user_text})
        if hasattr(agent, "ainvoke"):
            agent_response = await agent.ainvoke({"messages": [user_text]})
            reply_text = str(agent_response.get("content", agent_response))
        elif callable(agent):
            res = agent(user_text)
            if inspect.isawaitable(res):
                res = await res
            reply_text = str(res)
        else:
            reply_text = str(agent)
        await result.emit_lifecycle("agent_complete", {"reply_text": reply_text})
        result.transcript = reply_text

        # 3. Text to Speech Streaming
        await result.emit_lifecycle("tts_start")
        async for chunk in self.tts_model.synthesize_stream(reply_text, self.config.tts_settings):
            await result.emit_audio(chunk, format=self.config.tts_settings.response_format)

        await result.emit_lifecycle("tts_complete")
        await result.finish()
        return result


__all__ = ["VoicePipeline", "VoicePipelineConfig"]
