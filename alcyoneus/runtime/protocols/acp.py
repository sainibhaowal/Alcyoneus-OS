from __future__ import annotations


# """
# Agent Communication Protocol (ACP)

# A standardized protocol for agent-to-agent communication in the Alcyoneus OS system.
# Provides message format, validation, and serialization for reliable agent interactions.
# """

# import uuid
# from datetime import UTC, datetime
# from enum import Enum
# from typing import Any

# from pydantic import BaseModel, Field, field_validator


# class ACPMessageType(str, Enum):
#     """Types of messages supported by ACP."""

#     REQUEST = "REQUEST"  # Agent requests action from another agent
#     RESPONSE = "RESPONSE"  # Response to a previous request
#     BROADCAST = "BROADCAST"  # Message to all agents
#     NOTIFICATION = "NOTIFICATION"  # One-way notification
#     ERROR = "ERROR"  # Error message
#     HEARTBEAT = "HEARTBEAT"  # Keep-alive message


# class MessageContent(BaseModel):
#     """Content of an ACP message."""

#     action: str = Field(..., description="Action to perform or type of content")
#     data: dict[str, Any] = Field(default_factory=dict, description="Message payload data")
#     metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


# class MessageContext(BaseModel):
#     """Context information for message routing and tracking."""

#     thread_id: str | None = Field(None, description="Conversation thread ID")
#     conversation_id: str | None = Field(None, description="Conversation ID")
#     correlation_id: str | None = Field(None, description="ID to correlate request-response pairs")
#     parent_message_id: str | None = Field(
#         None, description="ID of the parent message if this is a reply"
#     )


# class ACPMessage(BaseModel):
#     """
#     Agent Communication Protocol Message.

#     Standard message format for all agent-to-agent communications.
#     """

#     protocol_version: str = Field(default="1.0", description="ACP protocol version")
#     message_id: str = Field(
#         default_factory=lambda: str(uuid.uuid4()),
#         description="Unique message identifier",
#     )
#     message_type: ACPMessageType = Field(..., description="Type of message")
#     sender_id: str = Field(..., description="ID of the sending agent")
#     recipient_id: str = Field(
#         ...,
#         description="ID of recipient agent, or '*' for broadcast",
#     )
#     timestamp: datetime = Field(
#         default_factory=lambda: datetime.now(UTC),
#         description="Message creation timestamp",
#     )
#     content: MessageContent = Field(..., description="Message content")
#     context: MessageContext = Field(
#         default_factory=MessageContext,
#         description="Message context for routing",
#     )
#     priority: int = Field(
#         default=5, ge=1, le=10, description="Message priority (1=highest, 10=lowest)"
#     )
#     ttl: int | None = Field(None, gt=0, description="Time-to-live in seconds (optional)")

#     @field_validator("recipient_id")
#     @classmethod
#     def validate_recipient(cls, v: str) -> str:
#         """Validate recipient ID format."""
#         if not v:
#             raise ValueError("recipient_id cannot be empty")
#         # '*' is valid for broadcast
#         if v == "*":
#             return v
#         # Add more validation as needed
#         return v

#     def is_broadcast(self) -> bool:
#         """Check if this is a broadcast message."""
#         return self.recipient_id == "*"

#     def is_expired(self) -> bool:
#         """Check if message has exceeded its TTL."""
#         if self.ttl is None:
#             return False
#         elapsed = (datetime.now(UTC) - self.timestamp).total_seconds()
#         return elapsed > self.ttl

#     def to_dict(self) -> dict[str, Any]:
#         """Convert message to dictionary."""
#         return self.model_dump(mode="json")

#     def to_json(self) -> str:
#         """Serialize message to JSON string."""
#         return self.model_dump_json()

#     @classmethod
#     def from_dict(cls, data: dict[str, Any]) -> "ACPMessage":
#         """Create message from dictionary."""
#         return cls(**data)

#     @classmethod
#     def from_json(cls, json_str: str) -> "ACPMessage":
#         """Deserialize message from JSON string."""
#         return cls.model_validate_json(json_str)


# class ACPProtocol:
#     """
#     Agent Communication Protocol handler.

