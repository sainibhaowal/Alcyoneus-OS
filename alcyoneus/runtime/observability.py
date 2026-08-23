"""Auto-instrumentation, Prometheus metrics, structured logging, trace context propagation."""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import wraps
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.metrics import (
    CallbackOptions,
    Observation,
    set_meter_provider,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, StatusCode
from prometheus_client import Counter, Gauge, Histogram


logger = logging.getLogger("alcyoneus.observability")

# Context variables for trace propagation
trace_context: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "trace_context", default=None
)
current_span: contextvars.ContextVar[Any] = contextvars.ContextVar("current_span", default=None)

# Prometheus metrics
REQUEST_COUNT = Counter(
    "alcyoneus_requests_total", "Total number of requests", ["method", "endpoint", "status"]
)

REQUEST_LATENCY = Histogram(
    "alcyoneus_request_duration_seconds", "Request latency in seconds", ["method", "endpoint"]
)

ACTIVE_REQUESTS = Gauge("alcyoneus_active_requests", "Number of active requests")

GRAPH_EXECUTIONS = Counter(
    "alcyoneus_graph_executions_total", "Total graph executions", ["graph_name", "status"]
)

GRAPH_DURATION = Histogram(
    "alcyoneus_graph_duration_seconds", "Graph execution duration", ["graph_name"]
)

NODE_EXECUTIONS = Counter(
    "alcyoneus_node_executions_total",
    "Total node executions",
    ["graph_name", "node_name", "status"],
)

NODE_DURATION = Histogram(
    "alcyoneus_node_duration_seconds", "Node execution duration", ["graph_name", "node_name"]
)

LLM_CALLS = Counter("alcyoneus_llm_calls_total", "Total LLM calls", ["model", "provider", "status"])

LLM_TOKENS = Counter(
    "alcyoneus_llm_tokens_total",
    "Total LLM tokens",
    ["model", "type"],
)

LLM_LATENCY = Histogram("alcyoneus_llm_latency_seconds", "LLM call latency", ["model", "provider"])

TOOL_CALLS = Counter("alcyoneus_tool_calls_total", "Total tool calls", ["tool_name", "status"])

TOOL_LATENCY = Histogram("alcyoneus_tool_latency_seconds", "Tool call latency", ["tool_name"])

ACTIVE_SESSIONS = Gauge("alcyoneus_active_sessions", "Number of active sessions")

CHECKPOINT_SIZE = Histogram("alcyoneus_checkpoint_size_bytes", "Checkpoint size in bytes")

STATE_SIZE = Gauge("alcyoneus_state_size", "Current state size")

ERROR_COUNT = Counter("alcyoneus_errors_total", "Total errors", ["component", "error_type"])


@dataclass
class InstrumentationConfig:
    """Configuration for auto-instrumentation."""

    enable_tracing: bool = True
    enable_metrics: bool = True
    enable_logging: bool = True
    service_name: str = "alcyoneus"
    otlp_endpoint: str | None = None
    prometheus_port: int | None = 9090
    push_gateway: str | None = None
    log_level: int = logging.INFO
    sample_rate: float = 1.0


