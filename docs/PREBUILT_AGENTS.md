# Prebuilt Agents — Ready-to-Use Patterns

> **Drop-in agent patterns for common use cases — including Voice/Audio, MCP, and Realtime agents.**

---

## Quick Comparison

| Agent | Use When | Key Feature |
|-------|----------|-------------|
| `Agent` | Simple LLM calls, tool use | Minimal setup, 10-30 lines |
| `ReactAgent` | Tool-use loops, reasoning | ReAct pattern, tool loops |
| `RAGAgent` | Document Q&A | Vector store + retrieval |
| `SwarmAgent` | Multi-agent collaboration | Peer-to-peer handoffs |
| `SupervisorTeamAgent` | Hierarchical teams | Supervisor delegates to team |
| `StructuredOutputAgent` | Guaranteed JSON schema | Pydantic schema enforcement |
| `PlanActReflectAgent` | Plan → Execute → Reflect | Iterative improvement |
| `AudioAgent` | Real-time audio-to-audio | Gemini Live, OpenAI Realtime, Azure, Local Whisper+TTS |
| `RouterAgent` | Route queries to specialists | Dynamic routing |

---

## 1. Agent (Base Class) — Minimal Setup

```python
from alcyoneus.core import Agent, StateGraph, ToolNode

agent = Agent(model="gemini/gemini-2.5-flash", tool_node="tools")
graph = StateGraph()
graph.add_node("agent", agent)
graph.add_node("tools", ToolNode([my_tool]))
graph.add_edge("agent", "tools")
graph.add_edge("tools", "agent")
```

---

## 2. ReactAgent — Tool-Use Loops

```python
from alcyoneus.prebuilt.agent import ReactAgent
from alcyoneus.prebuilt.tools import safe_calculator, fetch_url, google_web_search

agent = ReactAgent(
    model="google/gemini-2.5-flash",
    tools=[safe_calculator, fetch_url, google_web_search],
    system_prompt="You are a research assistant. Use tools to answer questions.",
    max_iterations=10,          # max tool loops
    return_intermediate=False,  # return only final answer
)

# Use in graph
graph = StateGraph(alc.AgentState)
graph.add_node("react", agent)
graph.add_edge(START, "react")
graph.add_edge("react", END)

result = compiled.invoke({"messages": [{"role": "user", "content": "What's the population of Tokyo?"}]})
```

**Key params:**
| Param | Default | Description |
|-------|---------|-------------|
| `model` | required | LLM model string |
| `tools` | `[]` | List of `@tool` functions |
| `system_prompt` | `None` | System prompt |
| `max_iterations` | `10` | Max tool loops |
| `return_intermediate` | `False` | Return intermediate steps |

---

## 2. RAGAgent — Document Q&A

```python
from alcyoneus.prebuilt.agent import RAGAgent
from alcyoneus.storage.store import QdrantStore

store = QdrantStore(
    url="https://your-cluster.qdrant.io",
    api_key="...",
    collection="my_docs",
    embedding_model="text-embedding-3-small",
)

agent = RAGAgent(
    model="google/gemini-2.5-flash",
    store=store,
    top_k=5,                    # docs to retrieve
    similarity_threshold=0.7,   # min similarity
    system_prompt="Answer using only the retrieved documents.",
)

# In graph
graph.add_node("rag", agent)
graph.add_edge(START, "rag")
graph.add_edge("rag", END)

result = compiled.invoke({"messages": [{"role": "user", "content": "What's our refund policy?"}]})
```

**Key params:**
| Param | Default | Description |
|-------|---------|-------------|
| `store` | required | Vector store (QdrantStore, Mem0Store) |
| `top_k` | `5` | Number of docs to retrieve |
| `similarity_threshold` | `0.7` | Min cosine similarity |
| `rerank` | `False` | Enable reranking |

---

## 3. SwarmAgent — Peer-to-Peer Multi-Agent

```python
from alcyoneus.prebuilt.agent import SwarmAgent, ReactAgent

researcher = ReactAgent(
    model="google/gemini-2.5-flash",
    tools=[google_web_search, fetch_url],
    name="researcher",
    system_prompt="You research topics and return summaries.",
)

coder = ReactAgent(
    model="google/gemini-2.5-flash",
    tools=[code_interpreter, file_write],
    name="coder",
    system_prompt="You write and execute code.",
)

swarm = SwarmAgent(
    model="google/gemini-2.5-flash",
    agents=[researcher, coder],
    max_handoffs=5,           # max agent switches
    system_prompt="Collaborate to solve the task.",
)

graph.add_node("swarm", swarm)
graph.add_edge(START, "swarm")
graph.add_edge("swarm", END)
```

---

## 4. SupervisorTeamAgent — Hierarchical Teams

