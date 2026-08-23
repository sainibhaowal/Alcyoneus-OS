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
"""Production-grade Remote Graph Execution and Hosting.

This module provides two complementary pieces:

* :class:`RemoteGraph` — a graph handle that forwards ``invoke``/``ainvoke``/
  ``stream``/``astream``/``stream_events``/``astream_events`` calls to a
  compiled graph either in-process or over HTTP to a :class:`GraphServer`.
* :class:`GraphServer` — a production-grade HTTP server (aiohttp-based)
  that hosts a compiled graph and executes it on request. Supports TLS,
  authentication, connection pooling, retries, and health checks.

Both share the same execution interface so callers can transparently swap a
local graph for a remote one.
"""

from __future__ import annotations

import asyncio
import json
import ssl
import time
from collections.abc import AsyncIterator, Callable, Generator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import aiohttp
from aiohttp import web
from aiohttp.client import ClientTimeout
from aiohttp.connector import TCPConnector

from alcyoneus.core.state import Message
from alcyoneus.utils.callable_utils import run_coroutine
from alcyoneus.utils.constants import ResponseGranularity


@dataclass
class RemoteGraphConfig:
    """Configuration for RemoteGraph client."""

    url: str
    api_key: str | None = None
    timeout: float = 60.0
    connect_timeout: float = 10.0
    max_retries: int = 3
    retry_backoff: float = 0.5
    max_connections: int = 100
    max_keepalive_connections: int = 20
    tls_verify: bool = True
    custom_headers: dict[str, str] = field(default_factory=dict)
    auth_provider: Callable[[], str] | None = None


@dataclass
class GraphServerConfig:
    """Configuration for GraphServer."""

    host: str = "127.0.0.1"
    port: int = 8080
    timeout: float = 60.0
    max_request_size: int = 10 * 1024 * 1024  # 10MB
    rate_limit: int = 100  # requests per minute
    enable_tls: bool = False
    ssl_cert: str | None = None
    ssl_key: str | None = None
    api_keys: set[str] = field(default_factory=set)
    enable_cors: bool = True
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    request_timeout: float = 300.0
    keepalive_timeout: float = 75.0
    max_concurrent_requests: int = 1000


def _serialize_messages(messages: list) -> list[dict[str, Any]]:
    """Convert Message objects to plain dicts."""
    return [m.model_dump() for m in messages]


def _deserialize_messages(payload: Any) -> list:
    """Convert serialized message dicts back to Message objects."""
    if not payload:
        return []
    items = payload if isinstance(payload, list) else [payload]
    return [Message.model_validate(m) for m in items]


def _payload_input(input_data: dict[str, Any]) -> dict[str, Any]:
    """Convert input to a JSON-serializable dict."""
    payload: dict[str, Any] = {}
    for k, v in input_data.items():
        if k == "messages" and isinstance(v, list):
            payload[k] = _serialize_messages(v)
        else:
            payload[k] = v
    return payload


def _deserialize_state(state_payload: Any) -> Any:
    if state_payload is None:
        return None
    if isinstance(state_payload, dict) and "messages" in state_payload:
        return {
            **state_payload,
            "messages": _deserialize_messages(state_payload.get("messages", [])),
        }
    return state_payload


