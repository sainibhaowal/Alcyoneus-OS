# Configuration — All Compile & Runtime Options

> **Every configuration option for `graph.compile()` and runtime.**

---

## Compile Options

```python
compiled = graph.compile(
    # ============================================
    # PERSISTENCE
    # ============================================
    checkpointer=InMemoryCheckpointer(),      # Checkpointer instance
    store=QdrantStore(...),                   # Vector store (optional)
    memory_config=MemoryConfig(...),          # Memory configuration
    
    # ============================================
    # MEDIA (Multimodal)
    # ============================================
    media_config=MediaConfig(...),            # Media configuration
    media_resolver=MediaResolver(...),        # Media resolver
    
    # ============================================
    # INTERRUPTS (Human-in-the-loop)
    # ============================================
    interrupt_before=["node_name"],           # Pause BEFORE node
    interrupt_after=["node_name"],            # Pause AFTER node
    
    # ============================================
    # CALLBACKS & HOOKS
    # ============================================
    callback_manager=CallbackManager([...]),  # Custom callbacks
    
    # ============================================
    # LIMITS & TIMEOUTS
    # ============================================
    recursion_limit=50,                       # Max recursion depth
    shutdown_timeout=30.0,                    # Graceful shutdown (seconds)
    
    # ============================================
    # EVENT HOOKS (Inline)
    # ============================================
    on_node_start=lambda node, state: ...,
    on_node_end=lambda node, state: ...,
    on_tool_call=lambda tool, args: ...,
    on_tool_result=lambda tool, result: ...,
    on_error=lambda error, state: ...,
)
```

---

## All Options Reference

### Persistence

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `checkpointer` | `BaseCheckpointer` | `InMemoryCheckpointer()` | State persistence |
| `store` | `BaseStore` | `None` | Vector/long-term memory |
| `memory_config` | `MemoryConfig` | `None` | Per-agent memory config |

### Media

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `media_config` | `MediaConfig` | `None` | Media processing config |
| `media_resolver` | `MediaResolver` | `None` | Media URL resolver |

### Interrupts

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `interrupt_before` | `List[str]` | `[]` | Node names to pause before |
| `interrupt_after` | `List[str]` | `[]` | Node names to pause after |

### Callbacks

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `callback_manager` | `CallbackManager` | `None` | Custom callbacks |

### Limits

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `recursion_limit` | `int` | `25` | Max recursion depth |
| `shutdown_timeout` | `float` | `30.0` | Graceful shutdown seconds |

### Event Hooks

| Hook | Signature | When |
|------|-----------|------|
| `on_node_start` | `(node: str, state: State) -> None` | Node starts |
| `on_node_end` | `(node: str, state: State) -> None` | Node ends |
| `on_tool_call` | `(tool: str, args: dict) -> None` | Tool invoked |
| `on_tool_result` | `(tool: str, result: Any) -> None` | Tool returns |
| `on_error` | `(error: Exception, state: State) -> None` | Error occurs |

---

## Runtime Config (Per Invocation)

```python
# Sync
result = compiled.invoke(
    input_data,
    config={
        # Required for persistence
        "thread_id": "thread_123",
        "user_id": "user_123",
        
        # Optional
        "run_id": "run_001",
        "recursion_limit": 25,
        "metadata": {"source": "api", "version": "1.0"},
        
        # Response granularity
        "response_granularity": "FULL",  # LOW | PARTIAL | FULL
    }
)
```

### Config Keys

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `thread_id` | `str` | For persistence | Unique thread identifier |
| `user_id` | `str` | Optional | User identifier |
| `run_id` | `str` | Optional | Run identifier |
| `recursion_limit` | `int` | Optional | Override compile limit |
| `response_granularity` | `str` | Optional | `LOW` \| `PARTIAL` \| `FULL` |
| `metadata` | `dict` | Optional | Custom metadata |

---

## Response Granularity

| Value | Output |
|-------|--------|
| `LOW` (default) | `{"messages": [...]}` only |
| `PARTIAL` | `{"context": {...}, "summary": "...", "messages": [...]}` |
| `FULL` | Entire `AgentState` |

---

## Agent Configuration

