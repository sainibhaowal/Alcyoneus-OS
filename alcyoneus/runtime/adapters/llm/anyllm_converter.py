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

"""AnyLLM generic OpenAI-compatible API response converter."""

from __future__ import annotations

import logging
from typing import Any

from .openai_converter import OpenAIConverter


logger = logging.getLogger("alcyoneus.adapters.llm.anyllm")


class AnyLLMConverter(OpenAIConverter):
    """Generic converter for any custom OpenAI-compatible API server.

    Works seamlessly with Ollama, vLLM, LMStudio, Jan, TGI, LocalAI, etc.
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key or "local-key"

    def convert_request(
        self, messages: list[Any], model: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        req = super().convert_request(messages=messages, model=model, **kwargs)
        if self.base_url:
            req["base_url"] = self.base_url
        if self.api_key:
            req["api_key"] = self.api_key
        return req


__all__ = ["AnyLLMConverter"]
