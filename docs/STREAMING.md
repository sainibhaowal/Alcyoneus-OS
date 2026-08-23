# Streaming — Real-time Event Streaming

> **Real-time UI updates, granular events, and granularity control.**

---

## Overview

```
compiled.astream()       → State updates (yielded per node)
compiled.astream_events() → Granular events (per tool call, node start/end, etc.)
```

---

## 1. State Streaming (`astream`)

```python
# Async iteration over state updates
async for state_update in compiled.astream(input_data):
    # Each yield = state after a node completes
    print(f"Node completed, state keys: {state_update.keys()}")
    # {'messages': [...], 'total': 100, ...}
```

**Yields:** Full state after each node completes.

---

## 2. Event Streaming (`astream_events`)

```python
async for event in compiled.astream_events(input_data):
    print(f"Type: {event['type']}")
    print(f"Payload: {event.get('payload')}")
    print(f"Metadata: {event.get('metadata')}")
```

### Event Types

| Event Type | When | Payload |
|------------|------|---------|
| `graph_start` | Graph begins | `{run_id, thread_id}` |
| `node_start` | Node begins | `{node_name, state_preview}` |
| `node_end` | Node completes | `{node_name, state_update}` |
| `tool_call` | Tool invoked | `{tool_name, arguments, tool_call_id}` |
| `tool_result` | Tool returns | `{tool_name, output, tool_call_id}` |
| `tool_error` | Tool fails | `{tool_name, error, tool_call_id}` |
| `interrupt` | Graph interrupted | `{interrupt_info}` |
| `graph_end` | Graph ends | `{final_state, run_id}` |
| `error` | Graph error | `{error, traceback}` |

### Example: Real-time Chat UI

```python
async def stream_response(user_input: str):
    async for event in compiled.astream_events({
        "messages": [{"role": "user", "content": user_input}]
    }):
        if event["type"] == "tool_call":
            yield f"🔧 Calling {event['payload']['tool_name']}..."
        elif event["type"] == "tool_result":
            yield f"✅ Result: {event['payload']['output'][:100]}..."
        elif event["type"] == "node_end" and event["payload"].get("messages"):
            last_msg = event["payload"]["messages"][-1]
            if last_msg.get("role") == "assistant":
                yield last_msg["content"]
        elif event["type"] == "graph_end":
            yield "✅ Done"
```

---

## 3. Granularity Control

```python
# LOW (default): messages only
result = await compiled.ainvoke(input_data)
# result["messages"] only

# PARTIAL: context + summary + messages
result = await compiled.ainvoke(
    input_data,
    config={"response_granularity": "PARTIAL"}
)
# result: {context: {...}, summary: "...", messages: [...]}

# FULL: entire state
result = await compiled.ainvoke(
    input_data,
    config={"response_granularity": "FULL"}
)
# result: entire AgentState
```

| Granularity | Use Case |
|-------------|----------|
| `LOW` (default) | Chat UI, minimal payload |
| `PARTIAL` | Debugging, audit logs |
| `FULL` | Full state inspection, replay |

---

## 4. Streaming with Config

```python
# Stream with persistence
async for event in compiled.astream_events(
    input_data,
    config={
        "thread_id": "thread_123",
        "user_id": "user_123",
        "run_id": "run_001",
    }
):
    ...

# Stream with granularity
async for event in compiled.astream_events(
    input_data,
    config={"response_granularity": "PARTIAL"}
):
    ...
```

---

## 5. Sync Streaming (for non-async contexts)

```python
# Requires running in thread pool
import asyncio

def run_streaming():
    return asyncio.run(_stream())

async def _stream():
    async for event in compiled.astream_events(input_data):
        yield event
```

---

## 5. Event Filtering

```python
async for event in compiled.astream_events(input_data):
    # Filter by type
    if event["type"] not in ("node_start", "node_end"):
        continue
    
    # Filter by node
    if event.get("metadata", {}).get("node_name") != "my_node":
        continue
    
    process(event)
```

---

## 6. Error Handling in Streams

```python
async for event in compiled.astream_events(input_data):
    if event["type"] == "error":
        print(f"❌ Error: {event['payload']['error']}")
        # Decide: retry, fallback, or abort
        break
    elif event["type"] == "tool_error":
        print(f"Tool failed: {event['payload']['error']}")
        # Can continue or handle
```

---

## 7. Buffering / Batching

```python
async def batched_stream(compiled, input_data, batch_size=10):
    buffer = []
    async for event in compiled.astream_events(input_data):
        buffer.append(event)
        if len(buffer) >= batch_size:
            yield buffer
            buffer = []
    if buffer:
        yield buffer

# Usage
async for batch in batched_stream(compiled, input_data, batch_size=5):
    await send_to_websocket(batch)
```

---

## 7. Complete Example: Chat with Streaming

```python
from alcyoneus.core import StateGraph, Agent, START, END
from alcyoneus.storage.checkpointer import InMemoryCheckpointer
from alcyoneus.prebuilt.tools import safe_calculator, fetch_url

class ChatState(alc.AgentState):
    messages: List[Message] = []

agent = Agent(
    model="google/gemini-2.5-flash",
    tools=[safe_calculator, fetch_url],
    system_prompt="You are a helpful assistant.",
)

graph = StateGraph(ChatState)
graph.add_node("agent", agent)
graph.add_edge(START, "agent")
graph.add_edge("agent", END)

compiled = graph.compile(
    checkpointer=InMemoryCheckpointer()
)

# Streaming endpoint
async def chat_endpoint(user_input: str, thread_id: str):
    async for event in compiled.astream_events(
        {"messages": [{"role": "user", "content": user_input}]},
        config={"thread_id": thread_id, "response_granularity": "PARTIAL"}
    ):
        if event["type"] == "tool_call":
            yield {"type": "tool_start", "tool": event["payload"]["tool_name"]}
        elif event["type"] == "tool_result":
            yield {"type": "tool_end", "result": event["payload"]["output"]}
        elif event["type"] == "graph_end":
            final_msg = event["payload"]["messages"][-1]
            yield {"type": "final", "content": final_msg["content"]}
```