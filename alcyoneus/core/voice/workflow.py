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

"""Voice workflow helper abstractions."""

from __future__ import annotations

import abc
from typing import Any

from .input import AudioInput
from .pipeline import VoicePipeline
from .result import StreamedAudioResult


class VoiceWorkflowBase(abc.ABC):
    """Abstract base class for stateful voice workflows."""

    @abc.abstractmethod
    async def process_audio(self, audio_input: AudioInput) -> StreamedAudioResult:
        pass


class SingleAgentVoiceWorkflow(VoiceWorkflowBase):
    """Voice workflow bound to a single agent and voice pipeline."""

    def __init__(self, pipeline: VoicePipeline, agent: Any) -> None:
        self.pipeline = pipeline
        self.agent = agent

    async def process_audio(self, audio_input: AudioInput) -> StreamedAudioResult:
        return await self.pipeline.run(audio_input, self.agent)


class VoiceWorkflowHelper:
    """Helper utilities for constructing voice pipelines."""

    @staticmethod
    def create_single_agent_workflow(
        pipeline: VoicePipeline, agent: Any
    ) -> SingleAgentVoiceWorkflow:
        return SingleAgentVoiceWorkflow(pipeline=pipeline, agent=agent)


__all__ = [
    "SingleAgentVoiceWorkflow",
    "VoiceWorkflowBase",
    "VoiceWorkflowHelper",
]
