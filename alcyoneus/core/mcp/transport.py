"""MCP Transport implementations: stdio, SSE, WebSocket with capability negotiation and caching."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import aiohttp


logger = logging.getLogger("alcyoneus.mcp.transport")


@dataclass
class MCPCapabilities:
    """MCP server/client capabilities."""

    tools: bool = True
    resources: bool = True
    prompts: bool = True
    logging: bool = True
    completions: bool = False
    sampling: bool = False
    experimental: dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPServerInfo:
    """MCP server metadata."""

    name: str
    version: str
    protocol_version: str = "2024-11-05"
    capabilities: MCPCapabilities = field(default_factory=MCPCapabilities)
    instructions: str | None = None


class MCPTransport(ABC):
    """Abstract MCP transport layer."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def send(self, message: dict[str, Any]) -> None: ...

    @abstractmethod
    async def receive(self) -> AsyncIterator[dict[str, Any]]: ...

    @abstractmethod
    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any: ...


class StdioTransport(MCPTransport):
    """Stdio JSON-RPC 2.0 transport."""

    def __init__(
        self, command: str, args: list[str] | None = None, env: dict[str, str] | None = None
    ):
        self.command = command
        self.args = args or []
        self.env = env or {}
        self._proc: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}

    async def connect(self) -> None:
        cmd = [self.command] + self.args
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.env or None,
        )
        asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        if not self._proc or not self._proc.stdout:
            return
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode())
                if "id" in msg and msg["id"] in self._pending:
                    fut = self._pending.pop(msg["id"])
                    if "error" in msg:
                        fut.set_exception(RuntimeError(msg["error"]))
                    else:
                        fut.set_result(msg.get("result"))
                else:
                    # Notification - handle via receive()
                    pass
            except Exception as e:
                logger.error("Stdio parse error: %s", e)

    async def disconnect(self) -> None:
        if self._proc:
            self._proc.terminate()
            await self._proc.wait()

    async def send(self, message: dict[str, Any]) -> None:
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("Not connected")
        self._proc.stdin.write((json.dumps(message) + "\n").encode())
        await self._proc.stdin.drain()

    async def receive(self) -> AsyncIterator[dict[str, Any]]:
        # Notifications would be yielded here
        while True:
            await asyncio.sleep(1)

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if not self._proc:
            raise RuntimeError("Not connected")
        self._request_id += 1
        req = {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params or {}}
        fut = asyncio.get_event_loop().create_future()
        self._pending[self._request_id] = fut
        await self.send(req)
        return await asyncio.wait_for(fut, timeout=30)


