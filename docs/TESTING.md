# Testing — Unit Tests Without Live LLM

> **Test your graphs without calling live LLMs.**

---

## Overview

| Tool | Purpose |
|------|---------|
| `QuickTest` | Single-turn assertion |
| `TestAgent` | Full graph simulation with mocks |
| `MockMCPClient` | Mock MCP server |
| `MockToolRegistry` | Mock tool responses |
| `TestContext` | Isolated test runs |

---

## 1. QuickTest — Single Turn

```python
from alcyoneus.qa.testing import QuickTest

# Simple assertion
test = QuickTest.single_turn("Expected response contains 'hello'")

result = await test.run(compiled, input_data={
    "messages": [{"role": "user", "content": "Hi"}]
})

assert result.passed
assert "hello" in result.actual_output.lower()
```

### Multi-turn Test

```python
test = QuickTest.multi_turn([
    ("user", "Hello", "assistant", "Hello! How can I help?"),
    ("user", "What's 2+2?", "assistant", "4"),
])

result = await test.run(compiled)
assert result.passed
```

---

## 2. TestAgent — Full Simulation

```python
from alcyoneus.qa.testing import TestAgent, MockMCPClient, MockToolRegistry

# Mock LLM responses
mock_llm = MockLLM(responses=[
    "I'll help you calculate that.",
    "The answer is 4.",
])

# Mock tool responses
mock_tools = MockToolRegistry({
    "safe_calculator": lambda expr: {"result": "4"},
    "fetch_url": lambda url: {"content": "Mock content", "status": 200},
})

test_agent = TestAgent(
    compiled=compiled,
    mock_llm=mock_llm,
    mock_tools=mock_tools,
)

# Run test
result = await test_agent.run({
    "messages": [{"role": "user", "content": "What's 2+2?"}]
})

assert result.state.messages[-1].content == "4"
assert result.passed
```

### MockLLM

```python
from alcyoneus.qa.testing import MockLLM

# Sequential responses
mock_llm = MockLLM(responses=["Response 1", "Response 2", "Response 3"])

# Or with tool calls
mock_llm = MockLLM(responses=[
    {"tool_calls": [{"name": "calc", "arguments": {"expr": "2+2"}}]},
    "The answer is 4.",
])
```

### MockToolRegistry

```python
from alcyoneus.qa.testing import MockToolRegistry

mock_tools = MockToolRegistry({
    "safe_calculator": lambda expr: {"result": "42"},
    "fetch_url": lambda url: {"content": "Mock page", "status": 200},
    "search": lambda q: {"results": [{"title": "Test", "url": "http://test.com"}]},
    # Async tools
    "async_tool": async_func,
})
```

---

## 3. MockMCPClient

```python
from alcyoneus.qa.testing import MockMCPClient

mock_mcp = MockMCPClient()

# Add mock tools
mock_mcp.add_tool("search", lambda q: {"results": [{"title": "Test", "url": "http://test.com"}]})
mock_mcp.add_tool("calculate", lambda expr: {"result": "42"})

# Use in graph
from alcyoneus.core import ToolNode
tool_node = ToolNode(tools=[], client=mock_mcp)
```

---

## 4. TestContext — Isolated Runs

```python
from alcyoneus.qa.testing import TestContext

async with TestContext() as ctx:
    # Run graph in isolated context
    result = await ctx.run(graph, input_data={"user_id": "test"})
    
    # Access events
    assert ctx.events[-1]["type"] == "graph_end"
    
    # Access state
    assert ctx.final_state.total == 100
    
    # Access tool calls
    assert len(ctx.tool_calls) == 2
```

---

## 5. Full Test Example

```python
import pytest
from alcyoneus.qa.testing import QuickTest, TestAgent, MockLLM, MockToolRegistry
from myapp.graphs import order_graph

@pytest.mark.asyncio
async def test_order_flow():
    """Test complete order processing flow."""
    
    # Setup mocks
    mock_llm = MockLLM(responses=[
        "I'll check inventory.",
        "Inventory confirmed. Charging payment.",
        "Payment successful. Order confirmed.",
    ])
    
    mock_tools = MockToolRegistry({
        "check_inventory": lambda order_id: {"available": True, "items": ["item1"]},
        "charge_payment": lambda amount, customer_id: {"payment_id": "pay_123", "status": "succeeded"},
        "send_confirmation": lambda email, order_id: {"sent": True},
    })
    
    # Build test agent
    test_agent = TestAgent(
        compiled=order_graph.compile(),
        mock_llm=mock_llm,
        mock_tools=mock_tools,
    )
    
    # Run test
    result = await test_agent.run({
        "user_id": "user_123",
        "order_id": "ord_456",
        "items": [{"sku": "ABC", "qty": 2, "price": 29.99}],
    })
    
    # Assertions
    assert result.passed
    assert result.state.confirmed is True
    assert result.state.payment_intent_id == "pay_123"
    assert len(result.tool_calls) == 3

# Run with pytest
# pytest tests/test_order_flow.py -v
```

