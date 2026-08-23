<div align="center">
  <img src="https://raw.githubusercontent.com/sainibhaowal/Alcyoneus-OS/main/assets/png/alcyoneus_banner_1200x320.png" alt="Alcyoneus OS Banner" width="100%" />
  <p>
    <a href="https://pypi.org/project/alcyoneus/"><img src="https://img.shields.io/badge/PyPI-v1.0.0-00F0FF?style=flat-square&logo=pypi&logoColor=white" alt="PyPI" /></a>&nbsp;
    <a href="https://github.com/sainibhaowal/Alcyoneus-OS/releases/tag/v1.0.0"><img src="https://img.shields.io/badge/Release-v1.0.0-38BDF8?style=flat-square&logo=github" alt="Release" /></a>&nbsp;
    <a href="https://github.com/sainibhaowal/Alcyoneus-OS"><img src="https://img.shields.io/badge/Python-3.12%20|%203.13-3B82F6?style=flat-square&logo=python" alt="Python Versions" /></a>&nbsp;
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-6366F1?style=flat-square" alt="License: MIT" /></a>&nbsp;
    <a href="https://github.com/sainibhaowal/Alcyoneus-OS/actions"><img src="https://img.shields.io/badge/CI-Passing-10B981?style=flat-square&logo=github-actions" alt="CI Status" /></a>&nbsp;
    <a href="https://github.com/sainibhaowal/Alcyoneus-OS"><img src="https://img.shields.io/badge/Coverage-80%25-10B981?style=flat-square" alt="Coverage" /></a>
  </p>
</div>

---

**Alcyoneus OS** is a production-grade Python framework for building intelligent agents and orchestrating multi-agent state-graph workflows. It provides an LLM-agnostic workflow engine with built-in persistence, streaming, human-in-the-loop, guardrails, multi-agent orchestration, sandboxing, and enterprise-grade observability.

```python
import alcyoneus as alc
from alcyoneus.core import StateGraph, Agent, ToolNode, START, END
from alcyoneus.storage.checkpointer import InMemoryCheckpointer
from alcyoneus.prebuilt.tools import safe_calculator, google_web_search

# 1. Define a tool
def get_weather(location: str) -> str:
    return f"It's sunny in {location}"

# 2. Build graph with Agent + tools
graph = StateGraph()
graph.add_node("agent", Agent(model="gemini/gemini-2.5-flash", tool_node="tools"))
graph.add_node("tools", ToolNode([get_weather]))
graph.add_edge("agent", "tools")
graph.add_edge("tools", "agent")
graph.set_entry_point("agent")

# 3. Run with persistence
compiled = graph.compile(checkpointer=InMemoryCheckpointer())
result = compiled.invoke(
    {"messages": [{"role": "user", "content": "Weather in NYC?"}]},
    config={"thread_id": "demo"}
)
```

---

## ✨ Key Features (100+ Production-Grade Capabilities)

### 🤖 Agent Engine & Orchestration
| Feature | Description |
|---------|-------------|
| **Agent Class** | Build complete agents in 10-30 lines |
| **StateGraph** | LangGraph-inspired engine with nodes, edges, conditional routing |
| **ReactAgent** | Reasoning + tool-use loops with ReAct pattern |
| **RAGAgent** | Retrieval-augmented generation with vector stores |
| **SwarmAgent** | Dynamic multi-agent collaboration |
| **SupervisorTeamAgent** | Hierarchical agent coordination |
| **PlanActReflectAgent** | Plan → Execute → Reflect cycles |
| **StructuredOutputAgent** | Guaranteed JSON schema output |
| **AudioAgent** | Real-time audio-to-audio (Gemini Live, OpenAI Realtime) |

### 🔄 Orchestration & Control Flow
| Feature | Description |
|---------|-------------|
| **StateGraph** | Nodes, edges, conditional routing, subgraphs |
| **Dynamic Routing** | `Command(goto=..., update=...)` for inline routing |
| **Subgraph Streaming** | Nested graph execution with `CompiledGraph` returns |
| **MessageGraph** | High-level message-only graph wrapper |
| **RemoteGraph/GraphServer** | HTTP/gRPC graph execution & serving |
| **Dynamic Inline Routing** | `Command(goto=..., update=...)` |
| **MessageGraph** | High-level message-only wrapper |
| **All/ALL Selector** | Catch-all edge routing (`*`, `All`, `ALL`) |

