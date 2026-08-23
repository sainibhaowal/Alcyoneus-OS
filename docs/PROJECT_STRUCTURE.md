# Project Structure — Recommended Layout

> **Organize your Alcyoneus project for maintainability and scale.**

---

## Recommended Layout

```
my_project/
├── config/
│   ├── __init__.py
│   ├── settings.py              # Pydantic settings (env-driven)
│   └── prompts/                 # System prompts as .txt files
│       ├── agent_system.txt
│       ├── rag_prompt.txt
│       └── supervisor_prompt.txt
├── state/
│   ├── __init__.py
│   ├── base.py                  # BaseAgentState
│   ├── order_state.py           # OrderState
│   ├── chat_state.py            # ChatState
│   └── enums.py                 # Shared enums
├── nodes/
│   ├── __init__.py
│   ├── payment.py               # Payment nodes
│   ├── inventory.py             # Inventory nodes
│   ├── notification.py          # Notification nodes
│   └── validation.py            # Validation nodes
├── graphs/
│   ├── __init__.py
│   ├── order_flow.py            # Order processing graph
│   ├── chat_flow.py             # Chat graph
│   └── admin_flow.py            # Admin graph
├── tools/
│   ├── __init__.py
│   ├── payment_tools.py         # @tool functions
│   ├── inventory_tools.py
│   ├── notification_tools.py
│   └── custom_tools.py          # Other @tool functions
├── agents/
│   ├── __init__.py
│   ├── prebuilt_config.py       # ReactAgent, RAGAgent configs
│   └── custom_agents.py         # Custom Agent subclasses
├── eval/
│   ├── __init__.py
│   ├── cases.yaml               # EvalCase definitions
│   ├── criteria.py              # Custom criteria
│   └── reporters.py             # Custom reporters
├── tests/
│   ├── __init__.py
│   ├── test_graph.py            # TestAgent / QuickTest
│   ├── test_nodes.py            # Unit test nodes
│   ├── test_tools.py            # Unit test tools
│   └── test_eval.py             # Evaluation tests
├── deployment/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── helm/
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── templates/
│   └── k8s/
├── skills/
│   ├── sql_analysis.yaml
│   ├── data_export.yaml
│   └── report_generation.yaml
├── .env.example
├── pyproject.toml
├── README.md
└── main.py                      # Entry point
```

---

## Directory Breakdown

### `config/` — Configuration

```
config/
├── settings.py          # Pydantic Settings (env vars)
└── prompts/             # System prompts as text files
```

```python
# config/settings.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    OPENAI_API_KEY: str
    GOOGLE_API_KEY: str
    POSTGRES_CONN_STR: str
    REDIS_URL: str
    QDRANT_URL: str
    QDRANT_API_KEY: str
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
```

### `state/` — State Definitions

```
state/
├── __init__.py          # Exports all states
├── base.py              # BaseAgentState (optional)
├── order_state.py       # OrderState
├── chat_state.py        # ChatState
└── enums.py             # Shared enums
```

```python
# state/order_state.py
from alcyoneus.core import AgentState
from typing import Optional, List
from pydantic import BaseModel, Field

class OrderItem(BaseModel):
    sku: str
    qty: int
    price: float

class OrderState(AgentState):
    user_id: str
    order_id: str
    items: List[OrderItem] = []
    total: float = 0.0
    shipping_address: Optional[str] = None
    confirmed: bool = False
```

### `nodes/` — Business Logic

```
nodes/
├── __init__.py          # Exports all nodes
├── payment.py           # Payment processing
├── inventory.py         # Inventory checks
├── notification.py      # Email/push notifications
└── validation.py        # Input validation
```

```python
# nodes/payment.py
from alcyoneus.core import AgentState
from myapp.state import OrderState

async def charge_payment(state: OrderState) -> OrderState:
    intent = await stripe.create_intent(state.total, state.user_id)
    state.payment_intent_id = intent.id
    return state

async def refund_payment(state: OrderState) -> OrderState:
    await stripe.refund(state.payment_intent_id)
    return state
```

### `graphs/` — Graph Construction

```
graphs/
├── __init__.py
├── order_flow.py        # Order processing graph
├── chat_flow.py         # Chat graph
└── admin_flow.py        # Admin graph
```