def _restore_input(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert serialized input back into a runnable dict."""
    restored = dict(payload)
    if "messages" in restored:
        restored["messages"] = _deserialize_messages(restored["messages"])
    return restored


def _client_ssl_context(tls_verify: bool) -> ssl.SSLContext | None:
    """Create a client-side SSL context (verifies the remote server)."""
    context = ssl.create_default_context()
    if not tls_verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


class RemoteGraph:
    """A graph handle that forwards execution to a local or remote graph.

    Args:
        graph: A compiled graph to wrap (in-process execution).
        config: RemoteGraphConfig with URL, auth, timeouts, retries, etc.
    """

    def __init__(
        self,
        graph: Any | None = None,
        config: RemoteGraphConfig | None = None,
        # Legacy params for backward compat
        graph_legacy: Any | None = None,
        url: str | None = None,
        timeout: float = 60.0,
    ):
        # Handle legacy params
        if config is None:
            if graph_legacy is not None:
                self.graph = graph_legacy
            elif url is not None:
                self.graph = None
                self._config = RemoteGraphConfig(url=url, timeout=timeout)
            else:
                self.graph = graph
                self._config = None
        else:
            self.graph = graph
            self._config = config

        # Initialize HTTP session lazily
        self._session: aiohttp.ClientSession | None = None
        self._connector: TCPConnector | None = None
        self._sessions: list[aiohttp.ClientSession] = []
        self._session_loop: Any = None

    @property
    def _url(self) -> str:
        return self._config.url.rstrip("/") if self._config else ""

    @property
    def _timeout(self) -> float:
        return self._config.timeout if self._config else 60.0

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    @property
    def nodes(self) -> dict[str, Any]:
        """Return the wrapped graph's nodes (local mode only)."""
        if self.graph is None:
            return {}
        return getattr(self.graph, "nodes", {})

    def get_graph(self) -> Any:
        """Return the underlying graph definition (local mode)."""
        return self.graph

    def _ensure_session(self) -> aiohttp.ClientSession:
        """Create or return an HTTP client session bound to the current loop."""
        running = asyncio.get_running_loop() if self._session is not None else None
        if self._session is not None and not self._session.closed:
            if self._session_loop is running:
                return self._session
            # Current loop differs (sync wrappers spin up their own loop):
            # reuse an existing session for this loop, else create one.
            for sess in self._sessions:
                if not sess.closed and getattr(sess, "_loop", None) is running:
                    return sess
        timeout = ClientTimeout(
            total=self._config.timeout,
            connect=self._config.connect_timeout,
            sock_read=self._config.timeout,
        )
        ssl_context = _client_ssl_context(self._config.tls_verify)
        connector = TCPConnector(
            limit=self._config.max_connections,
            limit_per_host=self._config.max_keepalive_connections,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
            keepalive_timeout=30,
            ssl=ssl_context,
        )
        session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "alcyoneus-remote-graph/1.0",
                **self._config.custom_headers,
            },
        )
        self._sessions.append(session)
        self._session = session
        self._connector = connector
        self._session_loop = running
        return session

    async def close(self) -> None:
        """Close the HTTP session and connector."""
        for sess in self._sessions:
            if not sess.closed:
                try:
                    await sess.close()
                except Exception:  # noqa: S110
                    pass
        if self._connector and not self._connector.closed:
            await self._connector.close()
        self._sessions.clear()
        self._session = None
        self._connector = None

    async def __aenter__(self) -> RemoteGraph:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    @property
    def graph_def(self) -> Any:
        """Return the underlying graph definition (local mode)."""
        return self.graph

    # ------------------------------------------------------------------
    # Invocation
    # ------------------------------------------------------------------
    def invoke(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any] | None = None,
        response_granularity: ResponseGranularity = "low",
        debug: bool | None = None,
    ) -> dict[str, Any]:
        """Execute the graph synchronously."""
        return run_coroutine(self.ainvoke(input_data, config, response_granularity, debug=debug))

    async def ainvoke(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any] | None = None,
        response_granularity: ResponseGranularity = "low",
        debug: bool | None = None,
    ) -> dict[str, Any]:
        """Execute the graph asynchronously."""
        if self._config and self._config.url:
            return await self._http_invoke(input_data, config, response_granularity)
        if self.graph is None:
            raise ValueError("RemoteGraph requires either a graph or a URL config")
        return await self.graph.ainvoke(
            input_data,
            config,
            response_granularity,
            debug=debug,
        )

    def stream(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any] | None = None,
        response_granularity: ResponseGranularity = "low",
        stream_mode: str | list[str] | None = None,
        debug: bool | None = None,
    ) -> Generator[Any]:
        """Stream graph execution synchronously (true sync via thread pool)."""
        # Use a dedicated event loop in a thread for true sync behavior
        import concurrent.futures

        def _run_async_stream():
            async def _stream():
                async for chunk in self.astream(
                    input_data,
                    config,
                    response_granularity,
                    stream_mode=stream_mode,
                    debug=debug,
                ):
                    yield chunk

            loop = asyncio.new_event_loop()
            try:

                async def _collect():
                    results = []
                    async for chunk in _stream():
                        results.append(chunk)
                    return results

                return loop.run_until_complete(_collect())
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_async_stream)
            yield from future.result()

    async def astream(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any] | None = None,
        response_granularity: ResponseGranularity = "low",
        stream_mode: str | list[str] | None = None,
        debug: bool | None = None,
    ) -> AsyncIterator[Any]:
        """Stream graph execution asynchronously."""
        if self._config and self._config.url:
            result = await self._http_invoke(input_data, config, response_granularity)
            yield {"event": "values", "data": result}
            return
        if self.graph is None:
            raise ValueError("RemoteGraph requires either a graph or a URL config")
        async for chunk in self.graph.astream(
            input_data,
            config,
            response_granularity,
            stream_mode=stream_mode,
            debug=debug,
        ):
            yield chunk

    async def astream_events(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any] | None = None,
        response_granularity: ResponseGranularity = "low",
        stream_mode: str | list[str] | None = None,
        debug: bool | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream graph execution as structured events (GraphRunStream v3)."""
        if self._config and self._config.url:
            async for event in self._http_stream_events(input_data, config, response_granularity):
                yield event
            return
        if self.graph is None:
            raise ValueError("RemoteGraph requires either a graph or a URL config")
        if hasattr(self.graph, "astream_events"):
            async for event in self.graph.astream_events(
                input_data,
                config,
                response_granularity,
                stream_mode=stream_mode,
                debug=debug,
            ):
                yield event
        else:
            # Fallback: convert stream chunks to events
            async for chunk in self.astream(
                input_data, config, response_granularity, stream_mode, debug
            ):
                yield {"event": "message", "data": chunk, "timestamp": datetime.now().isoformat()}

    def stream_events(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any] | None = None,
        response_granularity: ResponseGranularity = "low",
        stream_mode: str | list[str] | None = None,
        debug: bool | None = None,
    ) -> Generator[dict[str, Any]]:
        """Stream graph execution as structured events synchronously (true sync)."""
        import concurrent.futures

        def _run_async_events():
            async def _events():
                async for event in self.astream_events(
                    input_data,
                    config,
                    response_granularity,
                    stream_mode=stream_mode,
                    debug=debug,
                ):
                    yield event

            loop = asyncio.new_event_loop()
            try:

                async def _collect():
                    results = []
                    async for event in _events():
                        results.append(event)
                    return results

                return loop.run_until_complete(_collect())
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_async_events)
            yield from future.result()

    # ------------------------------------------------------------------
    # HTTP transport with retries, auth, connection pooling
    # ------------------------------------------------------------------
    def _get_auth_header(self) -> dict[str, str]:
        """Get authentication header."""
        headers = dict(self._config.custom_headers) if self._config else {}
        if self._config and self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        if self._config and self._config.auth_provider:
            try:
                token = self._config.auth_provider()
                if token:
                    headers["Authorization"] = f"Bearer {token}"
            except Exception:  # noqa: S110
                pass
        return headers

    async def _http_invoke(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any] | None,
        response_granularity: ResponseGranularity,
    ) -> dict[str, Any]:
        """Execute graph via HTTP with retries."""
        if self._config is None or not self._config.url:
            raise ValueError("RemoteGraph requires a configured URL (config.url)")
        payload = {
            "input": _payload_input(input_data),
            "config": config or {},
            "response_granularity": str(response_granularity),
        }
        url = f"{self._url}/invoke"
        headers = self._get_auth_header()

        last_error = None
        for attempt in range(self._config.max_retries + 1):
            try:
                session = self._ensure_session()
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 429 and attempt < self._config.max_retries:
                        await asyncio.sleep(self._config.retry_backoff * (2**attempt))
                        continue
                    resp.raise_for_status()
                    response = await resp.json()
                    raw_input = response.get("input", response.get("result", {}))
                    return {
                        "messages": _deserialize_messages(raw_input.get("messages", [])),
                        "state": _deserialize_state(raw_input.get("state")),
                        **({k: v for k, v in raw_input.items() if k not in ("messages", "state")}),
                    }
            except (TimeoutError, aiohttp.ClientError) as e:
                last_error = e
                if attempt < self._config.max_retries:
                    await asyncio.sleep(self._config.retry_backoff * (2**attempt))
                continue
        raise last_error or RuntimeError("HTTP invoke failed after retries")

    async def _http_stream_events(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any] | None,
        response_granularity: ResponseGranularity,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream events via HTTP with SSE."""
        if self._config is None or not self._config.url:
            raise ValueError("RemoteGraph requires a configured URL (config.url)")
        payload = {
            "input": _payload_input(input_data),
            "config": config or {},
            "response_granularity": "low",
        }
        url = f"{self._url}/stream-events"
        headers = {**self._get_auth_header(), "Accept": "text/event-stream"}

        session = self._ensure_session()
        async with session.post(url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.content:
                line = line.decode("utf-8").strip()
                if line.startswith("data: "):
                    try:
                        yield json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue

    async def health_check(self) -> dict[str, Any]:
        """Check the remote server liveness endpoint."""
        if self._config is None or not self._config.url:
            raise ValueError("RemoteGraph requires a configured URL (config.url)")
        session = self._ensure_session()
        async with session.get(f"{self._url}/health") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def ready_check(self) -> dict[str, Any]:
        """Check the remote server readiness endpoint."""
        if self._config is None or not self._config.url:
            raise ValueError("RemoteGraph requires a configured URL (config.url)")
        session = self._ensure_session()
        async with session.get(f"{self._url}/ready") as resp:
            resp.raise_for_status()
            return await resp.json()


class GraphServer:
    """Production-grade aiohttp HTTP server hosting a compiled graph.

    Features:
    - TLS/SSL support
    - API key authentication
    - Rate limiting
    - CORS support
    - Request/response logging
    - Health checks
    - Graceful shutdown
    - Request/response size limits
    - Rate limiting
    """

    def __init__(
        self,
        graph: Any,
        config: GraphServerConfig | None = None,
        # Legacy params for backward compat
        graph_legacy: Any | None = None,
        host: str = "127.0.0.1",
        port: int = 8080,
        timeout: float = 60.0,
    ):
        if config is None:
            self.graph = graph_legacy or graph
            self._config = GraphServerConfig(
                host=host,
                port=port,
                timeout=timeout,
            )
        else:
            self.graph = graph
            self._config = config

        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._rate_limiter: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    def _create_app(self) -> web.Application:
        """Create the aiohttp web application."""
        app = web.Application(
            client_max_size=self._config.max_request_size,
        )
        app["graph"] = self.graph
        app["config"] = self._config
        app["rate_limiter"] = self._rate_limiter
        app["lock"] = self._lock

        # Middleware
        if self._config.enable_cors:
            import aiohttp_cors

            cors = aiohttp_cors.setup(
                app,
                defaults={
                    origin: aiohttp_cors.ResourceOptions(
                        allow_credentials=True,
                        expose_headers="*",
                        allow_headers="*",
                        allow_methods="*",
                    )
                    for origin in self._config.cors_origins
                },
            )
            app["cors"] = cors

        app.middlewares.append(self._auth_middleware)
        app.middlewares.append(self._rate_limit_middleware)
        app.middlewares.append(self._request_logging_middleware)

        # Routes
        app.router.add_post("/invoke", self._handle_invoke)
        app.router.add_post("/stream-events", self._handle_stream_events)
        app.router.add_get("/health", self._handle_health)
        app.router.add_get("/ready", self._handle_ready)

        if self._config.enable_cors:
            for route in list(app.router.routes()):
                cors.add(route)

        return app

    @web.middleware
    async def _auth_middleware(self, request: web.Request, handler: Callable):
        """API key authentication middleware."""
        config = request.app["config"]
        if not config.api_keys:
            return await handler(request)

        # Skip auth for health checks
        if request.path in ("/health", "/ready"):
            return await handler(request)

        api_key = request.headers.get("Authorization", "").replace("Bearer ", "")
        if api_key not in config.api_keys:
            return web.json_response({"error": "unauthorized"}, status=401)
        return await handler(request)

    @web.middleware
    async def _rate_limit_middleware(self, request: web.Request, handler: Callable):
        """Rate limiting middleware."""
        config = request.app["config"]
        if config.rate_limit <= 0:
            return await handler(request)

        client_ip = request.remote or "unknown"
        now = time.time()
        minute_ago = now - 60

        async with request.app["lock"]:
            requests = request.app["rate_limiter"].get(client_ip, [])
            requests = [ts for ts in requests if ts > minute_ago]
            if len(requests) >= config.rate_limit:
                return web.json_response(
                    {"error": "rate limit exceeded"},
                    status=429,
                    headers={"Retry-After": "60"},
                )
            requests.append(now)
            request.app["rate_limiter"][client_ip] = requests

        return await handler(request)

    @web.middleware
    async def _request_logging_middleware(self, request: web.Request, handler: Callable):
        """Request/response logging middleware."""
        start = time.time()
        try:
            response = await handler(request)
            duration = time.time() - start
            request.app.logger.info(
                f"{request.method} {request.path} -> {response.status} ({duration:.3f}s)"
            )
            return response
        except Exception as e:
            duration = time.time() - start
            request.app.logger.error(
                f"{request.method} {request.path} -> ERROR ({duration:.3f}s): {e}"
            )
            raise

    async def _handle_invoke(self, request: web.Request) -> web.Response:
        """Handle /invoke endpoint."""
        graph = request.app["graph"]
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid json"}, status=400)

        input_data = payload.get("input", {})
        config = payload.get("config", {})
        granularity = _normalize_granularity(payload.get("response_granularity", "low"))

        try:
            result = await graph.ainvoke(
                _restore_input(input_data),
                config,
                granularity,
            )
            return web.json_response({"result": _payload_input(result)})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

    async def _handle_stream_events(self, request: web.Request) -> web.Response:
        """Handle /stream-events endpoint with SSE."""
        graph = request.app["graph"]
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid json"}, status=400)

        # Check if graph supports stream_events
        if not hasattr(graph, "astream_events"):
            return web.json_response({"error": "stream_events not supported"}, status=400)

        async def event_stream():
            try:
                async for event in graph.astream_events(
                    _restore_input(payload.get("input", {})),
                    payload.get("config", {}),
                    _normalize_granularity(payload.get("response_granularity", "low")),
                ):
                    yield f"data: {json.dumps(event, default=str)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
        await response.prepare(request)

        try:
            async for chunk in event_stream():
                await response.write(chunk.encode("utf-8"))
        except Exception:  # noqa: S110
            pass
        finally:
            await response.write_eof()

        return response

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        graph = request.app["graph"]
        return web.json_response(
            {
                "status": "ok",
                "nodes": list(graph.nodes.keys()) if hasattr(graph, "nodes") else [],
                "timestamp": datetime.now().isoformat(),
            }
        )

    async def _handle_ready(self, request: web.Request) -> web.Response:
        """Readiness check endpoint."""
        return web.json_response({"status": "ready"})

    async def start(self) -> GraphServer:
        """Start the server."""
        self._app = self._create_app()
        self._runner = web.AppRunner(self._app, shutdown_timeout=self._config.keepalive_timeout)
        await self._runner.setup()

        ssl_context = None
        if self._config.enable_tls:
            ssl_context = _create_ssl_context(
                tls_verify=True,
                cert_file=self._config.ssl_cert,
                key_file=self._config.ssl_key,
            )

        self._site = web.TCPSite(
            self._runner,
            host=self._config.host,
            port=self._config.port,
            ssl_context=ssl_context,
        )
        await self._site.start()
        return self

    async def stop(self) -> None:
        """Stop the server gracefully."""
        if self._site:
            await self._site.stop()
            self._site = None
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self._app = None

    async def __aenter__(self) -> GraphServer:
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.stop()


def _normalize_granularity(value: Any) -> ResponseGranularity:
    """Coerce a string/enum response granularity to the ResponseGranularity enum."""
    if isinstance(value, ResponseGranularity):
        return value
    try:
        return ResponseGranularity(str(value).upper())
    except ValueError:
        return ResponseGranularity.LOW


def _create_ssl_context(
    tls_verify: bool, cert_file: str | None = None, key_file: str | None = None
) -> ssl.SSLContext | None:
    """Create SSL context for TLS connections."""
    if not cert_file or not key_file:
        return None
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(cert_file, key_file)
    if not tls_verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


__all__ = [
    "GraphServer",
    "GraphServerConfig",
    "RemoteGraph",
    "RemoteGraphConfig",
]
