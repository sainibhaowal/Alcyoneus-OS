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

"""LiteLLM response converter supporting 100+ model providers."""

from __future__ import annotations

import logging
from typing import Any

from .base_converter import BaseConverter


logger = logging.getLogger("alcyoneus.adapters.llm.litellm")


class LiteLLMConverter(BaseConverter):
    """Adapter for LiteLLM unified completion interface.

    Allows Alcyoneus OS agents to call 100+ models (Anthropic, Cohere, Bedrock,
    Replicate, Groq, Ollama, etc.) through LiteLLM.
    """

    def __init__(self, default_model: str = "gpt-4o") -> None:
        self.default_model = default_model

    def convert_request(
        self, messages: list[Any], model: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        """Convert Alcyoneus OS internal messages into LiteLLM completion arguments."""
        target_model = model or self.default_model
        formatted_messages = []
        for msg in messages:
            if hasattr(msg, "model_dump"):
                formatted_messages.append(msg.model_dump())
            elif isinstance(msg, dict):
                formatted_messages.append(msg)
            else:
                formatted_messages.append(
                    {"role": getattr(msg, "role", "user"), "content": str(msg)}
                )

        return {
            "model": target_model,
            "messages": formatted_messages,
            **kwargs,
        }

    def convert_response(self, raw_response: Any) -> dict[str, Any]:
        """Convert LiteLLM completion response into Alcyoneus OS standard structure."""
        if hasattr(raw_response, "choices") and raw_response.choices:
            choice = raw_response.choices[0]
            message = choice.message
            content = getattr(message, "content", "")
            tool_calls = getattr(message, "tool_calls", None)
            return {
                "content": content,
                "tool_calls": tool_calls,
                "role": getattr(message, "role", "assistant"),
                "raw": raw_response,
            }
        return {"content": str(raw_response), "role": "assistant", "raw": raw_response}

    def convert_streaming_response(self, raw_chunk: Any) -> dict[str, Any] | None:
        if hasattr(raw_chunk, "choices") and raw_chunk.choices:
            delta = raw_chunk.choices[0].delta
            content = getattr(delta, "content", "")
            return {"content": content, "role": getattr(delta, "role", "assistant")}
        return None


__all__ = ["LiteLLMConverter"]