```python
# graphs/order_flow.py
from alcyoneus.core import StateGraph, START, END
from myapp.state import OrderState
from myapp.nodes import calculate_total, charge_payment, fulfill_order

def build_order_graph() -> StateGraph:
    graph = StateGraph(OrderState)
    graph.add_node("calculate", calculate_total)
    graph.add_node("charge", charge_payment)
    graph.add_node("fulfill", fulfill_order)
    
    graph.add_edge(START, "calculate")
    graph.add_edge("calculate", "charge")
    graph.add_conditional_edges("charge", route_payment)
    graph.add_edge("fulfill", END)
    
    return graph
```

### `tools/` — Custom Tools

```
tools/
├── __init__.py
├── payment_tools.py
├── inventory_tools.py
└── custom_tools.py
```

```python
# tools/payment_tools.py
from alcyoneus.utils import tool

@tool
async def create_stripe_intent(amount: int, customer_id: str) -> dict:
    return await stripe.create_intent(amount, customer_id)
```

### `agents/` — Agent Configurations

```
agents/
├── __init__.py
├── prebuilt_config.py   # ReactAgent, RAGAgent configs
└── custom_agents.py     # Custom Agent subclasses
```

```python
# agents/prebuilt_config.py
from alcyoneus.prebuilt.agent import ReactAgent, RAGAgent
from alcyoneus.storage.store import QdrantStore

def get_research_agent():
    return ReactAgent(
        model="google/gemini-2.5-flash",
        tools=[fetch_url, google_web_search],
        system_prompt="You are a research assistant.",
    )

def get_rag_agent():
    store = QdrantStore(url="...", collection="docs")
    return RAGAgent(model="...", store=store, top_k=5)
```

### `eval/` — Evaluation

```
eval/
├── __init__.py
├── cases.yaml           # EvalCase definitions
├── criteria.py          # Custom criteria
└── reporters.py         # Custom reporters
```

```yaml
# eval/cases.yaml
cases:
  - name: order_happy_path
    input:
      user_id: "user_123"
      items: [{"sku": "ABC", "qty": 1, "price": 29.99}]
    expected_output:
      confirmed: true
    criteria:
      - factual_accuracy
      - trajectory_match
```

### `tests/` — Testing

```
tests/
├── __init__.py
├── test_graph.py        # TestAgent / QuickTest
├── test_nodes.py        # Unit test nodes
├── test_tools.py        # Unit test tools
└── test_eval.py         # Evaluation tests
```

```python
# tests/test_graph.py
import pytest
from alcyoneus.qa.testing import TestAgent, MockLLM, MockToolRegistry
from myapp.graphs import order_flow

@pytest.fixture
def test_agent():
    return TestAgent(
        compiled=order_flow.build_order_graph().compile(),
        mock_llm=MockLLM(responses=["...", "..."]),
        mock_tools=MockToolRegistry({...}),
    )

async def test_order_flow(test_agent):
    result = await test_agent.run({"user_id": "test", "items": [...]})
    assert result.state.confirmed
```

### `deployment/` — Deployment

```
deployment/
├── Dockerfile
├── docker-compose.yml
├── helm/
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
└── k8s/
```

### `skills/` — Dynamic Skills

```
skills/
├── sql_analysis.yaml
├── data_export.yaml
└── report_generation.yaml
```

---

## Minimal Structure (Start Here)

```
my_project/
├── config/
│   └── settings.py
├── state/
│   └── my_state.py
├── nodes/
│   └── my_nodes.py
├── graphs/
│   └── my_graph.py
├── tools/
│   └── my_tools.py
├── tests/
│   └── test_graph.py
├── .env.example
├── pyproject.toml
└── main.py
```

---

## Import Conventions

```python
# In any file, use absolute imports from project root
from myapp.state import OrderState
from myapp.nodes.payment import charge_payment
from myapp.graphs.order_flow import build_order_graph
from myapp.tools.payment_tools import create_stripe_intent
from myapp.agents import get_research_agent
```

---

## Scaling Guidelines

| Size | Structure |
|------|-----------|
| Small (< 5 files) | Flat structure |
| Medium | Group by domain (orders/, chat/, admin/) |
| Large | Separate packages per domain |

---

## .gitignore Essentials

```gitignore
# Python
__pycache__/
*.py[cod]
*.pyc
.pytest_cache/
.mypy_cache/
.coverage
htmlcov/

# Virtual env
.venv/
venv/
.env

# IDE
.idea/
.vscode/
*.swp

# OS
.DS_Store
Thumbs.db

# Build
dist/
build/
*.egg-info/

# Logs
*.log
logs/

# Local
check code.md
```