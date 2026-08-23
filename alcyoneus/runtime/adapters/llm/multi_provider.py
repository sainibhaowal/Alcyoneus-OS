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

"""MultiProvider router for dynamic model and provider resolution."""

from __future__ import annotations

import logging
from typing import Any

from .base_converter import BaseConverter
from .google_genai_converter import GoogleGenAIConverter
from .openai_converter import OpenAIConverter


logger = logging.getLogger("alcyoneus.adapters.llm.multiprovider")


class MultiProvider(BaseConverter):
    """Router that dispatches calls to different converters based on model prefix.

    Examples:
        - "openai/gpt-4o" -> OpenAIConverter
        - "google/gemini-1.5-pro" -> GoogleGenAIConverter
        - "litellm/claude-3-5-sonnet" -> LiteLLMConverter
        - "ollama/llama3" -> AnyLLMConverter
    """

    def __init__(self, providers: dict[str, BaseConverter] | None = None) -> None:
        self.providers: dict[str, BaseConverter] = providers or {
            "openai": OpenAIConverter(),
            "google": GoogleGenAIConverter(),
            "gemini": GoogleGenAIConverter(),
        }
        self.default_provider = OpenAIConverter()

    def register_provider(self, prefix: str, converter: BaseConverter) -> None:
        """Register a provider converter under a prefix string."""
        self.providers[prefix.lower()] = converter

    def resolve_converter(self, model: str | None) -> tuple[BaseConverter, str]:
        """Resolve model name and matching converter."""
        if not model:
            return self.default_provider, "gpt-4o"

        if "/" in model:
            prefix, name = model.split("/", 1)
            prefix_lower = prefix.lower()
            if prefix_lower in self.providers:
                return self.providers[prefix_lower], name

        # Fallback keyword checks
        model_lower = model.lower()
        if "gemini" in model_lower:
            return self.providers.get("google", self.default_provider), model
        if "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower:
            return self.providers.get("openai", self.default_provider), model

        return self.default_provider, model

    def convert_request(
        self, messages: list[Any], model: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        converter, clean_model = self.resolve_converter(model)
        return converter.convert_request(messages=messages, model=clean_model, **kwargs)

    def convert_response(self, raw_response: Any) -> dict[str, Any]:
        return self.default_provider.convert_response(raw_response)

    def convert_streaming_response(self, raw_chunk: Any) -> dict[str, Any] | None:
        return self.default_provider.convert_streaming_response(raw_chunk)


__all__ = ["MultiProvider"]