### 🤖 LLM Providers (100+ Models)
| Provider | Models |
|----------|--------|
| **OpenAI** | GPT-4o, GPT-4o-mini, o1, o3-mini, Responses API |
| **Google** | Gemini 2.5 Flash/Pro, Gemini Live, Vertex AI |
| **Anthropic** | Claude 3.5 Sonnet, Haiku, Opus |
| **LiteLLM** | 100+ models (Ollama, Together, Bedrock, etc.) |
| **MultiProvider** | Prefix routing: `openai/`, `gemini/`, `ollama/`, `anthropic/` |
| **Fallbacks** | Exponential backoff, multi-provider retry |

### 🛠️ 50+ Built-in Tools
| Category | Tools |
|----------|-------|
| **Search** | `google_web_search`, `bing_search`, `brave_search`, `duckduckgo_search`, `serpapi_search`, `tavily_search`, `exa_search`, `multi_search` (7 providers + dedup) |
| **Browser** | `browser_navigate`, `browser_click`, `browser_fill`, `browser_extract`, `browser_screenshot`, `browser_close` |
| **Shell** | `shell_command` (safe, policy-guarded) |
| **Code** | `code_interpreter`, `CodeInterpreterTool` (sandboxed Python) |
| **Files** | `file_read`, `file_write`, `list_directory`, `edit_file`, `file_search` (semantic + incremental) |
| **Search** | `google_web_search`, `vertex_ai_search` |
| **Image** | `generate_image`, `dalle_generate`, `imagen_generate`, `sdxl_generate`, `midjourney_generate` |
| **Code** | `code_interpreter`, `CodeInterpreterTool` |
| **Shell** | `shell_command` (policy-guarded), `ShellTool` |
| **Files** | `file_read`, `file_write`, `list_directory`, `edit_file` (unified diff), `file_search` |
| **Calendar** | `calendar_create_event`, `calendar_update_event`, `calendar_delete_event`, `calendar_list_events` |
| **Scheduler** | `Scheduler`, `schedule_job`, `cancel_scheduled_job`, `list_scheduled_jobs` |
| **Subagents** | `start_subagent`, `SubagentManager`, `create_handoff_tool` |
| **Browser** | `browser_navigate`, `click`, `fill`, `extract`, `screenshot`, `close` |
| **Memory** | `memory_tool`, `create_memory_preload_node`, `make_agent_memory_tool` |
| **Image Gen** | `generate_image`, `dalle_generate`, `imagen_generate`, `sdxl_generate`, `midjourney_generate` |
| **Code** | `code_interpreter`, `CodeInterpreterTool` (sandboxed Python) |
| **Shell** | `shell_command` (policy-guarded), `ShellTool` (Docker/Local) |
| **Files** | `file_read`, `file_write`, `list_directory`, `edit_file` (unified diff), `file_search` |
| **Search** | 7 providers: Google, Bing, Brave, DuckDuckGo, SerpAPI, Tavily, Exa + `multi_search` |
| **Image Gen** | `generate_image` (unified), `dalle`, `imagen`, `sdxl`, `midjourney` |
| **Calendar** | `calendar_create_event`, `calendar_update_event`, `calendar_delete_event`, `calendar_list_events` |
| **Scheduler** | `Scheduler`, `schedule_job`, `cancel_scheduled_job`, `list_scheduled_jobs` |
| **Subagents** | `start_subagent`, `SubagentManager`, `create_handoff_tool` |
| **Browser** | `browser_navigate`, `click`, `fill`, `extract`, `screenshot`, `close` |
| **Memory** | `memory_tool`, `create_memory_preload_node`, `make_agent_memory_tool` |

### 💾 Persistence & Memory (3-Layer Architecture)
| Layer | Implementation |
|-------|----------------|
| **Working State** | `AgentState` (Pydantic, in-memory) |
| **Checkpointer** | `InMemoryCheckpointer`, `PgCheckpointer` (PostgreSQL + Redis), `SqliteCheckpointer` |
| **Vector Store** | `QdrantStore`, `Mem0Store`, `MemoryConfig`, `AgentMemoryConfig` |
| **Memory Tools** | `memory_tool`, `create_memory_preload_node`, `make_agent_memory_tool` |
| **Compaction** | `DynamicCompactionPolicy`, `ResponsesCompactionSession` |
| **Session Storage** | SQLite, Redis, MongoDB, SQLAlchemy, Dapr, Encrypted |

### 🌊 Streaming & Real-time
| Feature | Description |
|---------|-------------|
| **Event Streaming** | `astream_events()` - 15 event types (graph/node/tool start/end, tool calls, handoffs, interrupts) |
| **GraphRunStream v3** | SSE streaming, heartbeat keep-alive, sync wrapper |
| **Granularity** | `LOW`/`PARTIAL`/`FULL` response granularity |
| **Realtime Audio** | `AudioAgent` (Gemini Live, OpenAI Realtime, Azure, Local Whisper+TTS) |
| **Barge-in** | Audio interruption with transcript persistence |
| **WebRTC Streaming** | `RemoteDesktopStreamer` for VNC/WebRTC frame broadcast |

