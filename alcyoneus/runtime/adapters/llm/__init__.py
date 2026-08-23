"""Integration adapters for optional third-party LLM SDKs.

This package exposes the concrete response converters used by Alcyoneus OS.
"""

from .anyllm_converter import AnyLLMConverter
from .base_converter import BaseConverter, ConverterType
from .google_genai_converter import GoogleGenAIConverter
from .litellm_converter import LiteLLMConverter
from .multi_provider import MultiProvider
from .openai_converter import OpenAIConverter
from .openai_responses_converter import OpenAIResponsesConverter, is_responses_api_response


__all__ = [
    "AnyLLMConverter",
    "BaseConverter",
    "ConverterType",
    "GoogleGenAIConverter",
    "LiteLLMConverter",
    "MultiProvider",
    "OpenAIConverter",
    "OpenAIResponsesConverter",
    "is_responses_api_response",
]
