# Quick Decision Matrix

> **Instant answers: "I need X → use this"**

---

## By Goal

| I need to... | Use This |
|--------------|----------|
| Build a simple LLM chat | `Agent(model="...")` |
| Multi-step reasoning with tools | `ReactAgent` |
| Answer questions from documents | `RAGAgent` + `QdrantStore` |
| Multiple agents collaborating | `SwarmAgent` |
| Hierarchical team with supervisor | `SupervisorTeamAgent` |
| Guaranteed JSON output | `StructuredOutputAgent` |
| Plan → Execute → Self-correct | `PlanActReflectAgent` |
| Resume after crash/restart | `PgCheckpointer` |
| Long-term memory across sessions | `QdrantStore` / `Mem0Store` |
| Human approval step | `interrupt_before=["node"]` |
| Real-time streaming UI | `astream_events()` |
| Unit test without LLM | `QuickTest` / `TestAgent` |
| CI/CD quality gates | `AgentEvaluator` + `EvalSet` |
| Dynamic skill injection | `SkillConfig` + `SkillsRegistry` |
| Input validation | `InputGuardrail` |
| Output validation | `OutputGuardrail` |
| Tool access control | `ToolGuardrail` |
| Access control (RBAC) | `PolicyEngine` |
| A2A protocol (task-based) | `a2a.A2AClient` / `A2AServer` |
| ACP protocol (conversational) | `acp.ACPClient` / `ACPServer` |
| Custom tool | `@tool` decorator |
| MCP integration | `MCPClient` + `ToolNode` |

---

## By Import

| Need | Import |
|------|--------|
| Build graph | `from alcyoneus.core import StateGraph, START, END` |
| LLM agent | `from alcyoneus.core import Agent` |
| State schema | `from alcyoneus.core import AgentState` |
| Messages | `from alcyoneus.core import Message, TextBlock` |
| Tools | `from alcyoneus.prebuilt.tools import safe_calculator, fetch_url` |
| Checkpointer | `from alcyoneus.storage.checkpointer import InMemoryCheckpointer, PgCheckpointer` |
| Vector store | `from alcyoneus.storage.store import QdrantStore, Mem0Store` |
| Prebuilt agents | `from alcyoneus.prebuilt.agent import ReactAgent, RAGAgent` |
| Testing | `from alcyoneus.qa.testing import TestAgent, QuickTest` |
| Evaluation | `from alcyoneus.qa.evaluation import AgentEvaluator, EvalSet` |
| Custom tool | `from alcyoneus.utils import tool` |
| Callbacks | `from alcyoneus.utils.callbacks import CallbackManager` |
| Custom tool | `from alcyoneus.utils import tool` |
| Constants | `from alcyoneus.utils.constants import START, END` |

---

## By Complexity

| Level | Components |
|-------|------------|
| **Beginner** | `Agent`, `StateGraph`, `InMemoryCheckpointer` |
| **Intermediate** | `ReactAgent`, `PgCheckpointer`, `QdrantStore`, tools |
| **Advanced** | `SwarmAgent`, `SupervisorTeamAgent`, skills, guardrails, policies |
| **Expert** | Multi-agent, A2A/ACP, custom converters, custom checkpointers |

---

## By Use Case

| Use Case | Recommended Stack |
|----------|-------------------|
| Chatbot | `Agent` + `InMemoryCheckpointer` |
| Customer support | `ReactAgent` + `PgCheckpointer` + `QdrantStore` |
| Document Q&A | `RAGAgent` + `QdrantStore` |
| Code assistant | `ReactAgent` + `code_interpreter` + `file_search` |
| Data analysis | `ReactAgent` + `safe_calculator` + `file_search` |
| Multi-agent research | `SwarmAgent` / `SupervisorTeamAgent` |
| Structured data extraction | `StructuredOutputAgent` |
| Planning tasks | `PlanActReflectAgent` |
| Document processing | `Agent` + `multimodal_config` + `MediaConfig` |
| Scheduled tasks | `Scheduler` + `schedule_job` |
| Human-in-the-loop | `interrupt_before=["node"]` |
| Multi-tenant | `PgCheckpointer` + `PolicyEngine` |
| Agent marketplace | `a2a.A2AClient` / `A2AServer` |

---

## By Team Size

| Team | Start With |
|--------|------------|
| Solo / 1-2 devs | `Agent` + `StateGraph` + `InMemoryCheckpointer` |
| Small (3-5) | `ReactAgent` + `PgCheckpointer` + `QdrantStore` + `QuickTest` |
| Medium (6-15) | Prebuilt agents + `AgentEvaluator` + `PgCheckpointer` + CI |
| Large (15+) | Full stack: skills, guardrails, policies, A2A, multi-region |

---

## By Industry

| Industry | Key Features |
|----------|--------------|
| **SaaS** | Multi-tenant, PgCheckpointer, guardrails, eval |
| **Finance** | Audit trails, PgCheckpointer, guardrails, policies |
| **Healthcare** | HIPAA compliance, encryption, audit, guardrails |
| **E-commerce** | RAGAgent, SwarmAgent, streaming, eval |
| **DevTools** | code_interpreter, structured output, skills |
| **Support** | ReactAgent, streaming, human-in-loop, eval |

---

## By Maturity

| Stage | Focus |
|-------|-------|
| **Prototype** | `Agent` + `StateGraph` + `InMemoryCheckpointer` |
| **MVP** | `ReactAgent` + `PgCheckpointer` + `QuickTest` |
| **Launch** | Prebuilt agents + `PgCheckpointer` + `QdrantStore` + `AgentEvaluator` |
| **Scale** | Multi-agent, skills, guardrails, policies, A2A, K8s |
| **Enterprise** | Multi-region, audit, compliance, custom checkpointers |

---

## One-Liners

```python
# Simplest possible agent
Agent(model="google/gemini-2.5-flash")

# With tools
Agent(model="...", tools=[safe_calculator, fetch_url])

# With persistence
graph.compile(checkpointer=InMemoryCheckpointer())

# With vector memory
graph.compile(store=QdrantStore(...))

# With human approval
graph.compile(interrupt_before=["risky_node"])

# With streaming
async for event in compiled.astream_events(input_data): ...

# With testing
QuickTest.single_turn("expected").run(graph)

# With evaluation
AgentEvaluator(compiled, config).evaluate(eval_set)
```