class AutoInstrumentor:
    """Auto-instrumentation for Alcyoneus components."""

    def __init__(self, config: InstrumentationConfig | None = None):
        self.config = config or InstrumentationConfig()
        self._tracer_provider: TracerProvider | None = None
        self._meter_provider: MeterProvider | None = None
        self._initialized = False

    def initialize(self) -> None:
        """Initialize OpenTelemetry and Prometheus."""
        if self._initialized:
            return

        # Setup tracing
        if self.config.enable_tracing:
            resource = Resource.create({"service.name": self.config.service_name})
            self._tracer_provider = TracerProvider(resource=resource)

            if self.config.otlp_endpoint:
                try:
                    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                        OTLPSpanExporter,
                    )

                    exporter = OTLPSpanExporter(endpoint=self.config.otlp_endpoint)
                    self._tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
                except ImportError:
                    logger.warning("OTLP exporter not available")

            trace.set_tracer_provider(self._tracer_provider)

        # Setup metrics
        if self.config.enable_metrics:
            readers = []
            if self.config.prometheus_port:
                readers.append(PrometheusMetricReader())
            self._meter_provider = MeterProvider(
                resource=Resource.create({"service.name": self.config.service_name}),
                metric_readers=readers,
            )
            set_meter_provider(self._meter_provider)

            # Register callbacks for observable metrics
            self._register_metric_callbacks()

        # Setup structured logging
        if self.config.enable_logging:
            self._setup_structured_logging()

        self._initialized = True
        logger.info("Auto-instrumentation initialized")

    def _register_metric_callbacks(self) -> None:
        """Register observable metric callbacks."""

        # Active sessions callback
        def active_sessions_callback(options: CallbackOptions) -> list[Observation]:
            return [Observation(ACTIVE_SESSIONS._value.get(), {})]

        # State size callback
        def state_size_callback(options: CallbackOptions) -> list[Observation]:
            return [Observation(STATE_SIZE._value.get(), {})]

        # Could add more callbacks here

    def _setup_structured_logging(self) -> None:
        """Setup JSON structured logging with trace context."""

        class StructuredFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                log_data = {
                    "timestamp": self.formatTime(record),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno,
                }

                # Add trace context if available
                ctx = trace_context.get()
                if ctx:
                    log_data["trace_id"] = ctx.get("trace_id")
                    log_data["span_id"] = ctx.get("span_id")

                # Add extra fields
                for key, value in record.__dict__.items():
                    if key not in (
                        "name",
                        "msg",
                        "args",
                        "created",
                        "filename",
                        "funcName",
                        "levelname",
                        "levelno",
                        "lineno",
                        "module",
                        "msecs",
                        "message",
                        "name",
                        "pathname",
                        "process",
                        "processName",
                        "relativeCreated",
                        "thread",
                        "threadName",
                        "exc_info",
                        "exc_text",
                        "stack_info",
                    ):
                        log_data[key] = value

                return json.dumps(log_data)

        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        root_logger = logging.getLogger()
        root_logger.handlers = [handler]
        root_logger.setLevel(self.config.log_level)

    def get_tracer(self, name: str = "alcyoneus") -> trace.Tracer:
        """Get a tracer instance."""
        return trace.get_tracer(name)

    def shutdown(self) -> None:
        """Shutdown instrumentation."""
        if self._tracer_provider:
            self._tracer_provider.shutdown()
        if self._meter_provider:
            self._meter_provider.shutdown()