```python
from alcyoneus.prebuilt.agent import SupervisorTeamAgent, ReactAgent

researcher = ReactAgent(model="...", tools=[...], name="researcher")
coder = ReactAgent(model="...", tools=[...], name="coder")
reviewer = ReactAgent(model="...", tools=[...], name="reviewer")

team = SupervisorTeamAgent(
    model="google/gemini-2.5-flash",
    team={
        "researcher": researcher,
        "coder": coder,
        "reviewer": reviewer,
    },
    supervisor_prompt="Delegate tasks to team members. Review all outputs.",
    max_handoffs=10,
)

graph.add_node("team", team)
```

---

## 3. StructuredOutputAgent — Guaranteed JSON

```python
from pydantic import BaseModel
from alcyoneus.prebuilt.agent import StructuredOutputAgent

class AnalysisResult(BaseModel):
    sentiment: str = Field(description="positive|negative|neutral")
    key_points: List[str] = Field(max_items=5)
    confidence: float = Field(ge=0, le=1)

agent = StructuredOutputAgent(
    model="google/gemini-2.5-flash",
    output_schema=AnalysisResult,
    system_prompt="Analyze the text and return structured analysis.",
)

# In graph
graph.add_node("analyze", agent)
result = compiled.invoke({"messages": [{"role": "user", "content": "I love this product!"}]})
# result["output"] is AnalysisResult instance
```

### MCP Integration
 
```python
from alcyoneus.core.mcp import MCPClient, create_transport, StdioTransport, SSETransport, WebSocketTransport
 
# Stdio transport (local MCP server)
stdio_transport = create_transport("stdio", command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", "/workspace"])
client = MCPClient(stdio_transport)
await client.connect()
tools = await client.list_tools()
 
# SSE transport (HTTP+SSE)
sse_transport = create_transport("sse", url="http://mcp-server:8000/sse", headers={"Authorization": "Bearer token"})
client = MCPClient(sse_transport)
 
# WebSocket transport
ws_transport = create_transport("websocket", url="ws://mcp-server:8000/ws")
client = MCPClient(ws_transport)
 
# All support capability negotiation & tool caching (5min TTL)
await client.connect()
tools = await client.list_tools(force_refresh=False)  # Uses cache
result = await client.call_tool("read_file", {"path": "/workspace/file.txt"})
 
# MCP Server Hosting
from alcyoneus.core.mcp import MCPServerStdio, MCPServerStreamableHTTP, MCPManager
 
# Stdio server
server = MCPServerStdio("fs", command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", "/workspace"])
await server.connect()
tools = await server.list_tools()
 
# HTTP server
server = MCPServerStreamableHTTP(name="my-server", url="http://0.0.0.0:8000/mcp")
await server.connect()
 
# Multi-server management with approval
manager = MCPManager(
    servers=[MCPServerStdio("fs", command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", "/workspace"])],
    approval_fn=lambda req: MCPToolApprovalResult(approved=req.tool_name != "delete"),
)
await manager.connect_all()
tools = await manager.list_all_tools()          # aggregated across every server
```
 
---
 
## Using Prebuilt Agents in Graphs
 
```python
graph = StateGraph(alc.AgentState)
 
# Option 1: As node directly
graph.add_node("react", ReactAgent(...))
 
# Option 2: As tool (for handoff)
from alcyoneus.prebuilt.tools import create_handoff_tool
handoff = create_handoff_tool(ReactAgent(...), name="researcher")
 
# Option 2b: In SupervisorTeam
team = SupervisorTeamAgent(
    team={
        "researcher": ReactAgent(...),
    }
)
```
 
---
 
## Agent Configuration Reference
 
| Parameter | ReactAgent | RAGAgent | SwarmAgent | SupervisorTeamAgent | StructuredOutputAgent | PlanActReflectAgent | AudioAgent | RouterAgent |
|-----------|------------|----------|------------|---------------------|----------------------|---------------------|------------|-------------|
| `model` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `tools` | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ |
| `system_prompt` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `store` | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `top_k` | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `agents` | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ |
| `team` | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| `output_schema` | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| `max_iterations` | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ |
| `max_handoffs` | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ |
| `output_schema` | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| `realtime_config` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| `voice` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| `barge_in_enabled` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| `realtime_config` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
 
---
 
## When to Use Which
 
| Need | Use |
|------|-----|
| "I need the LLM to use tools" | `ReactAgent` |
| "Answer questions from my docs" | `RAGAgent` |
| "Multiple agents working together" | `SwarmAgent` |
| "Hierarchical team with supervisor" | `SupervisorTeamAgent` |
| "Guaranteed JSON output" | `StructuredOutputAgent` |
| "Plan, execute, self-correct" | `PlanActReflectAgent` |
| "Real-time voice conversations" | `AudioAgent` |
| "Route to specialized agents" | `RouterAgent` |
| "Connect to external MCP servers" | `MCPClient` + `ToolNode` |
| "Host my own MCP server" | `MCPServerStdio` / `MCPServerStreamableHTTP` |
| "Just call LLM once" | `Agent(model="...")` |