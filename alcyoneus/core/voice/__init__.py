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

"""Voice Pipeline System (STT -> Agent -> TTS) for Alcyoneus OS."""

from .events import (
    VoiceStreamEvent,
    VoiceStreamEventAudio,
    VoiceStreamEventLifecycle,
)
from .input import AudioInput, StreamedAudioInput
from .models import (
    STTModel,
    STTModelSettings,
    TTSModel,
    TTSModelSettings,
    VoiceModelProvider,
)
from .pipeline import VoicePipeline, VoicePipelineConfig
from .providers.google_stt import GoogleSTTModel
from .providers.openai_stt import OpenAISTTModel
from .providers.openai_tts import OpenAITTSModel
from .result import StreamedAudioResult
from .sip import SIPCallConfig, SIPTelephony
from .workflow import (
    SingleAgentVoiceWorkflow,
    VoiceWorkflowBase,
    VoiceWorkflowHelper,
)


__all__ = [
    "AudioInput",
    "GoogleSTTModel",
    "OpenAISTTModel",
    "OpenAITTSModel",
    "SIPCallConfig",
    "SIPTelephony",
    "STTModel",
    "STTModelSettings",
    "SingleAgentVoiceWorkflow",
    "StreamedAudioInput",
    "StreamedAudioResult",
    "TTSModel",
    "TTSModelSettings",
    "VoiceModelProvider",
    "VoicePipeline",
    "VoicePipelineConfig",
    "VoiceStreamEvent",
    "VoiceStreamEventAudio",
    "VoiceStreamEventLifecycle",
    "VoiceWorkflowBase",
    "VoiceWorkflowHelper",
]
