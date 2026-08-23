# Persistence — Checkpointing, Vector Stores, Media

> **How to persist state, memory, and media in Alcyoneus OS.**

---

## Overview — Three Layers

```
┌─────────────────────────────────────────┐
│  Working State (AgentState)             │  ← In-memory, per-run
├─────────────────────────────────────────┤
│  Checkpointer (Short-term / Resume)     │  ← Per-thread, durable
├─────────────────────────────────────────┤
│  Vector Store (Long-term Memory / RAG)  │  ← Cross-thread, semantic
└─────────────────────────────────────────┘
```

---

## 1. Checkpointers — Short-term / Resume

### InMemoryCheckpointer (Dev/Testing)

```python
from alcyoneus.storage.checkpointer import InMemoryCheckpointer

checkpointer = InMemoryCheckpointer()
compiled = graph.compile(checkpointer=checkpointer)
```

### PgCheckpointer (Production)

```python
from alcyoneus.storage.checkpointer import PgCheckpointer

checkpointer = PgCheckpointer(
    conn_str="postgresql://user:pass@host:5432/db",
    redis_url="redis://localhost:6379/0",  # for distributed locking
)

compiled = graph.compile(checkpointer=checkpointer)
```

**Requires:** `pip install "alcyoneus[pg_checkpoint]"`

### Using Checkpointers

```python
compiled = graph.compile(checkpointer=checkpointer)

# First run - creates checkpoint
result = compiled.invoke(
    {"user_id": "user_123", ...},
    config={"thread_id": "thread_abc"}  # enables persistence
)

# Resume from checkpoint
result = compiled.invoke(
    None,  # None = resume from last checkpoint
    config={"thread_id": "thread_abc"},
)

# List checkpoints
checkpoints = await checkpointer.alist(config={"thread_id": "thread_abc"})
# Returns: [{"thread_id": "...", "checkpoint_id": "...", "created_at": ...}, ...]

# Get specific checkpoint
checkpoint = await checkpointer.aget(config={"thread_id": "thread_abc", "checkpoint_id": "..."})

# Delete checkpoints
await checkpointer.adelete_thread("thread_abc")
```

### Custom Checkpointer

```python
from alcyoneus.storage.checkpointer import BaseCheckpointer

class MyCheckpointer(BaseCheckpointer):
    async def aget(self, config):
        ...

    async def aput(self, config, state):
        ...

    async def alist(self, config):
        ...
```

---

## 2. Vector Stores — Long-term Memory / RAG

### QdrantStore

```python
from alcyoneus.storage.store import QdrantStore

store = QdrantStore(
    url="https://your-cluster.qdrant.io",
    api_key="...",
    collection="my_collection",
    embedding_model="text-embedding-3-small",  # or "text-embedding-ada-002"
    vector_size=1536,  # must match model
    distance="Cosine",  # or "Euclidean", "Dot"
)

# Add documents
await store.aadd([
    {"id": "1", "content": "Doc 1 content", "metadata": {"source": "doc1"}},
    {"id": "2", "content": "Doc 2 content", "metadata": {"source": "doc2"}},
])

# Search
results = await store.asearch("query text", top_k=5, filter={"user_id": "user_123"})
# Returns: [{"id": "...", "content": "...", "score": 0.95, "metadata": {...}}, ...]

# Delete
await store.adelete(["1", "2"])
```

### Mem0Store (Managed)

```python
from alcyoneus.storage.store import Mem0Store

store = Mem0Store(
    api_key="...",
    org_id="...",
    project_id="...",
)

# Same interface as QdrantStore
```

### Memory Config (Per-Agent)

```python
from alcyoneus.storage.store import MemoryConfig, AgentMemoryConfig

memory_config = MemoryConfig(
    store=store,
    namespace="user_{user_id}",  # template with state fields
    max_tokens=4000,             # max context tokens
    ttl_days=30,                 # auto-expire
    retrieval_top_k=5,
    retrieval_threshold=0.7,
)

# Per-agent override
agent_config = AgentMemoryConfig(
    store=store,
    namespace="agent_{agent_name}",
    max_tokens=2000,
)

compiled = graph.compile(
    checkpointer=checkpointer,
    store=store,
    memory_config=memory_config,
)
```

### Memory Tool (Auto RAG)

```python
from alcyoneus.prebuilt.tools import memory_tool, create_memory_preload_node

# Tool for agent to read/write memory
agent = Agent(model="...", tools=[memory_tool])

# Preload memory at graph start
preload_node = create_memory_preload_node(
    query="user preferences",
    namespace="user_{user_id}",
    top_k=3,
)

graph.add_node("preload_memory", preload_node)
graph.add_edge(START, "preload_memory")
graph.add_edge("preload_memory", "agent")
```

---

## 3. Media (Multimodal)

```python
from alcyoneus.storage.media import MediaConfig, MediaResolver, MediaProcessor

config = MediaConfig(
    max_size_mb=50,
    allowed_types=["image/*", "audio/*", "video/*", "application/pdf"],
    storage="s3://my-bucket/media",
    public_base_url="https://cdn.example.com",
)

resolver = MediaResolver(config)
processor = MediaProcessor(config)

# In agent
agent = Agent(
    model="google/gemini-2.5-flash",
    multimodal_config=config,
)

# Resolve media reference
media_ref = await resolver.resolve("s3://bucket/image.png")
# Returns: {"url": "https://cdn.example.com/...", "mime_type": "image/png", "size": 1024}

# Process (resize, transcode, etc.)
processed = await processor.process(media_ref, operations=["resize:800x600"])
```

---

## Complete Compile Example

```python
from alcyoneus.storage.checkpointer import PgCheckpointer
from alcyoneus.storage.store import QdrantStore, MemoryConfig
from alcyoneus.storage.media import MediaConfig

checkpointer = PgCheckpointer(
    conn_str="postgresql://user:pass@host/db",
    redis_url="redis://localhost:6379",
)

vector_store = QdrantStore(
    url="https://cluster.qdrant.io",
    api_key="...",
    collection="agent_memory",
)

memory_config = MemoryConfig(
    store=vector_store,
    namespace="user_{user_id}",
    max_tokens=4000,
    ttl_days=30,
)

media_config = MediaConfig(
    max_size_mb=50,
    allowed_types=["image/*", "audio/*", "video/*"],
    storage="s3://my-bucket/media",
)

compiled = graph.compile(
    checkpointer=checkpointer,
    store=vector_store,
    memory_config=memory_config,
    media_config=media_config,
    interrupt_before=["human_review"],
    recursion_limit=50,
    shutdown_timeout=30.0,
)

# Run with full config
result = await compiled.ainvoke(
    {"user_id": "user_123", ...},
    config={
        "thread_id": "thread_123",
        "user_id": "user_123",
        "run_id": "run_001",
        "response_granularity": "FULL",
    }
)
```

---

## Quick Reference

| Need | Class | Install |
|------|-------|---------|
| Dev checkpointing | `InMemoryCheckpointer` | core |
| Prod checkpointing | `PgCheckpointer` | `pip install "alcyoneus[pg_checkpoint]"` |
| Vector search | `QdrantStore` | `pip install "alcyoneus[qdrant]"` |
| Managed memory | `Mem0Store` | `pip install "alcyoneus[mem0]"` |
| Media handling | `MediaConfig`, `MediaResolver` | core |
| Preload memory | `create_memory_preload_node` | `pip install "alcyoneus[qdrant]"` |
| Memory tool | `memory_tool` | core |