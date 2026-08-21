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