### 🛡️ Security & Guardrails
| Feature | Description |
|---------|-------------|
| **Input Guardrails** | PII detection, prompt injection prevention, length limits |
| **Output Guardrails** | JSON schema enforcement, blocked words, length limits |
| **Tool Guardrails** | `ToolInputGuardrail`/`ToolOutputGuardrail` with allow/deny/rate limits |
| **Policy Engine** | 9-priority RBAC (allow/deny/ask_user), predicates, tenant scoping |
| **RBAC** | 9 permissions (Viewer/Dev/Admin/Owner), tenant scoping |
| **Auth** | JWT (JWKS), mTLS, Token Introspection (RFC 7662), API Key Manager |
| **Secrets** | Vault, AWS/GCP/Azure Key Vault, Composite fallback chain |

### 🌐 Protocols & Communication
| Protocol | Implementation |
|----------|----------------|
| **A2A** | Server (Starlette, agent cards, streaming), Client (retries, pooling, TLS) |
| **ACP** | Client/Server (HTTP/in-memory), agent discovery, task delegation |
| **MCP** | Stdio/SSE/WebSocket transports, capability negotiation, 5-min tool cache |
| **A2A Server** | Starlette app, agent cards, task streaming, uvicorn |
| **ACP** | HTTP/in-memory transports, agent discovery, task delegation |

### 🛠️ Developer Experience & CLI
| Tool | Purpose |
|------|---------|
| **`alc` CLI** | `alc graph create/run/visualize/validate`, `alc agent create`, `alc tool list/test`, `alc config`, `alc deploy docker/helm/k8s` |
| **Graph Visualizer** | `compiled.generate_graph("mermaid" \| "graphviz" \| "html")` - renders in GitHub, Notion, browser |
| **Graph Visualizer** | Interactive HTML with browser preview |
| **Graph Debug** | `alc debug state/replay/trace` for debugging checkpoints and traces |

### 🖥️ Sandboxing & Isolation
| Backend | Capabilities |
|---------|-------------|
| **DockerSandbox** | GPU passthrough, resource limits, volume mounts, PTY |
| **K8sSandbox** | Pod lifecycle, exec, resource quotas, GPU |
| **FirecrackerSandbox** | Micro-VM, resource isolation |
| **LocalSandbox** | Unix PTY, subprocess |
| **Computer Use** | X11/Wayland/Headless/VNC/Remote Desktop, Accessibility Bridge, Action Verifier |
| **ShellTool** | Docker/Local environments, policy-guarded, workspace scoping |

### 📊 Observability & Observability
| Feature | Description |
|---------|-------------|
| **OpenTelemetry** | Auto-instrumentation decorators (`@trace_graph`, `@trace_node`, `@trace_llm`, `@trace_tool`) |
| **Prometheus** | 15+ metrics (requests, latency, tokens, errors, sessions) |
| **Structured Logging** | JSON + W3C traceparent propagation |
| **8 Span Types** | Agent, Generation, Function, Guardrail, Handoff, Custom, Task |
| **Tracing** | Nested spans, processors (OTLP, Datadog, Console) |

### 🧪 Testing & Evaluation
| Tool | Purpose |
|------|---------|
| `QuickTest` | One-liner single/multi-turn assertions |
| `TestAgent` | Full simulation with `MockLLM`, `MockToolRegistry` |
| `MockMCPClient` | MCP server mocking |
| `AgentEvaluator` | LLM-as-judge, trajectory matching, safety, hallucination |
| `QuickTest` | One-liner single/multi-turn assertions |
| `TestContext` | Isolated test environments |
| `UserSimulator` | AI-powered user simulation (personas, error injection) |
| `BatchSimulator` | Concurrent simulation runs |

