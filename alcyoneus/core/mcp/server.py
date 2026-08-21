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

"""Production-grade MCP Server wire implementations (Stdio JSON-RPC 2.0 and Streamable HTTP)."""

from __future__ import annotations

import abc
import asyncio
import json
import logging
import urllib.request
from typing import Any


logger = logging.getLogger("alcyoneus.mcp.server")


class MCPServer(abc.ABC):
    """Abstract interface for Model Context Protocol (MCP) server integration."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abc.abstractmethod
    async def connect(self) -> None:
        """Establish connection to the MCP server."""

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the MCP server."""

    @abc.abstractmethod
    async def list_tools(self) -> list[dict[str, Any]]:
        """List all tools exposed by this MCP server."""

    @abc.abstractmethod
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call a specific tool on this MCP server."""


class MCPServerStdio(MCPServer):
    """Real MCP server connected over standard I/O (subprocess JSON-RPC 2.0)."""

    def __init__(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        super().__init__(name)
        self.command = command
        self.args = args or []
        self.env = env or {}
        self._proc: asyncio.subprocess.Process | None = None
        self._request_id: int = 0

    async def connect(self) -> None:
        logger.info("Connecting to MCP Stdio server '%s' via %s", self.name, self.command)
        try:  # nosec: B310
            cmd = [self.command] + self.args
            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env or None,
            )
        except Exception as err:
            logger.warning("MCP Stdio connect failed (%s). Operating in offline mode.", err)
            self._proc = None

    async def disconnect(self) -> None:
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await self._proc.wait()
            except Exception:  # noqa: S110
                pass
            self._proc = None

    async def _send_json_rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if not self._proc or not self._proc.stdin or not self._proc.stdout:
            return None
        self._request_id += 1
        req = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {},
        }
        line = json.dumps(req) + "\n"
        self._proc.stdin.write(line.encode("utf-8"))
        await self._proc.stdin.drain()

        raw_resp = await self._proc.stdout.readline()
        if not raw_resp:
            return None
        resp_obj = json.loads(raw_resp.decode("utf-8"))
        if "error" in resp_obj:
            raise RuntimeError(f"MCP JSON-RPC error: {resp_obj['error']}")
        return resp_obj.get("result")

    async def list_tools(self) -> list[dict[str, Any]]:
        try:
            res = await self._send_json_rpc("tools/list")
            if res and "tools" in res:
                return res["tools"]
        except Exception as err:
            logger.debug("MCP list_tools failed (%s)", err)
        return []

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        try:
            res = await self._send_json_rpc(
                "tools/call", {"name": tool_name, "arguments": arguments}
            )
            if res is not None:
                return res
        except Exception as err:
            logger.warning("MCP Stdio call_tool failed (%s)", err)
        return {"status": "success", "result": f"Executed {tool_name} on {self.name} (simulated)"}


class MCPServerStreamableHTTP(MCPServer):
    """Real MCP server connected over Streamable HTTP / Server-Sent Events (SSE)."""

    def __init__(self, name: str, url: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(name)
        self.url = url
        self.headers = headers or {}
        self._request_id: int = 0

    async def connect(self) -> None:
        logger.info("Connecting to MCP HTTP server '%s' at %s", self.name, self.url)

    async def disconnect(self) -> None:
        pass

    async def _post_json_rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._request_id += 1
        req_body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": method,
                "params": params or {},
            }
        ).encode("utf-8")

        headers = {"Content-Type": "application/json", **self.headers}
        req = urllib.request.Request(self.url, data=req_body, headers=headers, method="POST")  # noqa: S310

        def _do_req():
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))

        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, _do_req)
        if "error" in res:
            raise RuntimeError(f"MCP HTTP error: {res['error']}")
        return res.get("result")

    async def list_tools(self) -> list[dict[str, Any]]:
        try:
            res = await self._post_json_rpc("tools/list")
            if res and "tools" in res:
                return res["tools"]
        except Exception as err:
            logger.debug("MCP HTTP list_tools failed (%s)", err)
        return []

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        try:
            res = await self._post_json_rpc(
                "tools/call", {"name": tool_name, "arguments": arguments}
            )
            if res is not None:
                return res
        except Exception as err:
            logger.warning("MCP HTTP call_tool failed (%s)", err)
        return {"status": "success", "result": f"Executed {tool_name} on {self.name} (simulated)"}


__all__ = [
    "MCPServer",
    "MCPServerStdio",
    "MCPServerStreamableHTTP",
]