---

## 5. Assertions Helpers

```python
from alcyoneus.qa.testing import assert_state_equals, assert_tool_called

# Assert final state
assert_state_equals(result.state, {"confirmed": True, "total": 59.98})

# Assert tool was called
assert_tool_called(result, "charge_payment", {"amount": 59.98})

# Assert tool call count
assert len([c for c in result.tool_calls if c["name"] == "search"]) == 2

# Assert message content
assert "confirmed" in result.state.messages[-1].content.lower()
```

---

## 6. Running Tests

```bash
# With pytest
pytest tests/ -v -k "test_order"

# With coverage
pytest tests/ --cov=myapp --cov-report=html

# Parallel
pytest tests/ -n auto

# Only integration tests
pytest tests/integration/ -v
```

---

## 7. Fixtures (conftest.py)

```python
# tests/conftest.py
import pytest
from alcyoneus.qa.testing import TestAgent, MockLLM, MockToolRegistry

@pytest.fixture
def mock_llm():
    return MockLLM(responses=["Mock response"])

@pytest.fixture
def mock_tools():
    return MockToolRegistry({
        "safe_calculator": lambda expr: {"result": "42"},
        "fetch_url": lambda url: {"content": "Mock", "status": 200},
    })

@pytest.fixture
def test_agent(compiled_graph, mock_llm, mock_tools):
    return TestAgent(
        compiled=compiled_graph,
        mock_llm=mock_llm,
        mock_tools=mock_tools,
    )

# Usage in tests
async def test_something(test_agent):
    result = await test_agent.run({"input": "test"})
    assert result.passed
```

---

## 8. Storage Conformance Testing

> **Verify identical behavior across all checkpointer backends.**

The conformance matrix (`tests/storage/test_conformance_matrix.py`) uses `pytest.mark.parametrize` to run the same tests across every checkpointer:

```python
import pytest
from alcyoneus.storage.checkpointer import (
    InMemoryCheckpointer,
    SqliteCheckpointer,
    PgCheckpointer,
)

@pytest.fixture(params=["in_memory_cp", "sqlite_cp", "pg_cp"])
def checkpointer(request):
    if request.param == "in_memory_cp":
        return InMemoryCheckpointer()
    elif request.param == "sqlite_cp":
        return SqliteCheckpointer(":memory:")
    elif request.param == "pg_cp":
        # Use async pool mock for CI (no live Postgres required)
        return make_mock_pg_checkpointer()

class TestStorageConformanceMatrix:
    async def test_put_and_get_state(self, checkpointer):
        """State roundtrip must be identical across all backends."""
        await checkpointer.aput("thread-1", {"counter": 42})
        state = await checkpointer.aget("thread-1")
        assert state["counter"] == 42

    async def test_thread_isolation(self, checkpointer):
        """Separate threads must maintain isolated state."""
        await checkpointer.aput("thread-a", {"value": "A"})
        await checkpointer.aput("thread-b", {"value": "B"})
        assert (await checkpointer.aget("thread-a"))["value"] == "A"
        assert (await checkpointer.aget("thread-b"))["value"] == "B"
```

### Conformance Test Matrix

| Test | What It Verifies |
|------|-----------------|
| `test_put_and_get_state` | Roundtrip save/load of complex Pydantic states |
| `test_thread_isolation` | Separate threads maintain isolated namespaces |
| `test_state_update_and_overwrite` | Deterministic atomic state updates |
| `test_thread_deletion_and_cleanup` | Consistent `aclean_thread` / `adelete_thread` |
| `test_messages_history_persistence` | Ordered message serialization and retrieval |

---

## 9. Sandbox Mock Isolation

> **Test Docker and Kubernetes sandboxes without live container runtimes.**

Hermetic mock isolation suites in `tests/sandbox/test_sandboxes.py` allow full CI execution:

