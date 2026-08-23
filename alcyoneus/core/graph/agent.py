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
"""Public Agent facade for graph-based LLM interactions.

The public import path remains ``alcyoneus.graph.agent.Agent`` while the
implementation lives in smaller internal modules under ``alcyoneus.graph.agent_internal``.
"""

import logging
import os
from typing import TYPE_CHECKING, Any

from alcyoneus.core.graph.base_agent import BaseAgent
from alcyoneus.core.graph.tool_node import ToolNode
from alcyoneus.core.skills.models import SkillConfig
from alcyoneus.core.state.message import Message
from alcyoneus.storage.media.config import MultimodalConfig

from .agent_internal.constants import DEFAULT_RETRY_CONFIG, REASONING_DEFAULT, RetryConfig
from .agent_internal.execution import AgentExecutionMixin
from .agent_internal.google import AgentGoogleMixin
from .agent_internal.memory import AgentMemoryMixin
from .agent_internal.openai import AgentOpenAIMixin
from .agent_internal.providers import AgentProviderMixin
from .agent_internal.skills import AgentSkillsMixin
from .tool_use_behavior import StopAtTools, ToolUseBehavior, normalize_tool_use_behavior


if TYPE_CHECKING:
    from alcyoneus.storage.store.memory_config import MemoryConfig


logger = logging.getLogger("alcyoneus.agent")