#     Provides utilities for creating, validating, and processing ACP messages.
#     """

#     PROTOCOL_VERSION = "1.0"

#     @staticmethod
#     def create_request(
#         sender_id: str,
#         recipient_id: str,
#         action: str,
#         data: dict[str, Any] | None = None,
#         **kwargs: Any,
#     ) -> ACPMessage:
#         """
#         Create a REQUEST message.

#         Args:
#             sender_id: ID of the sending agent
#             recipient_id: ID of the recipient agent
#             action: Action to request
#             data: Request data
#             **kwargs: Additional message fields
#         """
#         return ACPMessage(
#             message_type=ACPMessageType.REQUEST,
#             sender_id=sender_id,
#             recipient_id=recipient_id,
#             content=MessageContent(
#                 action=action,
#                 data=data or {},
#             ),
#             **kwargs,
#         )

#     @staticmethod
#     def create_response(
#         request_message: ACPMessage,
#         sender_id: str,
#         action: str,
#         data: dict[str, Any] | None = None,
#         **kwargs: Any,
#     ) -> ACPMessage:
#         """
#         Create a RESPONSE message to a previous request.

#         Args:
#             request_message: Original request message
#             sender_id: ID of the responding agent
#             action: Response action/result
#             data: Response data
#             **kwargs: Additional message fields
#         """
#         context = MessageContext(
#             correlation_id=request_message.message_id,
#             parent_message_id=request_message.message_id,
#             thread_id=request_message.context.thread_id,
#             conversation_id=request_message.context.conversation_id,
#         )

#         return ACPMessage(
#             message_type=ACPMessageType.RESPONSE,
#             sender_id=sender_id,
#             recipient_id=request_message.sender_id,
#             content=MessageContent(
#                 action=action,
#                 data=data or {},
#             ),
#             context=context,
#             **kwargs,
#         )

#     @staticmethod
#     def create_broadcast(
#         sender_id: str,
#         action: str,
#         data: dict[str, Any] | None = None,
#         **kwargs: Any,
#     ) -> ACPMessage:
#         """
#         Create a BROADCAST message to all agents.

#         Args:
#             sender_id: ID of the broadcasting agent
#             action: Broadcast action
#             data: Broadcast data
#             **kwargs: Additional message fields
#         """
#         return ACPMessage(
#             message_type=ACPMessageType.BROADCAST,
#             sender_id=sender_id,
#             recipient_id="*",
#             content=MessageContent(
#                 action=action,
#                 data=data or {},
#             ),
#             **kwargs,
#         )

#     @staticmethod
#     def create_notification(
#         sender_id: str,
#         recipient_id: str,
#         action: str,
#         data: dict[str, Any] | None = None,
#         **kwargs: Any,
#     ) -> ACPMessage:
#         """
#         Create a NOTIFICATION message (one-way, no response expected).

#         Args:
#             sender_id: ID of the sending agent
#             recipient_id: ID of the recipient agent
#             action: Notification action
#             data: Notification data
#             **kwargs: Additional message fields
#         """
#         return ACPMessage(
#             message_type=ACPMessageType.NOTIFICATION,
#             sender_id=sender_id,
#             recipient_id=recipient_id,
#             content=MessageContent(
#                 action=action,
#                 data=data or {},
#             ),
#             **kwargs,
#         )

#     @staticmethod
#     def create_error(
#         sender_id: str,
#         recipient_id: str,
#         error_message: str,
#         error_code: str | None = None,
#         original_message_id: str | None = None,
#         **kwargs: Any,
#     ) -> ACPMessage:
#         """
#         Create an ERROR message.

#         Args:
#             sender_id: ID of the sending agent
#             recipient_id: ID of the recipient agent
#             error_message: Error description
#             error_code: Optional error code
#             original_message_id: ID of message that caused the error
#             **kwargs: Additional message fields
#         """
#         data = {"error_message": error_message}
#         if error_code:
#             data["error_code"] = error_code

#         context = MessageContext()
#         if original_message_id:
#             context.parent_message_id = original_message_id