```python
from alcyoneus.core import Agent

agent = Agent(
    # Required
    model="google/gemini-2.5-flash",
    
    # Optional
    system_prompt="You are a helpful assistant.",
    tools=[safe_calculator, fetch_url],
    output_type="text",                    # "text" | "structured" | "tool"
    output_schema=MyPydanticModel,         # For structured output
    tool_node=ToolNode(tools=[...]),       # Custom ToolNode
    tool_node_name="tools",
    max_tool_iterations=10,
    tool_choice="auto",                    # "auto" | "any" | "none" | "tool_name"
    retry_config=RetryConfig(...),
    fallback_models=["gpt-4o"],            # Fallback models
    multimodal_config=MediaConfig(...),    # Multimodal
    memory_config=AgentMemoryConfig(...),  # Per-agent memory
    reasoning_config={...},                # Reasoning config
    skills=SkillConfig(...),               # Dynamic skills
    input_guardrail=InputGuardrail(...),   # Input validation
    output_guardrail=OutputGuardrail(...), # Output validation
    tool_guardrail=ToolGuardrail(...),     # Tool policy
)
```

---

## Checkpointer Config

### InMemoryCheckpointer

```python
InMemoryCheckpointer()  # No config
```

### PgCheckpointer

```python
PgCheckpointer(
    conn_str="postgresql://user:pass@host:5432/db",
    redis_url="redis://localhost:6379/0",
    pool_size=10,
    pool_timeout=30.0,
)
```

---

## Vector Store Config

### QdrantStore

```python
QdrantStore(
    url="https://cluster.qdrant.io",
    api_key="...",
    collection="my_collection",
    embedding_model="text-embedding-3-small",
    vector_size=1536,
    distance="Cosine",  # "Cosine" | "Euclidean" | "Dot"
    timeout=30.0,
)
```

### Mem0Store

```python
Mem0Store(
    api_key="...",
    org_id="...",
    project_id="...",
)
```

---

## Memory Config

```python
MemoryConfig(
    store=vector_store,
    namespace="user_{user_id}",
    max_tokens=4000,
    ttl_days=30,
    retrieval_top_k=5,
    retrieval_threshold=0.7,
)
```

---

## Media Config

```python
MediaConfig(
    max_size_mb=50,
    allowed_types=["image/*", "audio/*", "video/*", "application/pdf"],
    storage="s3://bucket/media",
    public_base_url="https://cdn.example.com",
    temp_dir="/tmp/alcyoneus_media",
)
```

---

## Retry Config

```python
RetryConfig(
    max_retries=3,
    base_delay=1.0,
    max_delay=60.0,
    exponential_base=2.0,
    retry_on=[ConnectionError, TimeoutError],
)
```

---

## Skill Config

```python
SkillConfig(
    skills_dir="./skills",
    mode="on-demand",  # "on-demand" | "session"
    watch=True,        # hot reload in dev
    preload=["skill1", "skill2"],  # for session mode
)
```

---

## Guardrails Config

```python
InputGuardrail(
    blocked_patterns=[r"password", r"api_key"],
    max_length=10000,
    custom_validator=lambda text: len(text) > 0,
)

OutputGuardrail(
    blocked_words=["secret", "internal"],
    require_json_schema=MySchema,
    max_length=50000,
)

ToolGuardrail(
    allowed_tools=["search", "calc"],
    blocked_tools=["shell"],
    rate_limit=100,
    tool_limits={"fetch": {"timeout": 10}},
)
```

---

## Complete Example

```python
compiled = graph.compile(
    checkpointer=PgCheckpointer(conn_str="postgresql://..."),
    store=QdrantStore(url="...", collection="memory"),
    memory_config=MemoryConfig(namespace="user_{user_id}"),
    media_config=MediaConfig(storage="s3://bucket"),
    interrupt_before=["human_review"],
    interrupt_after=["payment"],
    recursion_limit=50,
    shutdown_timeout=30.0,
    callback_manager=CallbackManager([LoggingCallback()]),
    on_node_start=lambda n, s: logger.info(f"Starting {n}"),
    on_node_end=lambda n, s: logger.info(f"Finished {n}"),
    on_tool_call=lambda t, a: logger.info(f"Tool {t} called"),
    on_tool_result=lambda t, r: logger.info(f"Tool {t} result: {r}"),
    on_error=lambda e, s: sentry.capture_exception(e),
)
```