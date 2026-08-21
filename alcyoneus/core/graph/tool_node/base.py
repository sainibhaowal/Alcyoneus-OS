"""Tool execution node for TAF graph workflows.

This module provides the ToolNode class, which serves as a unified registry and executor
for callable functions from various sources including local functions and MCP (Model Context
Protocol) tools. The ToolNode is designed with a modular architecture using mixins to handle
different tool providers.

The ToolNode maintains compatibility with TAF's dependency injection system and
publishes execution events for monitoring and debugging purposes.

Typical usage example:
    ```python
    def my_tool(query: str) -> str:
        return f"Result for: {query}"


    tools = ToolNode([my_tool])
    result = await tools.invoke("my_tool", {"query": "test"}, "call_id", config, state)
    ```
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import sys
import typing as t


try:
    from injectq import Inject
except ImportError:

    class _DummyInject:
        def __getitem__(self, item):
            return None

    Inject = _DummyInject()


from alcyoneus.core.state import AgentState, ErrorBlock, Message, ToolCallBlock, ToolResultBlock
from alcyoneus.core.state.message_block import RemoteToolCallBlock
from alcyoneus.core.state.stream_emitter import StreamEmitter
from alcyoneus.runtime.publisher.events import ContentType, Event, EventModel, EventType
from alcyoneus.runtime.publisher.publish import publish_event
from alcyoneus.utils import CallbackManager

from . import deps
from .executors import KwargsResolverMixin, LocalExecMixin, MCPMixin
from .policy import PolicyConfig
from .registry import ToolRegistry
from .schema import SchemaMixin


logger = logging.getLogger("alcyoneus.graph.tool_node")


class ToolNode(
    SchemaMixin,
    LocalExecMixin,
    MCPMixin,
    KwargsResolverMixin,
):
    """A unified registry and executor for callable functions from various tool providers.

    ToolNode serves as the central hub for managing and executing tools from multiple sources:
    - Local Python functions
    - MCP (Model Context Protocol) tools

    The class uses a mixin-based architecture to separate concerns and maintain clean
    integration with different tool providers. It provides both synchronous and asynchronous
    execution methods with comprehensive event publishing and error handling.

    Attributes:
        _funcs: Dictionary mapping function names to callable functions.
        _client: Optional MCP client for remote tool execution.
        mcp_tools: List of available MCP tool names.

    Example:
        ```python
        # Define local tools
        def weather_tool(location: str) -> str:
            return f"Weather in {location}: Sunny, 25°C"


        def calculator(a: int, b: int) -> int:
            return a + b


        # Create ToolNode with local functions
        tools = ToolNode([weather_tool, calculator])

        # Execute a tool
        result = await tools.invoke(
            name="weather_tool",
            args={"location": "New York"},
            tool_call_id="call_123",
            config={"user_id": "user1"},
            state=agent_state,
        )
        ```
    """

    def __init__(
        self,
        tools: t.Iterable[t.Callable],
        client: deps.Client | None = None,  # type: ignore
        pass_user_info_to_mcp: bool = False,
        enabled_tools: list[str] | None = None,
        disabled_tools: list[str] | None = None,
        policy_config: PolicyConfig | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        """Initialize ToolNode with functions and optional MCP client.

        Args:
            tools: Iterable of callable functions to register as tools. Each function
                will be registered with its `__name__` as the tool identifier.
            client: Optional MCP (Model Context Protocol) client for remote tool access.
                Requires 'fastmcp' and 'mcp' packages to be installed.
            pass_user_info_to_mcp: If True, extracts the 'user' dictionary from the config
                and passes it as metadata to MCP tool calls. The user info will be accessible
                on the MCP server via `ctx.request_context.meta`. Defaults to False.
            enabled_tools: Optional allowlist of tool names. If provided, only these tools
                will be exposed to the agent. Mutually exclusive with disabled_tools.
            disabled_tools: Optional denylist of tool names. If provided, all tools except
                these will be exposed to the agent. Mutually exclusive with enabled_tools.
            policy_config: Optional safety policy configuration for controlling tool execution.

        Raises:
            ImportError: If MCP client is provided but required packages are not installed.
            TypeError: If any item in tools is not callable.
            ValueError: If both enabled_tools and disabled_tools are provided.

        Note:
            When using MCP client functionality, ensure you have installed the required
            dependencies with: `pip install alcyoneus[mcp]`

        Example:
            ```python
            # Create ToolNode with user info passing enabled
            tools = ToolNode([my_tool], client=mcp_client, pass_user_info_to_mcp=True)

            # When invoking, the 'user' dict from config will be sent to MCP
            result = await tools.invoke(
                name="my_tool",
                args={"param": "value"},
                tool_call_id="call_123",
                config={"user": {"id": "user1", "name": "John"}},
                state=agent_state,
            )
            # On the MCP server, access via ctx.request_context.meta
            ```
        """
        tools = list(tools)
        logger.info("Initializing ToolNode with %d tools", len(tools))

        if client is not None:
            # Read flags dynamically so tests can patch alcyoneus.graph.tool_node.HAS_*
            mod = sys.modules.get("alcyoneus.graph.tool_node")
            has_fastmcp = getattr(mod, "HAS_FASTMCP", deps.HAS_FASTMCP) if mod else deps.HAS_FASTMCP
            has_mcp = getattr(mod, "HAS_MCP", deps.HAS_MCP) if mod else deps.HAS_MCP

            if not has_fastmcp or not has_mcp:
                raise ImportError(
                    "MCP client functionality requires 'fastmcp' and 'mcp' packages. "
                    "Install with: pip install alcyoneus[mcp]"
                )
            logger.debug("ToolNode initialized with MCP client")

        # Validate tool filtering options
        if enabled_tools is not None and disabled_tools is not None:
            raise ValueError(
                "enabled_tools and disabled_tools are mutually exclusive. "
                "Provide only one or neither."
            )

        self._funcs: dict[str, t.Callable] = {}
        self._client: deps.Client | None = client  # type: ignore
        self._pass_user_info_to_mcp: bool = pass_user_info_to_mcp
        self._enabled_tools: set[str] | None = set(enabled_tools) if enabled_tools else None
        self._disabled_tools: set[str] | None = set(disabled_tools) if disabled_tools else None
        self._policy_config: PolicyConfig | None = policy_config
        self.registry = registry or ToolRegistry()

        for tool in tools:
            if not callable(tool):
                raise TypeError("ToolNode only accepts callables")
            self._funcs[tool.__name__] = tool
            self.registry.register(tool)

        self.mcp_tools: list[str] = []
        self.remote_tools: list[dict] = []
        self.remote_tool_names: list[str] = []

    def add_tool(self, tool: t.Callable) -> None:
        """Add a single tool to the ToolNode after initialization.

        This method allows dynamic addition of tools to an existing ToolNode,
        useful for cases like skills where tools need to be added programmatically.

        Args:
            tool: A callable function to register as a tool. The function will be
                registered with its `__name__` as the tool identifier.

        Raises:
            TypeError: If the provided tool is not callable.

        Example:
            ```python
            tool_node = ToolNode([existing_tool])


            def new_tool(param: str) -> str:
                return f"Result: {param}"


            tool_node.add_tool(new_tool)
            ```
        """
        if not callable(tool):
            raise TypeError("ToolNode.add_tool() only accepts callables")
        self._funcs[tool.__name__] = tool
        self.registry.register(tool)
        logger.debug(f"Added tool '{tool.__name__}' to ToolNode")

    def tool_descriptors(self):
        """Return stable metadata for local tools registered on this node."""
        return self.registry.descriptors()

    def _is_tool_enabled(self, tool_name: str) -> bool:
        """Check if a tool is enabled based on enabled_tools/disabled_tools configuration.

        Args:
            tool_name: Name of the tool to check.

        Returns:
            True if the tool is enabled, False otherwise.
        """
        # If enabled_tools is set, only allow those tools
        if self._enabled_tools is not None:
            return tool_name in self._enabled_tools

        # If disabled_tools is set, allow all except those
        if self._disabled_tools is not None:
            return tool_name not in self._disabled_tools

        # No filtering configured, allow all
        return True

    async def _all_tools_async(
        self,
        tags: set[str] | None = None,
    ) -> list[dict]:
        tools: list[dict] = self.get_local_tool(tags=tags)
        tools.extend(await self._get_mcp_tool(tags=tags))
        tools.extend(self.remote_tools)

        # Apply tool filtering
        if self._enabled_tools is not None or self._disabled_tools is not None:
            tools = [
                tool
                for tool in tools
                if self._is_tool_enabled(tool.get("function", {}).get("name", ""))
            ]

        return tools

    def set_remote_tool(self, tool_names: list[dict]) -> None:
        # already validated tool names
        self.remote_tools = tool_names
        self.remote_tool_names = [tool.get("function", {}).get("name") for tool in tool_names]

    async def all_tools(self, tags: set[str] | None = None) -> list[dict]:
        """Get all available tools from all configured providers.

        Retrieves and combines tool definitions from local functions, MCP client,
        Composio adapter, and LangChain adapter. Each tool definition includes
        the function schema with parameters and descriptions.

        Args:
            tags: Optional set of tags to filter tools. Only tools matching
                the specified tags will be included in the result.

        Returns:
            List of tool definitions in OpenAI function calling format. Each dict
            contains 'type': 'function' and 'function' with name, description,
            and parameters schema.

        Example:
            ```python
            tools = await tool_node.all_tools(tags={"weather"})
            # Returns:
            # [
            #   {
            #     "type": "function",
            #     "function": {
            #       "name": "weather_tool",
            #       "description": "Get weather information for a location",
            #       "parameters": {
            #         "type": "object",
            #         "properties": {
            #           "location": {"type": "string"}
            #         },
            #         "required": ["location"]
            #       }
            #     }
            #   }
            # ]
            ```
        """
        return await self._all_tools_async(
            tags=tags,
        )

    def all_tools_sync(
        self,
        tags: set[str] | None = None,
    ) -> list[dict]:
        """Synchronously get all available tools from all configured providers.

        This is a synchronous wrapper around the async all_tools() method.
        It uses asyncio.run() to handle async operations from MCP, Composio,
        and LangChain adapters.

        Returns:
            List of tool definitions in OpenAI function calling format.

        Note:
            Prefer using the async `all_tools()` method when possible, especially
            in async contexts, to avoid potential event loop issues.
        """
        tools: list[dict] = self.get_local_tool(tags=tags)

        if self._client:
            result = asyncio.run(self._get_mcp_tool(tags=tags))
            if result:
                tools.extend(result)

        return tools

    async def invoke(
        self,
        name: str,
        args: dict,
        tool_call_id: str,
        config: dict[str, t.Any],
        state: AgentState,
        callback_manager: CallbackManager = Inject[CallbackManager],
    ) -> dict[str, t.Any] | Message:
        """Execute a specific tool by name with the provided arguments.

        This method handles tool execution across all configured providers (local,
        MCP, Composio, LangChain) with comprehensive error handling, event publishing,
        and callback management.

        Args:
            name: The name of the tool to execute.
            args: Dictionary of arguments to pass to the tool function.
            tool_call_id: Unique identifier for this tool execution, used for
                tracking and result correlation.
            config: Configuration dictionary containing execution context and
                user-specific settings.
            state: Current agent state for context-aware tool execution.
            callback_manager: Manager for executing pre/post execution callbacks.
                Injected via dependency injection if not provided.

        Returns:
            Message object containing tool execution results, either successful
            output or error information with appropriate status indicators.

        Raises:
            The method handles all exceptions internally and returns error Messages
            rather than raising exceptions, ensuring robust execution flow.

        Example:
            ```python
            result = await tool_node.invoke(
                name="weather_tool",
                args={"location": "Paris", "units": "metric"},
                tool_call_id="call_abc123",
                config={"user_id": "user1", "session_id": "session1"},
                state=current_agent_state,
            )

            # result is a Message with tool execution results
            print(result.content)  # Tool output or error information
            ```

        Note:
            The method publishes execution events throughout the process for
            monitoring and debugging purposes. Tool execution is routed based
            on tool provider precedence: MCP → Local.
        """
        logger.info("Executing tool '%s' with %d arguments", name, len(args))
        logger.debug("Tool arguments: %s", args)

        # Check policy enforcement if configured
        if self._policy_config is not None:
            from .policy import PolicyAction

            # Determine if this is an MCP tool
            mcp_server_name = None
            if name in self.mcp_tools:
                mcp_server_name = "mcp"

            action, policy = self._policy_config.evaluate(
                name,
                mcp_server_name,
                args=args,
                context=config,
            )
            audit = config.get("audit_tool_call") if isinstance(config, dict) else None
            if audit is not None:
                audit_record = {
                    "tool": name,
                    "args": args,
                    "action": action.value,
                    "policy": policy.description if policy else None,
                    "user_id": config.get("user_id"),
                    "tenant_id": config.get("tenant_id"),
                }
                audit_result = audit("policy_decision", audit_record)
                if inspect.isawaitable(audit_result):
                    await audit_result

            if action == PolicyAction.DENY:
                logger.warning(
                    f"Tool '{name}' denied by policy: {policy.description if policy else 'No matching policy'}"  # noqa: E501
                )
                return Message.tool_message(
                    content=[
                        ErrorBlock(message=f"Tool '{name}' is denied by safety policy"),
                        ToolResultBlock(
                            call_id=tool_call_id,
                            output=f"Tool '{name}' is denied by safety policy",
                            is_error=True,
                            status="failed",
                        ),
                    ],
                    meta={
                        "function_name": name,
                        "function_argument": args,
                        "tool_call_id": tool_call_id,
                    },
                )

            if action == PolicyAction.ASK_USER:
                handler = policy.handler if policy else None
                if handler is None:
                    from .policy import default_ask_user_handler

                    handler = default_ask_user_handler

                allowed = await handler(name, args)
                if not allowed:
                    logger.warning(f"Tool '{name}' denied by user confirmation")
                    return Message.tool_message(
                        content=[
                            ErrorBlock(message=f"Tool '{name}' was not approved by user"),
                            ToolResultBlock(
                                call_id=tool_call_id,
                                output=f"Tool '{name}' was not approved by user",
                                is_error=True,
                                status="failed",
                            ),
                        ],
                        meta={
                            "function_name": name,
                            "function_argument": args,
                            "tool_call_id": tool_call_id,
                        },
                    )

        event = EventModel.default(
            config,
            data={"args": args, "tool_call_id": tool_call_id, "function_name": name},
            content_type=[ContentType.TOOL_CALL],
            event=Event.TOOL_EXECUTION,
        )
        event.node_name = name
        # Attach structured tool call block
        event.content_blocks = [ToolCallBlock(id=tool_call_id, name=name, args=args)]
        publish_event(event)
        # Check this is available in remote tools
        if name in self.remote_tool_names:
            event.metadata["is_remote"] = True
            publish_event(event)
            # This tool in remote tools, so we can not execute it locally
            # so we will return a message
            # And the graph will be interrupted here
            return Message(
                content=[RemoteToolCallBlock(id=tool_call_id, name=name, args=args)],
                role="tool",
                metadata={
                    "is_remote": True,
                },
            )

        if name in self.mcp_tools:
            event.metadata["is_mcp"] = True
            publish_event(event)
            res = await self._mcp_execute(
                name,
                args,
                tool_call_id,
                config,
                callback_manager,
            )
            event.data["message"] = res.model_dump()
            # Attach tool result block mirroring the tool output
            event.content_blocks = [
                ToolResultBlock(
                    call_id=tool_call_id,
                    output=res.model_dump(),
                )
            ]
            event.event_type = EventType.END
            event.content_type = [ContentType.TOOL_RESULT, ContentType.MESSAGE]
            publish_event(event)
            return res

        if name in self._funcs:
            event.metadata["is_mcp"] = False
            publish_event(event)
            res = await self._internal_execute(
                name,
                args,
                tool_call_id,
                config,
                state,
                callback_manager,
            )
            if isinstance(res, Message):
                event.data["message"] = res.model_dump()
                event.content_blocks = [
                    ToolResultBlock(
                        call_id=tool_call_id,
                        output=res.model_dump(),
                    )
                ]
            elif isinstance(res, dict):
                msg = res.get("messages")
                if isinstance(msg, Message):
                    event.data["message"] = msg.model_dump()
                    event.content_blocks = [
                        ToolResultBlock(
                            call_id=tool_call_id,
                            output=msg.model_dump(),
                        )
                    ]

            event.event_type = EventType.END
            event.content_type = [ContentType.TOOL_RESULT, ContentType.MESSAGE]
            publish_event(event)
            return res

        error_msg = f"Tool '{name}' not found."
        event.data["error"] = error_msg
        event.event_type = EventType.ERROR
        event.content_type = [ContentType.TOOL_RESULT, ContentType.ERROR]
        publish_event(event)
        return Message.tool_message(
            content=[
                ErrorBlock(message=error_msg),
                ToolResultBlock(
                    call_id=tool_call_id,
                    output=error_msg,
                    is_error=True,
                    status="failed",
                ),
            ],
        )

    async def stream(
        self,
        name: str,
        args: dict,
        tool_call_id: str,
        config: dict[str, t.Any],
        state: AgentState,
        emit: StreamEmitter | None = None,
        callback_manager: CallbackManager = Inject[CallbackManager],
    ) -> t.AsyncIterator[Message | dict[str, t.Any]]:
        """Execute a tool with streaming support, yielding incremental results.

        Similar to invoke() but designed for tools that can provide streaming responses
        or when you want to process results as they become available. Currently,
        most tool providers return complete results, so this method typically yields
        a single Message with the full result.

        Args:
            name: The name of the tool to execute.
            args: Dictionary of arguments to pass to the tool function.
            tool_call_id: Unique identifier for this tool execution.
            config: Configuration dictionary containing execution context.
            state: Current agent state for context-aware tool execution.
            callback_manager: Manager for executing pre/post execution callbacks.

        Yields:
            Message objects containing tool execution results or status updates.
            For most tools, this will yield a single complete result Message.

        Example:
            ```python
            async for message in tool_node.stream(
                name="data_processor",
                args={"dataset": "large_data.csv"},
                tool_call_id="call_stream123",
                config={"user_id": "user1"},
                state=current_state,
            ):
                print(f"Received: {message.content}")
                # Process each streamed result
            ```

        Note:
            The streaming interface is designed for future expansion where tools
            may provide true streaming responses. Currently, it provides a
            consistent async iterator interface over tool results.
        """
        logger.info("Executing tool '%s' with %d arguments", name, len(args))
        logger.debug("Tool arguments: %s", args)
        event = EventModel.default(
            config,
            data={"args": args, "tool_call_id": tool_call_id, "function_name": name},
            content_type=[ContentType.TOOL_CALL],
            event=Event.TOOL_EXECUTION,
        )
        event.node_name = "ToolNode"
        event.content_blocks = [ToolCallBlock(id=tool_call_id, name=name, args=args)]

        if name in self.remote_tool_names:
            event.metadata["is_remote"] = True
            publish_event(event)
            # This tool in remote tools, so we can not execute it locally
            # so we will return a message
            # And the graph will be interrupted here
            yield Message(
                content=[RemoteToolCallBlock(id=tool_call_id, name=name, args=args)],
                role="tool",
                metadata={
                    "is_remote": True,
                },
            )
            return

        if name in self.mcp_tools:
            event.metadata["function_type"] = "mcp"
            publish_event(event)
            message = await self._mcp_execute(
                name,
                args,
                tool_call_id,
                config,
                callback_manager,
            )
            event.data["message"] = message.model_dump()
            event.content_blocks = [
                ToolResultBlock(call_id=tool_call_id, output=message.model_dump())
            ]
            event.event_type = EventType.END
            event.content_type = [ContentType.TOOL_RESULT, ContentType.MESSAGE]
            publish_event(event)
            yield message
            return

        if name in self._funcs:
            event.metadata["function_type"] = "internal"
            publish_event(event)

            result = await self._internal_execute(
                name,
                args,
                tool_call_id,
                config,
                state,
                callback_manager,
                emit=emit,
            )
            if isinstance(result, Message):
                event.data["message"] = result.model_dump()
                event.content_blocks = [
                    ToolResultBlock(call_id=tool_call_id, output=result.model_dump())
                ]
            elif isinstance(result, dict):
                msg = result.get("messages")
                if isinstance(msg, Message):
                    event.data["message"] = msg.model_dump()
                    event.content_blocks = [
                        ToolResultBlock(call_id=tool_call_id, output=msg.model_dump())
                    ]
            event.event_type = EventType.END
            event.content_type = [ContentType.TOOL_RESULT, ContentType.MESSAGE]
            publish_event(event)
            yield result
            return

        error_msg = f"Tool '{name}' not found."
        event.data["error"] = error_msg
        event.event_type = EventType.ERROR
        event.content_type = [ContentType.TOOL_RESULT, ContentType.ERROR]
        publish_event(event)

        yield Message.tool_message(
            content=[
                ErrorBlock(message=error_msg),
                ToolResultBlock(
                    call_id=tool_call_id,
                    output=error_msg,
                    is_error=True,
                    status="failed",
                ),
            ],
        )
