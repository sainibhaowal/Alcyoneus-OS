# Protocols — A2A & ACP

> **Agent-to-Agent (A2A) and Agent Communication Protocol (ACP) support.**

---

## Overview

| Protocol | Purpose | Use Case |
|----------|---------|----------|
| **A2A** | Agent-to-Agent communication | Multi-agent systems, agent marketplaces |
| **ACP** | Agent Communication Protocol | Standardized agent messaging |

---

## A2A (Agent-to-Agent)

### Client

```python
from alcyoneus.runtime.protocols import a2a

client = a2a.A2AClient(
    endpoint="https://agent.example.com",
    api_key="your-api-key",
    timeout=30.0,
)

# Send task
result = await client.send_task({
    "message": {
        "role": "user",
        "content": "Analyze this document",
        "parts": [{"type": "file", "file": {"url": "https://example.com/doc.pdf"}}]
    },
    "metadata": {
        "user_id": "user_123",
        "priority": "high"
    }
})

print(result)  # {"task_id": "...", "status": "completed", "artifacts": [...]}
```

### Server

```python
from alcyoneus.runtime.protocols import a2a
from alcyoneus.core import StateGraph, Agent

# Build your agent
agent = Agent(model="google/gemini-2.5-flash", tools=[...])
graph = StateGraph(...).compile()

# Create A2A server
server = a2a.A2AServer(
    agent=graph,
    host="0.0.0.0",
    port=8080,
    auth=a2a.APIKeyAuth(keys={"client_key": "client_123"}),
    cors_origins=["https://app.example.com"],
)

await server.start()
```

### Task Handling

```python
from alcyoneus.runtime.protocols.a2a import TaskHandler

class MyTaskHandler(TaskHandler):
    async def handle_task(self, task: a2a.Task) -> a2a.TaskResult:
        # Extract input
        user_input = task.message.content
        
        # Run your agent
        result = await self.compiled.ainvoke({
            "messages": [{"role": "user", "content": user_input}]
        }, config={"thread_id": task.id})
        
        # Return result
        return a2a.TaskResult(
            status="completed",
            artifacts=[a2a.Artifact(
                type="text",
                content=result["messages"][-1].content
            )]
        )

# Register handler
server = a2a.A2AServer(
    task_handler=MyTaskHandler(compiled=compiled),
    ...
)
```

---

## ACP (Agent Communication Protocol)

### Client

```python
from alcyoneus.runtime.protocols import acp

client = acp.ACPClient(
    endpoint="ws://agent.example.com/acp",
    api_key="...",
)

# Connect
await client.connect()

# Send message
response = await client.send_message({
    "thread_id": "thread_123",
    "message": {
        "role": "user",
        "content": "Hello",
        "parts": [{"type": "text", "text": "Hello"}]
    }
})

# Stream responses
async for message in client.stream_messages("thread_123"):
    print(f"Received: {message.content}")
```

### Server

```python
from alcyoneus.runtime.protocols import acp

server = acp.ACPServer(
    host="0.0.0.0",
    port=8081,
    handler=my_agent_handler,
    auth=acp.TokenAuth(tokens=["token1", "token2"]),
)

await server.start()
```

### Message Types

```python
from alcyoneus.runtime.protocols.acp import (
    ACPMessage, ACPMessagePart, ACPThread,
)

# Send
await client.send(ACPMessage(
    thread_id="thread_123",
    message=ACPMessage(
        role="user",
        parts=[
            ACPMessagePart(type="text", text="Hello"),
            ACPMessagePart(type="file", file={"url": "https://example.com/doc.pdf"})
        ]
    )
))

# Receive
async for msg in client.stream("thread_123"):
    if msg.type == "text":
        print(msg.content)
    elif msg.type == "tool_call":
        print(f"Tool: {msg.tool_name}")
    elif msg.type == "tool_result":
        print(f"Result: {msg.result}")
```

---

## 3. Message Format

### A2A Message

```json
{
  "id": "msg_123",
  "role": "user",
  "parts": [
    {"type": "text", "text": "Hello"},
    {"type": "file", "file": {"url": "https://example.com/doc.pdf", "mime": "application/pdf"}}
  ],
  "metadata": {"user_id": "123"}
}
```

### ACP Message

```json
{
  "thread_id": "thread_123",
  "message": {
    "role": "user",
    "parts": [
      {"type": "text", "text": "Hello"},
      {"type": "tool_call", "tool_call": {"name": "search", "arguments": {"query": "AI"}}}
    ]
  }
}
```

---

## 4. Authentication

### A2A

```python
from alcyoneus.runtime.protocols.a2a import APIKeyAuth, JWTAuth, OAuth2Auth

# API Key
auth = APIKeyAuth(keys={"client_1": "secret_1"})

# JWT
auth = JWTAuth(
    public_key="-----BEGIN PUBLIC KEY-----...",
    algorithm="RS256",
    audience="my-app"
)

# OAuth2
auth = OAuth2Auth(
    token_url="https://auth.example.com/token",
    client_id="my-client",
    client_secret="...",
    scopes=["agent:read", "agent:write"],
)

server = a2a.A2AServer(auth=auth, ...)
```

### ACP

```python
from alcyoneus.runtime.protocols.acp import TokenAuth, JWTAuth

auth = TokenAuth(tokens=["token1", "token2"])
# or
auth = JWTAuth(public_key="...", algorithm="RS256")
```

---

## 4. Error Handling

```python
from alcyoneus.runtime.protocols.a2a import A2AError, A2AErrorCode

try:
    result = await client.send_task(task)
except A2AError as e:
    if e.code == A2AErrorCode.TASK_NOT_FOUND:
        # Handle
    elif e.code == A2AErrorCode.AGENT_UNAVAILABLE:
        # Retry
    elif e.code == A2AErrorCode.AUTH_FAILED:
        # Re-auth
```

---

## 5. Interoperability

### A2A → ACP Bridge

```python
from alcyoneus.runtime.protocols import a2a, acp

# Convert A2A task to ACP message
def a2a_to_acp(task: a2a.Task) -> acp.ACPMessage:
    return acp.ACPMessage(
        thread_id=task.id,
        message=acp.ACPMessage(
            role="user",
            parts=[acp.ACPMessagePart(type="text", text=task.message.content)]
        )
    )
```

---

## 6. Quick Reference

| Feature | A2A | ACP |
|---------|-----|-----|
| Transport | HTTP/REST | WebSocket |
| Pattern | Request/Response | Streaming |
| Auth | API Key, JWT, OAuth2 | Token, JWT |
| Use Case | Task-based | Conversational |
| Artifacts | Yes | Via parts |
| Streaming | Polling | Native |

---

## 7. Running Both

```python
# Run A2A and ACP servers together
import asyncio

async def main():
    a2a_server = a2a.A2AServer(...)
    acp_server = acp.ACPServer(...)
    
    await asyncio.gather(
        a2a_server.start(),
        acp_server.start(),
    )

asyncio.run(main())
```