#         return ACPMessage(
#             message_type=ACPMessageType.ERROR,
#             sender_id=sender_id,
#             recipient_id=recipient_id,
#             content=MessageContent(
#                 action="error",
#                 data=data,
#             ),
#             context=context,
#             **kwargs,
#         )

#     @staticmethod
#     def create_heartbeat(sender_id: str, recipient_id: str = "*") -> ACPMessage:
#         """
#         Create a HEARTBEAT message.

#         Args:
#             sender_id: ID of the sending agent
#             recipient_id: ID of recipient (default: broadcast)
#         """
#         return ACPMessage(
#             message_type=ACPMessageType.HEARTBEAT,
#             sender_id=sender_id,
#             recipient_id=recipient_id,
#             content=MessageContent(action="heartbeat"),
#             priority=10,  # Lowest priority
#         )

#     @staticmethod
#     def validate_message(message: ACPMessage) -> tuple[bool, str | None]:
#         """
#         Validate an ACP message.

#         Returns:
#             Tuple of (is_valid, error_message)
#         """
#         try:
#             # Check if expired
#             if message.is_expired():
#                 return False, "Message has expired (TTL exceeded)"

#             # Validate protocol version
#             if message.protocol_version != ACPProtocol.PROTOCOL_VERSION:
#                 return (
#                     False,
#                     f"Unsupported protocol version: {message.protocol_version}",
#                 )

#             # Validate required fields
#             if not message.sender_id:
#                 return False, "sender_id is required"

#             if not message.recipient_id:
#                 return False, "recipient_id is required"

#             if not message.content.action:
#                 return False, "content.action is required"

#             return True, None

#         except Exception as e:
#             return False, f"Validation error: {e!s}"
"""
Agent Communication Protocol (ACP)

A standardized protocol for agent-to-agent communication in the Alcyoneus OS system.
Provides message format, validation, and serialization for reliable agent interactions.
"""

import asyncio  # noqa: E402
import logging  # noqa: E402
import uuid  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from enum import Enum  # noqa: E402
from typing import Any  # noqa: E402

from pydantic import BaseModel, Field, field_validator  # noqa: E402


logger = logging.getLogger("alcyoneus.acp")


class ACPMessageType(str, Enum):
    """Types of messages supported by ACP."""

    REQUEST = "REQUEST"  # Agent requests action from another agent
    RESPONSE = "RESPONSE"  # Response to a previous request
    BROADCAST = "BROADCAST"  # Message to all agents
    NOTIFICATION = "NOTIFICATION"  # One-way notification
    ERROR = "ERROR"  # Error message
    HEARTBEAT = "HEARTBEAT"  # Keep-alive message


class MessageContent(BaseModel):
    """Content of an ACP message."""

    action: str = Field(..., description="Action to perform or type of content")
    data: dict[str, Any] = Field(default_factory=dict, description="Message payload data")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class MessageContext(BaseModel):
    """Context information for message routing and tracking."""

    thread_id: str | None = Field(None, description="Conversation thread ID")
    conversation_id: str | None = Field(None, description="Conversation ID")
    correlation_id: str | None = Field(None, description="ID to correlate request-response pairs")
    parent_message_id: str | None = Field(
        None, description="ID of the parent message if this is a reply"
    )


class ACPMessage(BaseModel):
    """
    Agent Communication Protocol Message.

    Standard message format for all agent-to-agent communications.
    """

    protocol_version: str = Field(default="1.0", description="ACP protocol version")
    message_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique message identifier",
    )
    message_type: ACPMessageType = Field(..., description="Type of message")
    sender_id: str = Field(..., description="ID of the sending agent")
    recipient_id: str = Field(
        ...,
        description="ID of recipient agent, or '*' for broadcast",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Message creation timestamp",
    )
    content: MessageContent = Field(..., description="Message content")
    context: MessageContext = Field(
        default_factory=MessageContext,
        description="Message context for routing",
    )
    priority: int = Field(
        default=5, ge=1, le=10, description="Message priority (1=highest, 10=lowest)"
    )
    ttl: int | None = Field(None, gt=0, description="Time-to-live in seconds (optional)")

    @field_validator("recipient_id")
    @classmethod
    def validate_recipient(cls, v: str) -> str:
        """Validate recipient ID format."""
        if not v:
            raise ValueError("recipient_id cannot be empty")
        # '*' is valid for broadcast
        if v == "*":
            return v
        # Add more validation as needed
        return v

    def is_broadcast(self) -> bool:
        """Check if this is a broadcast message."""
        return self.recipient_id == "*"

    def is_expired(self) -> bool:
        """Check if message has exceeded its TTL."""
        if self.ttl is None:
            return False
        elapsed = (datetime.now(UTC) - self.timestamp).total_seconds()
        return elapsed > self.ttl

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary."""
        return self.model_dump(mode="json")

    def to_json(self) -> str:
        """Serialize message to JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ACPMessage:
        """Create message from dictionary."""
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> ACPMessage:
        """Deserialize message from JSON string."""
        return cls.model_validate_json(json_str)