class Agent(
    AgentExecutionMixin,
    AgentGoogleMixin,
    AgentOpenAIMixin,
    AgentProviderMixin,
    AgentSkillsMixin,
    AgentMemoryMixin,
    BaseAgent,
):
    """A smart node function wrapper for LLM interactions.

    This class handles common boilerplate for agent implementations including:
    - Automatic message conversion
    - LLM calls via native provider SDKs (OpenAI, Google)
    - Tool handling with conditional logic
    - Optional learning/RAG capabilities
    - Response conversion

    The Agent is designed to be used as a node within a StateGraph, providing
    a high-level interface while maintaining full graph flexibility.

    Example:
        ```python
        # Create an agent node with a ToolNode
        tool_node = ToolNode([weather_tool])
        agent = Agent(
            model="gpt-4o",
            provider="openai",
            system_prompt=[{"role": "system", "content": "You are a helpful assistant"}],
            tool_node=tool_node,
        )

        # Use it in a graph
        graph = StateGraph()
        graph.add_node("MAIN", agent)
        graph.add_node("TOOL", tool_node)
        # ... setup conditional edges
        ```

    Attributes:
        model: Model identifier (e.g., "gpt-4o", "gemini-2.0-flash")
        provider: Provider name ("openai", "google")
        system_prompt: System prompt string or list of message dicts
        tool_node: ToolNode instance or name of an existing TOOL graph node (str)
        client: Optional custom client instance (escape hatch for power users)
        temperature: LLM sampling temperature
        max_tokens: Maximum tokens to generate
        llm_kwargs: Additional provider-specific parameters
    """

    def __init__(  # noqa: PLR0913
        self,
        model: str,
        output_type: str = "text",
        system_prompt: list[dict[str, Any]] | None = None,
        tool_node: "str | ToolNode | None" = None,
        extra_messages: list[Message] | None = None,
        trim_context: bool = False,
        tools_tags: set[str] | None = None,
        reasoning_config: dict[str, Any] | bool | None = REASONING_DEFAULT,  # type: ignore
        skills: "SkillConfig | None" = None,
        memory: "MemoryConfig | None" = None,
        retry_config: RetryConfig | bool | None = True,
        fallback_models: list[str | tuple[str, str]] | None = None,
        multimodal_config: MultimodalConfig | None = None,
        output_schema: Any | None = None,
        subagents: list[Any] | dict[str, Any] | None = None,
        tool_use_behavior: str | ToolUseBehavior | StopAtTools | None = None,
        **kwargs,
    ):
        """Initialize an Agent node.

        Args:
            model: Model identifier (any model name - no parsing required).
                Examples: "gpt-4o", "gemini-2.0-flash-exp", "qwen-2.5-72b", "deepseek-chat"
            provider: Provider name ("openai", "google"). If None, will auto-detect from model.
            output_type: Type of output to generate (default: "text").
                - "text": Text generation (default, most common)
                - "image": Image generation
                - "video": Video generation
                - "audio": Audio/TTS generation
            system_prompt: System prompt as list of message dicts.
                Supports state variable interpolation using placeholders like ``{field_name}``.
                At execution time, placeholders are replaced with actual values from the state.

                Example with interpolation::

                    class MyState(AgentState):
                        user_name: str = "Guest"
                        occasion: str = "casual"

                    agent = Agent(
                        model="gpt-4o",
                        system_prompt=[{
                            "role": "system",
                            "content": "You are helping {user_name} with {occasion} planning."
                        }]
                    )
                    # At runtime, placeholders are replaced with state values
            tool_node: A ``ToolNode`` instance containing the tools this agent may call,
                **or** a ``str`` naming an existing graph node whose ``func`` is a
                ``ToolNode`` (resolved at execution time via the DI container).
                Pass ``None`` when the agent needs no tools.

                Examples::

                    # Inline ToolNode — agent owns the tools
                    tool_node = ToolNode([get_weather, search])
                    agent = Agent(model="gpt-4o", tool_node=tool_node)

                    # Named reference — ToolNode lives as a separate graph node
                    agent = Agent(model="gpt-4o", tool_node="TOOL")

            extra_messages: Additional messages to include in every interaction.
            trim_context: Whether to trim context using context manager.
            tools_tags: Optional tags to filter tools.
            base_url (via **kwargs): Optional base URL for OpenAI-compatible APIs
                (ollama, vllm, openrouter, deepseek, etc.). Default: ``None``.
            api_style: API style for OpenAI provider. ``"chat"`` uses
                Chat Completions, ``"responses"`` uses the Responses API.
                Default: ``"chat"``.
            memory: Optional ``MemoryConfig`` enabling agent-level long-term
                memory tools and system prompts.
            reasoning_config: Unified reasoning control for all providers. Default
                is ``{"effort": "medium"}`` (on). Pass ``None`` to turn off.
                ``effort`` applies to both providers; ``summary`` is OpenAI-only;
                ``thinking_budget`` is Google-only and overrides ``effort``.

                For Google, ``effort`` is translated to ``thinking_budget`` automatically:
                ``"low"`` → 512, ``"medium"`` → 8192 (default), ``"high"`` → 24576.
                So thinking is **on by default** for Google with ``thinking_budget=8192``.

                Examples::

                    reasoning_config=None                        # OFF for both
                    reasoning_config={"effort": "high"}          # high, both providers
                    reasoning_config={"effort": "low", "summary": "auto"}  # OpenAI: low+summary
                    reasoning_config={"thinking_budget": 5000}   # Google exact budget
            retry_config: Controls automatic retry with exponential back-off for
                transient LLM errors (429, 500, 502, 503, 529).  Default is
                ``True`` which uses ``RetryConfig()`` (3 retries, 1 s initial
                delay, 2x backoff, 30 s cap).  Pass ``False`` or ``None`` to
                disable.  Pass a ``RetryConfig`` instance for fine-grained
                control::

                    retry_config = RetryConfig(max_retries=5, initial_delay=2.0)
                    retry_config = False  # disable retries entirely

            fallback_models: Ordered list of fallback models to try when the
                primary model exhausts all retries.  Each entry is either a
                plain model string (inherits the agent's provider) or a
                ``(model, provider)`` tuple for cross-provider fallback::

                    fallback_models = ["gpt-4o-mini"]
                    fallback_models = [("gemini-2.0-flash", "google")]
                    fallback_models = ["gpt-4o-mini", ("gemini-2.0-flash", "google")]

            **llm_kwargs: Additional provider-specific parameters
                (temperature, max_tokens, top_p, or model args, organization_id, project_id).

        Raises:
            ImportError: If required provider SDK is not installed.
            ValueError: If provider cannot be determined or doesn't support output_type.

        Example:
            ```python
            # Text generation with inline ToolNode
            tool_node = ToolNode([weather_tool, calculator])
            text_agent = Agent(
                model="openai/gpt-4o",
                system_prompt=[{"role": "system", "content": "You are a helpful assistant"}],
                tool_node=tool_node,
                temperature=0.8,
            )

            # Text generation with named ToolNode in graph
            agent = Agent(
                model="google/gemini-2.5-flash",
                tool_node="TOOL",  # references graph node named "TOOL"
            )

            # No tools
            agent = Agent(model="gpt-4o")

            # Image generation
            image_agent = Agent(
                model="openai/dall-e-3",
                output_type="image",
            )

            # Third-party models (Qwen, DeepSeek, Ollama)
            qwen_agent = Agent(
                model="qwen-2.5-72b-instruct",
                provider="openai",
                base_url="https://api.qwen.com/v1",
            )

            # With retry and fallback
            resilient_agent = Agent(
                model="gemini-2.5-flash",
                provider="google",
                retry_config=RetryConfig(max_retries=5, initial_delay=2.0),
                fallback_models=[
                    "gemini-2.0-flash",
                    ("gpt-4o-mini", "openai"),
                ],
            )
            ```
        """
        # Pop kwargs-only params before passing to parent
        base_url: str | None = kwargs.pop("base_url", None)
        provider: str | None = kwargs.pop("provider", None)
        # this is mainly for OpenAI-compatible APIs but can be used as a hint for provider detection
        api_style: str = kwargs.pop("api_style", "chat")

        # check user using vertex ai for google or other model
        use_vertex_ai: bool = kwargs.pop(
            "use_vertex_ai",
            os.getenv(
                "GOOGLE_GENAI_USE_VERTEXAI",
                "false",
            ).lower()
            == "true",
        )  # legacy alias for provider="google"
        # Persist so fallback clients (created lazily at call time) honour the
        # same Vertex AI selection as the primary client.
        self.use_vertex_ai = use_vertex_ai
        # Call parent constructor
        super().__init__(
            model=model,
            system_prompt=system_prompt or [],
            tool_node=tool_node,
            base_url=base_url,
            **kwargs,
        )

        # Store output type
        self.output_type = output_type.lower()
        self.output_schema = output_schema
        self._validate_output_schema_output_type()

        # Determine provider; self.llm_kwargs is set by super().__init__ and is
        # already available here for _create_client().
        self.base_url = base_url
        if provider is not None:
            # Provider explicitly supplied — trust it as-is.
            self.provider = provider.lower()
            self.client = self._create_client(self.provider, base_url, use_vertex_ai)
        else:
            # Resolve provider (and strip a recognised ``provider/`` prefix) from
            # the model string. Unknown prefixes resolve to ``openai`` and keep
            # the full model name (e.g. OpenAI-compatible/self-hosted models).
            self.provider, self.model = self._resolve_provider_and_model(model, use_vertex_ai)
            self.client = self._create_client(self.provider, base_url, use_vertex_ai)

        # Validate that provider supports the output type
        self._validate_output_type()

        self.extra_messages = extra_messages
        self.trim_context = trim_context
        self.tools_tags = tools_tags
        self.subagents = subagents or []
        self.tool_node_name = None  # may be set to a str by _setup_tools()

        # Internal setup
        self._tool_node = self._setup_tools()

        # API style & reasoning configuration
        if api_style not in ("chat", "responses"):
            raise ValueError(f"Invalid api_style '{api_style}'. Supported: 'chat', 'responses'")
        self.api_style = api_style

        # Apply default (medium effort) when not explicitly provided;
        # True or sentinel = enable with defaults; False or None = disabled.
        if reasoning_config is REASONING_DEFAULT or reasoning_config is True:
            reasoning_config = {"effort": "medium"}
        self.reasoning_config: dict[str, Any] | None = (
            None if (reasoning_config is False or reasoning_config is None) else reasoning_config
        )  # type: ignore

        # Retry & fallback configuration
        if retry_config is True:
            self.retry_config: RetryConfig | None = DEFAULT_RETRY_CONFIG
        elif isinstance(retry_config, RetryConfig):
            self.retry_config = retry_config
        else:
            self.retry_config = None

        # Normalise fallback_models to list[tuple[str, str | None]]
        self.fallback_models: list[tuple[str, str | None]] = []
        if fallback_models:
            for entry in fallback_models:
                if isinstance(entry, str):
                    self.fallback_models.append((entry, None))  # inherit provider
                else:
                    self.fallback_models.append(tuple(entry))  # type: ignore[arg-type]

        logger.info(
            f"Agent initialized: model={model}, provider={self.provider}, "
            f"output_type={self.output_type}, has_tools={self._tool_node is not None}"
        )

        # Memory setup (via mixin) runs before skills so a memory-only Agent can
        # lazily create the internal ToolNode that both systems append to.
        self._setup_memory(memory)

        # Skills setup (via mixin)
        self._setup_skills(skills)

        # Multimodal configuration
        self.multimodal_config = multimodal_config

        # Tool use behavior controls how the agent loop proceeds after tool calls.
        self.tool_use_behavior: ToolUseBehavior | StopAtTools = normalize_tool_use_behavior(
            tool_use_behavior
        )

    def clone(self, **kwargs) -> "Agent":
        """Create a copy of this agent with modified parameters.

        Args:
            **kwargs: Parameters to override in the cloned agent.

        Returns:
            A new Agent instance with the specified modifications.

        Example:
            ```python
            # Clone agent with different model
            new_agent = agent.clone(model="gpt-4o-mini")
            ```
        """
        # Collect current config
        config = {
            "model": self.model,
            "output_type": self.output_type,
            "system_prompt": self.system_prompt,
            "tool_node": self.tool_node,
            "extra_messages": self.extra_messages,
            "trim_context": self.trim_context,
            "tools_tags": self.tools_tags,
            "reasoning_config": self.reasoning_config,
            "skills": self.skills,
            "memory": self.memory,
            "retry_config": self.retry_config,
            "fallback_models": self.fallback_models,
            "multimodal_config": self.multimodal_config,
            "output_schema": self.output_schema,
            "subagents": self.subagents,
        }
        # Override with provided kwargs
        config.update(kwargs)
        return Agent(**config)

    def as_tool(self, name: str | None = None, description: str | None = None) -> Any:
        """Convert this agent into a callable tool.

        Args:
            name: Tool name (defaults to agent name or 'agent').
            description: Tool description.

        Returns:
            A Tool instance that can be used in other graphs.

        Example:
            ```python
            # Create a specialized agent
            research_agent = Agent(
                model="gpt-4o",
                system_prompt="You are a research assistant.",
                tool_node=search_tools,
            )

            # Convert to tool for use in other agents
            research_tool = research_agent.as_tool(
                name="research", description="Research any topic using web search"
            )
            ```
        """
        from alcyoneus.utils import tool

        tool_name = name or "agent"
        tool_desc = description or f"Invoke {tool_name} agent"

        @tool(name=tool_name, description=tool_desc)
        async def agent_tool(query: str) -> str:
            """Invoke the agent as a tool."""
            # Create a temporary state with the query
            state = {"messages": [Message.text_message(query)]}
            result = await self.ainvoke(state)
            return result.get("messages", [""])[-1].content if result.get("messages") else ""

        return agent_tool

    def get_system_prompt(self) -> list[dict[str, Any]]:
        """Get the system prompt for this agent.

        Returns:
            List of system prompt message dictionaries.
        """
        return self.system_prompt

    def get_prompt(self) -> list[dict[str, Any]]:
        """Get the full prompt including system and extra messages.

        Returns:
            List of message dictionaries representing the full prompt.
        """
        prompt = list(self.system_prompt)
        if self.extra_messages:
            prompt.extend(self.extra_messages)
        return prompt

    def _validate_output_schema_output_type(self) -> None:
        """Validate compatibility between output_schema and output_type."""
        if self.output_schema is None:
            return

        if self.output_type in {"image", "video", "audio"}:
            raise ValueError(
                "output_schema can only be used with text generation. "
                "Use output_type='text' (or 'json' for legacy compatibility), "
                "or remove output_schema for media generation."
            )