class SSETransport(MCPTransport):
    """Server-Sent Events transport for MCP."""

    def __init__(self, url: str, headers: dict[str, str] | None = None):
        self.url = url
        self.headers = headers or {}
        self._session: aiohttp.ClientSession | None = None
        self._sse_response: aiohttp.ClientResponse | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._notification_queue: asyncio.Queue = asyncio.Queue()

    async def connect(self) -> None:
        self._session = aiohttp.ClientSession()
        self._sse_response = await self._session.get(
            self.url, headers={"Accept": "text/event-stream", **self.headers}
        )
        asyncio.create_task(self._sse_read_loop())

    async def _sse_read_loop(self) -> None:
        if not self._sse_response:
            return
        async for line in self._sse_response.content:
            line = line.decode().strip()
            if line.startswith("data: "):
                data = line[6:]
                if data:
                    try:
                        msg = json.loads(data)
                        if "id" in msg and msg["id"] in self._pending:
                            fut = self._pending.pop(msg["id"])
                            if "error" in msg:
                                fut.set_exception(RuntimeError(msg["error"]))
                            else:
                                fut.set_result(msg.get("result"))
                        else:
                            await self._notification_queue.put(msg)
                    except Exception as e:
                        logger.error("SSE parse error: %s", e)

    async def disconnect(self) -> None:
        if self._sse_response:
            self._sse_response.close()
        if self._session:
            await self._session.close()

    async def send(self, message: dict[str, Any]) -> None:
        if not self._session:
            raise RuntimeError("Not connected")
        # POST to same endpoint
        async with self._session.post(self.url, json=message, headers=self.headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"SSE send failed: {resp.status}")

    async def receive(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            msg = await self._notification_queue.get()
            yield msg

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._request_id += 1
        req = {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params or {}}
        fut = asyncio.get_event_loop().create_future()
        self._pending[self._request_id] = fut
        await self.send(req)
        return await asyncio.wait_for(fut, timeout=30)


class WebSocketTransport(MCPTransport):
    """WebSocket transport for MCP (bidirectional)."""

    def __init__(self, url: str, headers: dict[str, str] | None = None):
        self.url = url
        self.headers = headers or {}
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._notification_queue: asyncio.Queue = asyncio.Queue()

    async def connect(self) -> None:
        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(self.url, headers=self.headers)
        asyncio.create_task(self._ws_read_loop())

    async def _ws_read_loop(self) -> None:
        if not self._ws:
            return
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    if "id" in data and data["id"] in self._pending:
                        fut = self._pending.pop(data["id"])
                        if "error" in data:
                            fut.set_exception(RuntimeError(data["error"]))
                        else:
                            fut.set_result(data.get("result"))
                    else:
                        await self._notification_queue.put(data)
                except Exception as e:
                    logger.error("WS parse error: %s", e)

    async def disconnect(self) -> None:
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()

    async def send(self, message: dict[str, Any]) -> None:
        if not self._ws:
            raise RuntimeError("Not connected")
        await self._ws.send_json(message)

    async def receive(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            msg = await self._notification_queue.get()
            yield msg

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._request_id += 1
        req = {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params or {}}
        fut = asyncio.get_event_loop().create_future()
        self._pending[self._request_id] = fut
        await self.send(req)
        return await asyncio.wait_for(fut, timeout=30)


class MCPClient:
    """High-level MCP client with capability negotiation and tool caching."""

    def __init__(self, transport: MCPTransport):
        self.transport = transport
        self._capabilities: MCPCapabilities | None = None
        self._server_info: MCPServerInfo | None = None
        self._tools_cache: list[dict[str, Any]] | None = None
        self._cache_ttl = 300  # 5 minutes
        self._cache_time = 0

    async def connect(self) -> MCPServerInfo:
        await self.transport.connect()
        await self._negotiate_capabilities()
        return self._server_info

    async def _negotiate_capabilities(self) -> None:
        """Perform MCP initialization handshake."""
        result = await self.transport.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                "clientInfo": {"name": "alcyoneus", "version": "1.0.0"},
            },
        )
        if result:
            self._server_info = MCPServerInfo(
                name=result.get("serverInfo", {}).get("name", "unknown"),
                version=result.get("serverInfo", {}).get("version", "0.0.0"),
                protocol_version=result.get("protocolVersion", "2024-11-05"),
                capabilities=MCPCapabilities(**result.get("capabilities", {})),
                instructions=result.get("instructions"),
            )
            self._capabilities = self._server_info.capabilities
            await self.transport.send({"jsonrpc": "2.0", "method": "initialized", "params": {}})

    async def disconnect(self) -> None:
        await self.transport.disconnect()

    async def list_tools(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        if (
            not force_refresh
            and self._tools_cache
            and time.time() - self._cache_time < self._cache_ttl
        ):
            return self._tools_cache
        result = await self.transport.request("tools/list")
        if result and "tools" in result:
            self._tools_cache = result["tools"]
            self._cache_time = time.time()
            return self._tools_cache
        return []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = await self.transport.request("tools/call", {"name": name, "arguments": arguments})
        return result

    async def list_resources(self) -> list[dict[str, Any]]:
        if not self._capabilities or not self._capabilities.resources:
            return []
        result = await self.transport.request("resources/list")
        return result.get("resources", []) if result else []

    async def read_resource(self, uri: str) -> dict[str, Any]:
        result = await self.transport.request("resources/read", {"uri": uri})
        return result

    async def list_prompts(self) -> list[dict[str, Any]]:
        if not self._capabilities or not self._capabilities.prompts:
            return []
        result = await self.transport.request("prompts/list")
        return result.get("prompts", []) if result else []

    async def get_prompt(self, name: str, arguments: dict[str, Any]) -> Any:
        result = await self.transport.request("prompts/get", {"name": name, "arguments": arguments})
        return result


def create_transport(transport_type: str, **kwargs) -> MCPTransport:
    """Factory for creating MCP transports."""
    if transport_type == "stdio":
        return StdioTransport(kwargs["command"], kwargs.get("args"), kwargs.get("env"))
    if transport_type == "sse":
        return SSETransport(kwargs["url"], kwargs.get("headers"))
    if transport_type == "websocket":
        return WebSocketTransport(kwargs["url"], kwargs.get("headers"))
    raise ValueError(f"Unknown transport: {transport_type}")


__all__ = [
    "MCPCapabilities",
    "MCPClient",
    "MCPServerInfo",
    "MCPTransport",
    "SSETransport",
    "StdioTransport",
    "WebSocketTransport",
    "create_transport",
]