### 🏭 Production Hardening (17 Phases Complete)
| Phase | Area | Status |
|-------|------|--------|
| 1 | Sandbox Hardening | ✅ Docker, K8s, Firecracker, RemoteFileSync |
| 2 | Computer Use | ✅ X11/Wayland/Headless/VNC/Remote Desktop/Accessibility |
| 3 | Shell Tool | ✅ Docker/Local environments, policy-guarded |
| 4 | Web Search | ✅ 7 providers + multi_search dedup |
| 5 | Image Gen | ✅ DALL-E, Imagen, SDXL, Midjourney |
| 5b | File Search | ✅ Semantic index, incremental, multi-repo |
| 6 | Realtime Audio | ✅ OpenAI/Azure Realtime, Local Whisper+TTS |
| 7 | Distributed Sync | ✅ yjs/Automerge CRDT, mDNS/Consul |
| 8 | MCP Transports | ✅ Stdio/SSE/WebSocket, capability negotiation |
| 9 | A2A/ACP | ✅ Server/Client, streaming, agent cards |
| 10 | Observability | ✅ Auto-instrumentation, 15 Prometheus metrics |
| 11 | Multi-tenancy | ✅ TenantRegistry, quotas, RBAC, isolation |
| 12 | AuthZ/AuthN | ✅ JWT/mTLS/Token Introspection, ASGI middleware |
| 13 | Deployment | ✅ Docker, Helm, K8s Operator, systemd |
| 14 | Secrets | ✅ Vault/AWS/GCP/Azure + Composite fallback |
| 15 | Rate Limiting | ✅ Redis sliding-window, priority-weighted |
| 16 | Audit/Compliance | ✅ AuditLogger, GDPR, DataLineage, OPA, SBOM |
| 17 | Developer UX | ✅ `alc` CLI, Graph Visualizer (Mermaid/Graphviz/HTML) |

---

## Quick Install

```bash
# Core
pip install alcyoneus

# Common stacks
pip install "alcyoneus[openai,google-genai,mcp,pg_checkpoint,qdrant]"
pip install "alcyoneus[realtime]"      # Audio agents
pip install "alcyoneus[browser]"       # Browser automation
pip install "alcyoneus[cli]"           # CLI tools
```

```bash
export OPENAI_API_KEY=sk-...    # or GEMINI_API_KEY, ANTHROPIC_API_KEY
```

---

## 30-Second Example

```python
from alcyoneus.core import StateGraph, Agent, ToolNode, START, END
from alcyoneus.storage.checkpointer import InMemoryCheckpointer
from alcyoneus.prebuilt.tools import safe_calculator, google_web_search

graph = StateGraph()
graph.add_node("agent", Agent(model="gemini/gemini-2.5-flash", tool_node="tools"))
graph.add_node("tools", ToolNode([safe_calculator, google_web_search]))
graph.add_edge("agent", "tools")
graph.add_edge("tools", "agent")
graph.set_entry_point("agent")

compiled = graph.compile(checkpointer=InMemoryCheckpointer())
result = compiled.invoke(
    {"messages": [{"role": "user", "content": "What's 25 * 4?"}]},
    config={"thread_id": "demo"}
)
```

---

## Documentation

| Topic | Link |
|-------|------|
| **Quickstart** | [docs/QUICKSTART.md](docs/QUICKSTART.md) |
| **All Imports** | [docs/IMPORTS.md](docs/IMPORTS.md) |
| **Core Patterns** | [docs/CORE_PATTERNS.md](docs/CORE_PATTERNS.md) |
| **Prebuilt Agents** | [docs/PREBUILT_AGENTS.md](docs/PREBUILT_AGENTS.md) |
| **Tools** | [docs/TOOLS.md](docs/TOOLS.md) |
| **Persistence** | [docs/PERSISTENCE.md](docs/PERSISTENCE.md) |
| **Streaming** | [docs/STREAMING.md](docs/STREAMING.md) |
| **Testing** | [docs/TESTING.md](docs/TESTING.md) |
| **Evaluation** | [docs/EVALUATION.md](docs/EVALUATION.md) |
| **Skills** | [docs/SKILLS.md](docs/SKILLS.md) |
| **Security** | [docs/SECURITY.md](docs/SECURITY.md) |
| **Protocols** | [docs/PROTOCOLS.md](docs/PROTOCOLS.md) |
| **Configuration** | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| **Deployment** | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| **Project Structure** | [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) |
| **Common Issues** | [docs/GOTCHAS.md](docs/GOTCHAS.md) |

---

## Examples

```bash
# Basic agent
python examples/react/react_sync.py

# MCP integration
pip install "alcyoneus[mcp]"
python examples/react-mcp/server.py  # terminal 1
python examples/react-mcp/react-mcp.py  # terminal 2

# Streaming
python examples/react_stream/stream_react_agent.py

# Realtime audio
pip install "alcyoneus[realtime]"
export GEMINI_API_KEY=...
python examples/realtime/audio_agent_file.py
```

---

## Testing & Quality

```bash
# Run all tests (3159 passing)
pytest tests/ -q

# Lint
ruff check . && ruff format .

# Type check
mypy alcyoneus/
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Links

- **PyPI Package**: https://pypi.org/project/alcyoneus/
- **GitHub Repository**: https://github.com/sainibhaowal/Alcyoneus-OS
- **Documentation**: [docs/QUICKSTART.md](docs/QUICKSTART.md)
- **Examples**: [examples/](examples/)
- **License**: [LICENSE](LICENSE)

---

**Alcyoneus OS** — Build intelligent agents with confidence.