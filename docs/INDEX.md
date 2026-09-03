# Alcyoneus OS Documentation

> **Complete reference for building production AI workflows with Alcyoneus OS.**

## Quick Navigation

| Topic | File | Description |
|-------|------|-------------|
| **Quick Start** | [QUICKSTART.md](QUICKSTART.md) | Get running in 5 minutes |
| **All Imports** | [IMPORTS.md](IMPORTS.md) | Complete import reference |
| **Core Patterns** | [CORE_PATTERNS.md](CORE_PATTERNS.md) | State, nodes, graphs, compilation |
| **Prebuilt Agents** | [PREBUILT_AGENTS.md](PREBUILT_AGENTS.md) | ReactAgent, RAGAgent, Swarm, etc. |
| **Tools** | [TOOLS.md](TOOLS.md) | Prebuilt & custom tools |
| **Persistence** | [PERSISTENCE.md](PERSISTENCE.md) | Checkpointers, vector stores, media |
| **Streaming** | [STREAMING.md](STREAMING.md) | Real-time event streaming |
| **Testing** | [TESTING.md](TESTING.md) | QuickTest, TestAgent, mocks |
| **Evaluation** | [EVALUATION.md](EVALUATION.md) | AgentEvaluator, criteria, simulators |
| **Skills** | [SKILLS.md](SKILLS.md) | Dynamic capability injection |
| **Security** | [SECURITY.md](SECURITY.md) | Guardrails, policies, policies |
| **Protocols** | [PROTOCOLS.md](PROTOCOLS.md) | A2A, ACP |
| **Configuration** | [CONFIGURATION.md](CONFIGURATION.md) | All compile/runtime options |
| **Deployment** | [DEPLOYMENT.md](DEPLOYMENT.md) | Docker, K8s, env vars |
| **Quick Decision** | [QUICK_DECISION.md](QUICK_DECISION.md) | Feature → import mapping |
| **Project Structure** | [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | Recommended file layout |
| **Gotchas** | [GOTCHAS.md](GOTCHAS.md) | Common issues & fixes |

---

## One-Line Mental Model

> **Build a flowchart of Python functions → Compile → Run.**

```
StateGraph → add_node() → add_edge() → compile() → invoke()
```

---

## Quick Links by Use Case

| I want to... | Start Here |
|--------------|------------|
| Build my first graph | [QUICKSTART.md](QUICKSTART.md) |
| See all imports | [IMPORTS.md](IMPORTS.md) |
| Write custom nodes | [CORE_PATTERNS.md](CORE_PATTERNS.md#2-write-nodes-plain-functions--your-logic) |
| Use LLM + tools | [PREBUILT_AGENTS.md](PREBUILT_AGENTS.md) |
| Add persistence | [PERSISTENCE.md](PERSISTENCE.md) |
| Add streaming UI | [STREAMING.md](STREAMING.md) |
| Write tests | [TESTING.md](TESTING.md) |
| Add eval/CI | [EVALUATION.md](EVALUATION.md) |
| Deploy to prod | [DEPLOYMENT.md](DEPLOYMENT.md) |

---

## Version

**Alcyoneus OS v1.1.0** — Apache 2.0 Licensed — Package: `pip install alcyoneus`