class ACPProtocol:
    """
    Agent Communication Protocol handler.

    Provides utilities for creating, validating, and processing ACP messages.
    """

    PROTOCOL_VERSION = "1.0"

    @staticmethod
    def create_request(
        sender_id: str,
        recipient_id: str,
        action: str,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ACPMessage:
        """
        Create a REQUEST message.

        Args:
            sender_id: ID of the sending agent
            recipient_id: ID of the recipient agent
            action: Action to request
            data: Request data
            **kwargs: Additional message fields
        """
        return ACPMessage(
            message_type=ACPMessageType.REQUEST,
            sender_id=sender_id,
            recipient_id=recipient_id,
            content=MessageContent(
                action=action,
                data=data or {},
            ),
            **kwargs,
        )

    @staticmethod
    def create_response(
        request_message: ACPMessage,
        sender_id: str,
        action: str,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ACPMessage:
        """
        Create a RESPONSE message to a previous request.

        Args:
            request_message: Original request message
            sender_id: ID of the responding agent
            action: Response action/result
            data: Response data
            **kwargs: Additional message fields
        """
        context = MessageContext(
            correlation_id=request_message.message_id,
            parent_message_id=request_message.message_id,
            thread_id=request_message.context.thread_id,
            conversation_id=request_message.context.conversation_id,
        )

        return ACPMessage(
            message_type=ACPMessageType.RESPONSE,
            sender_id=sender_id,
            recipient_id=request_message.sender_id,
            content=MessageContent(
                action=action,
                data=data or {},
            ),
            context=context,
            **kwargs,
        )

    @staticmethod
    def create_broadcast(
        sender_id: str,
        action: str,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ACPMessage:
        """
        Create a BROADCAST message to all agents.

        Args:
            sender_id: ID of the broadcasting agent
            action: Broadcast action
            data: Broadcast data
            **kwargs: Additional message fields
        """
        return ACPMessage(
            message_type=ACPMessageType.BROADCAST,
            sender_id=sender_id,
            recipient_id="*",
            content=MessageContent(
                action=action,
                data=data or {},
            ),
            **kwargs,
        )

    @staticmethod
    def create_notification(
        sender_id: str,
        recipient_id: str,
        action: str,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ACPMessage:
        """
        Create a NOTIFICATION message (one-way, no response expected).

        Args:
            sender_id: ID of the sending agent
            recipient_id: ID of the recipient agent
            action: Notification action
            data: Notification data
            **kwargs: Additional message fields
        """
        return ACPMessage(
            message_type=ACPMessageType.NOTIFICATION,
            sender_id=sender_id,
            recipient_id=recipient_id,
            content=MessageContent(
                action=action,
                data=data or {},
            ),
            **kwargs,
        )

    @staticmethod
    def create_error(
        sender_id: str,
        recipient_id: str,
        error_message: str,
        error_code: str | None = None,
        original_message_id: str | None = None,
        **kwargs: Any,
    ) -> ACPMessage:
        """
        Create an ERROR message.

        Args:
            sender_id: ID of the sending agent
            recipient_id: ID of the recipient agent
            error_message: Error description
            error_code: Optional error code
            original_message_id: ID of message that caused the error
            **kwargs: Additional message fields
        """
        data = {"error_message": error_message}
        if error_code:
            data["error_code"] = error_code

        context = MessageContext()
        if original_message_id:
            context.parent_message_id = original_message_id

        return ACPMessage(
            message_type=ACPMessageType.ERROR,
            sender_id=sender_id,
            recipient_id=recipient_id,
            content=MessageContent(
                action="error",
                data=data,
            ),
            context=context,
            **kwargs,
        )

    @staticmethod
    def create_heartbeat(sender_id: str, recipient_id: str = "*") -> ACPMessage:
        """
        Create a HEARTBEAT message.

        Args:
            sender_id: ID of the sending agent
            recipient_id: ID of recipient (default: broadcast)
        """
        return ACPMessage(
            message_type=ACPMessageType.HEARTBEAT,
            sender_id=sender_id,
            recipient_id=recipient_id,
            content=MessageContent(action="heartbeat"),
            priority=10,  # Lowest priority
        )

    @staticmethod
    def validate_message(message: ACPMessage) -> tuple[bool, str | None]:
        """
        Validate an ACP message.

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check if expired
            if message.is_expired():
                return False, "Message has expired (TTL exceeded)"

            # Validate protocol version
            if message.protocol_version != ACPProtocol.PROTOCOL_VERSION:
                return (
                    False,
                    f"Unsupported protocol version: {message.protocol_version}",
                )

            # Validate required fields
            if not message.sender_id:
                return False, "sender_id is required"

            if not message.recipient_id:
                return False, "recipient_id is required"

            if not message.content.action:
                return False, "content.action is required"

            return True, None

        except Exception as e:
            return False, f"Validation error: {e!s}"


class ACPTransportError(RuntimeError):
    """Raised when an ACP message cannot be delivered or decoded."""


class ACPHttpTransport:
    """Small async HTTP transport for ACP JSON messages.

    ACP deliberately keeps transport separate from message semantics. The
    endpoint must accept a JSON ACP message and return a JSON ACP message.
    """

    def __init__(
        self, endpoint: str, *, timeout: float = 30.0, headers: dict[str, str] | None = None
    ):
        self.endpoint = endpoint
        self.timeout = timeout
        self.headers = {"content-type": "application/json", **(headers or {})}

    async def send(self, message: ACPMessage) -> ACPMessage:
        try:
            import httpx
        except ImportError as exc:
            raise ACPTransportError("ACP HTTP transport requires httpx") from exc
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.endpoint, content=message.to_json(), headers=self.headers
                )
                response.raise_for_status()
                return ACPMessage.from_dict(response.json())
        except Exception as exc:
            raise ACPTransportError(f"ACP delivery failed: {exc}") from exc


class ACPInMemoryTransport:
    """Deterministic transport useful for local composition and tests."""

    def __init__(self) -> None:
        import asyncio

        self._queue: asyncio.Queue[ACPMessage] = asyncio.Queue()

    async def send(self, message: ACPMessage) -> ACPMessage:
        await self._queue.put(message)
        return message

    async def receive(self, timeout: float | None = None) -> ACPMessage:
        import asyncio

        if timeout is None:
            return await self._queue.get()
        return await asyncio.wait_for(self._queue.get(), timeout=timeout)


class ACPClient:
    """ACP client for communicating with ACP servers.

    Supports agent discovery, task delegation, and streaming responses.
    """

    def __init__(
        self,
        transport: ACPHttpTransport | ACPInMemoryTransport,
        agent_id: str,
        timeout: float = 30.0,
    ):
        self.transport = transport
        self.agent_id = agent_id
        self.timeout = timeout
        self._pending_requests: dict[str, asyncio.Future] = {}
        self._running = False

    async def send_request(
        self,
        recipient_id: str,
        action: str,
        data: dict[str, Any] | None = None,
        wait_for_response: bool = True,
        ttl: int | None = None,
    ) -> ACPMessage | None:
        """Send a request and optionally wait for response."""
        msg = ACPProtocol.create_request(
            sender_id=self.agent_id,
            recipient_id=recipient_id,
            action=action,
            data=data,
            ttl=ttl,
        )
        response = await self.transport.send(msg)

        if wait_for_response:
            return response
        return None

    async def send_notification(
        self,
        recipient_id: str,
        action: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Send a one-way notification."""
        msg = ACPProtocol.create_notification(
            sender_id=self.agent_id,
            recipient_id=recipient_id,
            action=action,
            data=data,
        )
        await self.transport.send(msg)

    async def broadcast(
        self,
        action: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Broadcast to all agents."""
        msg = ACPProtocol.create_broadcast(
            sender_id=self.agent_id,
            action=action,
            data=data,
        )
        await self.transport.send(msg)

    async def resolve_agent_card(self, agent_url: str) -> dict[str, Any] | None:
        """Resolve agent card from A2A endpoint."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{agent_url.rstrip('/')}/.well-known/agent.json")
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.error(f"Failed to resolve agent card: {e}")
        return None

    async def delegate_task(
        self,
        agent_url: str,
        task: str,
        input_data: dict[str, Any],
        stream: bool = False,
    ) -> Any:
        """Delegate a task to another agent via A2A/ACP."""
        if stream:
            return self._stream_task(agent_url, task, input_data)

        # Use ACP request
        return await self.send_request(
            recipient_id=agent_url,
            action="execute_task",
            data={"task": task, "input": input_data},
        )

    async def _stream_task(
        self,
        agent_url: str,
        task: str,
        input_data: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream task execution updates."""
        msg = ACPProtocol.create_request(
            sender_id=self.agent_id,
            recipient_id=agent_url,
            action="execute_task_stream",
            data={"task": task, "input": input_data},
        )
        # Send initial request
        await self.transport.send(msg)

        # Stream responses
        while True:
            try:
                response = await asyncio.wait_for(self.transport.receive(), timeout=self.timeout)
                yield response.to_dict()
                if response.message_type in (ACPMessageType.RESPONSE, ACPMessageType.ERROR):
                    break
            except TimeoutError:
                break

    async def heartbeat(self, interval: float = 30.0) -> None:
        """Send periodic heartbeats."""
        self._running = True
        while self._running:
            await self.broadcast("heartbeat")
            await asyncio.sleep(interval)

    def stop_heartbeat(self) -> None:
        self._running = False


class ACPServer:
    """ACP server for receiving and processing agent messages."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.handlers: dict[str, callable] = {}
        self._running = False

    def register_handler(self, action: str, handler: callable) -> None:
        """Register a handler for a specific action."""
        self.handlers[action] = handler

    async def handle_message(self, message: ACPMessage) -> ACPMessage:
        """Process incoming message and return response."""
        if message.message_type == ACPMessageType.REQUEST:
            handler = self.handlers.get(message.content.action)
            if handler:
                try:
                    result = await handler(message.content.data)
                    return ACPProtocol.create_response(
                        request_message=message,
                        sender_id=self.agent_id,
                        action=message.content.action,
                        data=result,
                    )
                except Exception as e:
                    return ACPProtocol.create_error(
                        sender_id=self.agent_id,
                        recipient_id=message.sender_id,
                        error_message=str(e),
                        original_message_id=message.message_id,
                    )
            else:
                return ACPProtocol.create_error(
                    sender_id=self.agent_id,
                    recipient_id=message.sender_id,
                    error_message=f"No handler for action: {message.content.action}",
                    error_code="ACTION_NOT_FOUND",
                    original_message_id=message.message_id,
                )
        elif message.message_type == ACPMessageType.HEARTBEAT:
            return ACPProtocol.create_heartbeat(self.agent_id, message.sender_id)
        return ACPProtocol.create_error(
            sender_id=self.agent_id,
            recipient_id=message.sender_id,
            error_message="Unsupported message type",
            error_code="INVALID_MESSAGE_TYPE",
        )

    async def run_http(self, host: str = "0.0.0.0", port: int = 8080) -> None:  # noqa: S104
        """Run as HTTP server."""
        from aiohttp import web

        async def handle(request):
            data = await request.json()
            msg = ACPMessage.from_dict(data)
            response = await self.handle_message(msg)
            return web.json_response(response.to_dict())

        app = web.Application()
        app.router.add_post("/", handle)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        logger.info(f"ACP server running on {host}:{port}")
        try:
            while self._running:
                await asyncio.sleep(1)
        finally:
            await runner.cleanup()