# Decorators for auto-instrumentation
def trace_graph(graph_name: str):
    """Decorator to trace graph execution."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = trace.get_tracer("alcyoneus")
            with tracer.start_as_current_span(
                f"graph.{graph_name}",
                kind=SpanKind.SERVER,
            ) as span:
                span.set_attribute("graph.name", graph_name)
                start = time.time()
                ACTIVE_SESSIONS.inc()
                GRAPH_EXECUTIONS.labels(graph_name=graph_name, status="started").inc()

                try:
                    result = await func(*args, **kwargs)
                    span.set_status(StatusCode.OK)
                    GRAPH_EXECUTIONS.labels(graph_name=graph_name, status="success").inc()
                    return result
                except Exception as e:
                    span.set_status(StatusCode.ERROR, str(e))
                    span.record_exception(e)
                    GRAPH_EXECUTIONS.labels(graph_name=graph_name, status="error").inc()
                    ERROR_COUNT.labels(component="graph", error_type=type(e).__name__).inc()
                    raise
                finally:
                    duration = time.time() - start
                    GRAPH_DURATION.labels(graph_name=graph_name).observe(duration)
                    ACTIVE_SESSIONS.dec()

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = trace.get_tracer("alcyoneus")
            with tracer.start_as_current_span(
                f"graph.{graph_name}",
                kind=SpanKind.SERVER,
            ) as span:
                span.set_attribute("graph.name", graph_name)
                start = time.time()
                ACTIVE_SESSIONS.inc()
                GRAPH_EXECUTIONS.labels(graph_name=graph_name, status="started").inc()

                try:
                    result = func(*args, **kwargs)
                    span.set_status(StatusCode.OK)
                    GRAPH_EXECUTIONS.labels(graph_name=graph_name, status="success").inc()
                    return result
                except Exception as e:
                    span.set_status(StatusCode.ERROR, str(e))
                    span.record_exception(e)
                    GRAPH_EXECUTIONS.labels(graph_name=graph_name, status="error").inc()
                    ERROR_COUNT.labels(component="graph", error_type=type(e).__name__).inc()
                    raise
                finally:
                    duration = time.time() - start
                    GRAPH_DURATION.labels(graph_name=graph_name).observe(duration)
                    ACTIVE_SESSIONS.dec()

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def trace_node(graph_name: str, node_name: str):
    """Decorator to trace node execution."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = trace.get_tracer("alcyoneus")
            with tracer.start_as_current_span(
                f"node.{node_name}",
                kind=SpanKind.INTERNAL,
            ) as span:
                span.set_attribute("graph.name", graph_name)
                span.set_attribute("node.name", node_name)
                start = time.time()
                NODE_EXECUTIONS.labels(
                    graph_name=graph_name, node_name=node_name, status="started"
                ).inc()

                try:
                    result = await func(*args, **kwargs)
                    span.set_status(StatusCode.OK)
                    NODE_EXECUTIONS.labels(
                        graph_name=graph_name, node_name=node_name, status="success"
                    ).inc()
                    return result
                except Exception as e:
                    span.set_status(StatusCode.ERROR, str(e))
                    span.record_exception(e)
                    NODE_EXECUTIONS.labels(
                        graph_name=graph_name, node_name=node_name, status="error"
                    ).inc()
                    ERROR_COUNT.labels(component="node", error_type=type(e).__name__).inc()
                    raise
                finally:
                    duration = time.time() - start
                    NODE_DURATION.labels(graph_name=graph_name, node_name=node_name).observe(
                        duration
                    )

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = trace.get_tracer("alcyoneus")
            with tracer.start_as_current_span(
                f"node.{node_name}",
                kind=SpanKind.INTERNAL,
            ) as span:
                span.set_attribute("graph.name", graph_name)
                span.set_attribute("node.name", node_name)
                start = time.time()
                NODE_EXECUTIONS.labels(
                    graph_name=graph_name, node_name=node_name, status="started"
                ).inc()

                try:
                    result = func(*args, **kwargs)
                    span.set_status(StatusCode.OK)
                    NODE_EXECUTIONS.labels(
                        graph_name=graph_name, node_name=node_name, status="success"
                    ).inc()
                    return result
                except Exception as e:
                    span.set_status(StatusCode.ERROR, str(e))
                    span.record_exception(e)
                    NODE_EXECUTIONS.labels(
                        graph_name=graph_name, node_name=node_name, status="error"
                    ).inc()
                    ERROR_COUNT.labels(component="node", error_type=type(e).__name__).inc()
                    raise
                finally:
                    duration = time.time() - start
                    NODE_DURATION.labels(graph_name=graph_name, node_name=node_name).observe(
                        duration
                    )

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def trace_llm(model: str, provider: str):
    """Decorator to trace LLM calls."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = trace.get_tracer("alcyoneus")
            with tracer.start_as_current_span(
                f"llm.{model}",
                kind=SpanKind.CLIENT,
            ) as span:
                span.set_attribute("llm.model", model)
                span.set_attribute("llm.provider", provider)
                start = time.time()
                LLM_CALLS.labels(model=model, provider=provider, status="started").inc()

                try:
                    result = await func(*args, **kwargs)
                    span.set_status(StatusCode.OK)
                    LLM_CALLS.labels(model=model, provider=provider, status="success").inc()

                    # Extract token usage if available
                    if hasattr(result, "usage"):
                        usage = result.usage
                        if usage.prompt_tokens:
                            LLM_TOKENS.labels(model=model, type="input").inc(usage.prompt_tokens)
                        if usage.completion_tokens:
                            LLM_TOKENS.labels(model=model, type="output").inc(
                                usage.completion_tokens
                            )

                    return result
                except Exception as e:
                    span.set_status(StatusCode.ERROR, str(e))
                    span.record_exception(e)
                    LLM_CALLS.labels(model=model, provider=provider, status="error").inc()
                    ERROR_COUNT.labels(component="llm", error_type=type(e).__name__).inc()
                    raise
                finally:
                    duration = time.time() - start
                    LLM_LATENCY.labels(model=model, provider=provider).observe(duration)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = trace.get_tracer("alcyoneus")
            with tracer.start_as_current_span(
                f"llm.{model}",
                kind=SpanKind.CLIENT,
            ) as span:
                span.set_attribute("llm.model", model)
                span.set_attribute("llm.provider", provider)
                start = time.time()
                LLM_CALLS.labels(model=model, provider=provider, status="started").inc()

                try:
                    result = func(*args, **kwargs)
                    span.set_status(StatusCode.OK)
                    LLM_CALLS.labels(model=model, provider=provider, status="success").inc()
                    return result
                except Exception as e:
                    span.set_status(StatusCode.ERROR, str(e))
                    span.record_exception(e)
                    LLM_CALLS.labels(model=model, provider=provider, status="error").inc()
                    ERROR_COUNT.labels(component="llm", error_type=type(e).__name__).inc()
                    raise
                finally:
                    duration = time.time() - start
                    LLM_LATENCY.labels(model=model, provider=provider).observe(duration)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def trace_tool(tool_name: str):
    """Decorator to trace tool calls."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = trace.get_tracer("alcyoneus")
            with tracer.start_as_current_span(
                f"tool.{tool_name}",
                kind=SpanKind.CLIENT,
            ) as span:
                span.set_attribute("tool.name", tool_name)
                start = time.time()
                TOOL_CALLS.labels(tool_name=tool_name, status="started").inc()

                try:
                    result = await func(*args, **kwargs)
                    span.set_status(StatusCode.OK)
                    TOOL_CALLS.labels(tool_name=tool_name, status="success").inc()
                    return result
                except Exception as e:
                    span.set_status(StatusCode.ERROR, str(e))
                    span.record_exception(e)
                    TOOL_CALLS.labels(tool_name=tool_name, status="error").inc()
                    ERROR_COUNT.labels(component="tool", error_type=type(e).__name__).inc()
                    raise
                finally:
                    duration = time.time() - start
                    TOOL_LATENCY.labels(tool_name=tool_name).observe(duration)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = trace.get_tracer("alcyoneus")
            with tracer.start_as_current_span(
                f"tool.{tool_name}",
                kind=SpanKind.CLIENT,
            ) as span:
                span.set_attribute("tool.name", tool_name)
                start = time.time()
                TOOL_CALLS.labels(tool_name=tool_name, status="started").inc()

                try:
                    result = func(*args, **kwargs)
                    span.set_status(StatusCode.OK)
                    TOOL_CALLS.labels(tool_name=tool_name, status="success").inc()
                    return result
                except Exception as e:
                    span.set_status(StatusCode.ERROR, str(e))
                    span.record_exception(e)
                    TOOL_CALLS.labels(tool_name=tool_name, status="error").inc()
                    ERROR_COUNT.labels(component="tool", error_type=type(e).__name__).inc()
                    raise
                finally:
                    duration = time.time() - start
                    TOOL_LATENCY.labels(tool_name=tool_name).observe(duration)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


