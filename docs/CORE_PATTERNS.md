# Core Patterns — State, Nodes, Graphs

> **How to wire your business logic into Alcyoneus OS.**

---

## 1. Define State (Your Data Schema)

```python
from alcyoneus.core import AgentState
from typing import Optional, List
from pydantic import BaseModel, Field

class OrderItem(BaseModel):
    sku: str
    qty: int
    price: float

class OrderState(alc.AgentState):
    """Extend AgentState with YOUR business fields"""
    user_id: str
    order_id: str
    items: List[OrderItem] = Field(default_factory=list)
    total: float = 0.0
    shipping_address: Optional[str] = None
    confirmed: bool = False
    payment_intent_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
```

**Key points:**
- Extend `AgentState` (not `BaseModel` directly)
- All fields are optional with defaults
- Use `Field(default_factory=list)` for mutable defaults
- Add any business fields you need

---

## 2. Write Nodes (Plain Functions = Your Logic)

### Sync Node (Pure Computation)

```python
def calculate_total(state: OrderState) -> OrderState:
    state.total = sum(item.qty * item.price for item in state.items)
    return state
```

### Async Node (I/O, API Calls, DB)

```python
async def charge_payment(state: OrderState) -> OrderState:
    from myapp.payments import stripe_client
    intent = await stripe_client.create_payment_intent(
        amount=int(state.total * 100),
        currency="usd",
        customer=state.user_id,
    )
    state.payment_intent_id = intent.id
    return state
```

### Node with Injected Dependencies

```python
from alcyoneus.utils import tool

@tool
async def call_external_api(
    endpoint: str,
    payload: dict,
    state: OrderState,        # injected automatically
    config: dict,             # injected from compile config
) -> dict:
    api_key = config.get("api_key")
    return await http.post(endpoint, json=payload, headers={"Authorization": api_key})
```

### Conditional Routing Node

```python
def route_after_payment(state: OrderState) -> str:
    """Return next node name based on state"""
    if state.payment_intent_id:
        return "fulfill_order"
    return "payment_failed"
```

---

## 3. Build Graph

```python
from alcyoneus.core import StateGraph, START, END

graph = StateGraph(OrderState)

# Add nodes
graph.add_node("calculate", calculate_total)
graph.add_node("charge", charge_payment)
graph.add_node("fulfill", fulfill_order)
graph.add_node("notify", send_confirmation)

# Linear edges
graph.add_edge(START, "calculate")
graph.add_edge("calculate", "charge")

# Conditional branch
graph.add_conditional_edges(
    "charge",
    route_after_payment,
    {"fulfill_order": "fulfill", "payment_failed": "notify"},
)

# Continue flow
graph.add_edge("fulfill", "notify")
graph.add_edge("notify", END)
```

---

## 4. Compile with Options

```python
compiled = graph.compile(
    # Persistence
    checkpointer=InMemoryCheckpointer(),  # or PgCheckpointer
    store=QdrantStore(...),               # optional vector memory
    
    # Interruption (human-in-the-loop)
    interrupt_before=["charge"],          # pause BEFORE node
    interrupt_after=["payment"],          # pause AFTER node
    
    # Limits
    recursion_limit=50,
    shutdown_timeout=30.0,
    
    # Callbacks
    callback_manager=CallbackManager([...]),
)
```

---

## 5. Run / Invoke

### Simple Invoke

```python
result = compiled.invoke({
    "user_id": "user_123",
    "order_id": "ord_456",
    "items": [{"sku": "ABC", "qty": 2, "price": 29.99}],
})
```

### With Persistence (Resume Later)

```python
# First run - creates checkpoint
result = compiled.invoke(
    {"user_id": "user_123", "order_id": "ord_456", ...},
    config={"thread_id": "thread_abc"}  # enables persistence
)

# Later - resume from checkpoint
result = compiled.invoke(
    None,  # None = resume from last checkpoint
    config={"thread_id": "thread_abc"},
)
```

### Async / Streaming

```python
# Async invoke
result = await compiled.ainvoke(input_data, config=config)

# Streaming (real-time UI)
async for chunk in compiled.astream(input_data):
    print(chunk)

# Event streaming (granular events)
async for event in compiled.astream_events(input_data):
    print(f"{event['type']}: {event['payload']}")

# Granularity control
result = await compiled.ainvoke(
    input_data,
    config={"response_granularity": "FULL"}  # LOW | PARTIAL | FULL
)
```

---

## Key Types Reference

| Type | Purpose |
|------|---------|
| `StateGraph` | Build workflow |
| `CompiledGraph` | Runnable, compiled graph |
| `AgentState` | Base class for your state |
| `Message` | LLM messages (`Message.text_message("hi")`) |
| `START` / `END` | Special node constants |
| `CompiledGraph.invoke()` | Sync run |
| `CompiledGraph.ainvoke()` | Async run |
| `CompiledGraph.astream()` | Stream state updates |
| `CompiledGraph.astream_events()` | Stream events |

---

## State Reducers (Advanced)

```python
from alcyoneus.core.state import add_messages, append_items

class MyState(AgentState):
    messages: Annotated[List[Message], add_messages] = []
    tags: Annotated[List[str], append_items] = []

# add_messages: merges message lists (used by Agent)
# append_items: appends to list (no deduplication)
```