```python
from unittest.mock import AsyncMock, MagicMock, patch

class TestDockerSandboxIsolation:
    async def test_docker_sdk_lifecycle(self):
        """Full container start → exec → stop lifecycle with mocked Docker SDK."""
        with patch("docker.from_env") as mock_docker:
            mock_container = MagicMock()
            mock_docker.return_value.containers.run.return_value = mock_container
            mock_container.exec_run.return_value = (0, b"hello world")

            sandbox = DockerSandbox(image="python:3.12-slim")
            await sandbox.astart()
            result = await sandbox.aexec("echo hello world")
            assert result.exit_code == 0
            await sandbox.astop()

class TestK8sSandboxIsolation:
    async def test_k8s_sandbox_lifecycle(self):
        """Pod creation → exec → deletion with mocked Kubernetes API."""
        with patch("kubernetes.client.CoreV1Api") as mock_api:
            # ... mocked V1Pod lifecycle
            sandbox = K8sSandbox(namespace="test")
            await sandbox.astart()
            result = await sandbox.aexec("python -c 'print(1)'")
            assert result.exit_code == 0
```

### What's Tested

| Suite | Tests | Coverage |
|-------|-------|----------|
| **DockerSandbox** | SDK lifecycle, CLI fallback, TAR file transfer, timeout handling, unstarted error | 5 tests |
| **K8sSandbox** | Pod lifecycle, exec streaming, base64 file I/O, failure phases, uninitialized errors | 3 tests |

---

## 10. Graph Lifecycle & Human-in-the-Loop Testing

> **Test complex graph execution patterns including cycles, interrupts, and streaming.**

```python
class TestGraphLifecycle:
    async def test_complex_cyclic_graph_with_conditional_loop(self):
        """Conditional loop transitions terminate deterministically on cycle limit."""
        graph = StateGraph(MyState)
        graph.add_node("process", process_node)
        graph.add_conditional_edges("process", should_continue)
        compiled = graph.compile()
        result = await compiled.ainvoke({"iteration": 0})
        assert result["iteration"] <= MAX_CYCLES

    async def test_interrupt_before_and_checkpoint_resumption(self):
        """HITL: interrupt_before pauses execution, aupdate_state resumes it."""
        compiled = graph.compile(
            checkpointer=InMemoryCheckpointer(),
            interrupt_before=["human_review"],
        )
        # First invocation pauses at human_review
        result = await compiled.ainvoke(input_data, config={"thread_id": "t1"})
        assert result["__interrupt__"]

        # Simulate human approval, then resume
        await compiled.aupdate_state(
            config={"thread_id": "t1"},
            values={"approved": True},
        )
        final = await compiled.ainvoke(None, config={"thread_id": "t1"})
        assert final["approved"] is True
```

### Test Coverage

| Test | Pattern |
|------|---------|
| `test_complex_cyclic_graph` | Conditional loop with deterministic termination |
| `test_dynamic_prompt_interpolation` | State variable injection into system prompts |
| `test_interrupt_before_and_checkpoint_resumption` | HITL pause, `aupdate_state`, and resume |
| `test_stream_transformer_pipeline` | Streaming event transformation with `ToolCallTransformer` |

---

## 11. Coverage Policy

The project enforces a minimum coverage threshold via `pyproject.toml`:

```toml
[tool.coverage.report]
fail_under = 90
exclude_lines = [
    "pragma: no cover",
]
```

### Running Coverage

```bash
# Generate coverage report
pytest tests/ --cov=alcyoneus --cov-report=html --cov-report=term

# Fail CI if coverage drops below 90%
pytest tests/ --cov=alcyoneus --cov-fail-under=90
```

---

## 12. Zero-Skip Policy

> **All tests must run unconditionally — no `pytest.skip()` or `@pytest.mark.skip` allowed.**

Optional dependencies (`Pillow`, `piexif`, `redis`, `aiokafka`, `aio-pika`) must be installed in the test environment. Tests must never conditionally skip based on import availability.

**Enforcement:**

```bash
# Verify zero skips remain in codebase
grep -rn "pytest.skip\|@pytest.mark.skip" tests/
# Expected output: (empty — zero matches)

# Verify test run has zero skips
pytest tests/ -q
# Expected: XXXX passed, 0 skipped, 0 failed
```

---

## 13. Running the Full Suite

```bash
# Full suite
pytest tests/ -v

# Pillar 3 suites only
pytest tests/storage/test_conformance_matrix.py \
       tests/sandbox/test_sandboxes.py \
       tests/graph/test_graph_lifecycle.py -v

# With coverage
pytest tests/ --cov=alcyoneus --cov-report=html

# Parallel execution
pytest tests/ -n auto

# Only integration tests
pytest tests/integration/ -v
```