@asynccontextmanager
async def trace_context_propagation(headers: dict[str, str] | None = None):
    """Context manager for trace context propagation."""
    ctx = {}
    if headers:
        # Extract trace context from headers
        trace_id = (
            headers.get("traceparent", "").split("-")[1] if "traceparent" in headers else None
        )
        span_id = headers.get("traceparent", "").split("-")[2] if "traceparent" in headers else None
        if trace_id and span_id:
            ctx = {"trace_id": trace_id, "span_id": span_id}

    token = trace_context.set(ctx)
    try:
        yield ctx
    finally:
        trace_context.reset(token)


def inject_trace_context(headers: dict[str, str]) -> dict[str, str]:
    """Inject current trace context into headers for propagation."""
    ctx = trace_context.get() or {}
    if ctx.get("trace_id") and ctx.get("span_id"):
        headers["traceparent"] = f"00-{ctx['trace_id']}-{ctx['span_id']}-01"
    return headers


class StructuredLogger:
    """Structured logger with trace context."""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def _log(self, level: int, msg: str, **kwargs) -> None:
        extra = {"trace_ctx": trace_context.get()}
        extra.update(kwargs)
        self.logger.log(level, msg, extra=extra)

    def debug(self, msg: str, **kwargs) -> None:
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs) -> None:
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs) -> None:
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs) -> None:
        self._log(logging.ERROR, msg, **kwargs)

    def critical(self, msg: str, **kwargs) -> None:
        self._log(logging.CRITICAL, msg, **kwargs)


# Global instrumentor instance
_instrumentor: AutoInstrumentor | None = None


def get_instrumentor() -> AutoInstrumentor:
    """Get or create the global instrumentor."""
    global _instrumentor
    if _instrumentor is None:
        _instrumentor = AutoInstrumentor()
    return _instrumentor


def init_observability(config: InstrumentationConfig | None = None) -> AutoInstrumentor:
    """Initialize global observability."""
    global _instrumentor
    _instrumentor = AutoInstrumentor(config)
    _instrumentor.initialize()
    return _instrumentor


__all__ = [
    "InstrumentationConfig",
    "AutoInstrumentor",
    "trace_graph",
    "trace_node",
    "trace_llm",
    "trace_tool",
    "trace_context_propagation",
    "inject_trace_context",
    "StructuredLogger",
    "get_instrumentor",
    "init_observability",
    # Prometheus metrics
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
    "ACTIVE_REQUESTS",
    "GRAPH_EXECUTIONS",
    "GRAPH_DURATION",
    "NODE_EXECUTIONS",
    "NODE_DURATION",
    "LLM_CALLS",
    "LLM_TOKENS",
    "LLM_LATENCY",
    "TOOL_CALLS",
    "TOOL_LATENCY",
    "ACTIVE_SESSIONS",
    "CHECKPOINT_SIZE",
    "STATE_SIZE",
    "ERROR_COUNT",
]
