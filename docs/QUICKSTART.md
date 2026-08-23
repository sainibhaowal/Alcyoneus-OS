# Quick Start — Alcyoneus OS

> **Get running in 5 minutes.**

---

## Install

```bash
pip install alcyoneus
# With common extras:
pip install "alcyoneus[google-genai,openai,mcp,pg_checkpoint]"
```

---

## Minimal Working Example

```python
import alcyoneus as alc
from alcyoneus.core import StateGraph, Agent, START, END
from alcyoneus.storage.checkpointer import InMemoryCheckpointer

# 1. Define state (your data schema)
class MyState(alc.AgentState):
    user_name: str
    answer: str = ""

# 2. Write a node (plain Python function)
async def greet(state: MyState) -> MyState:
    state.answer = f"Hello, {state.user_name}!"
    return state

# 3. Build the graph
graph = StateGraph(MyState)
graph.add_node("greet", greet)
graph.add_edge(START, "greet")
graph.add_edge("greet", END)

# 4. Compile with persistence
compiled = graph.compile(checkpointer=InMemoryCheckpointer())

# 5. Run
result = compiled.invoke({"user_name": "Alice"})
print(result["answer"])  # "Hello, Alice!"
```

---

## With LLM + Tools

```python
from alcyoneus.core import Agent
from alcyoneus.prebuilt.tools import safe_calculator, fetch_url

# LLM agent with tools
agent = Agent(
    model="google/gemini-2.5-flash",
    system_prompt="You are a helpful assistant.",
    tools=[safe_calculator, fetch_url],
)

# Use in graph
graph = StateGraph(alc.AgentState)
graph.add_node("agent", agent)
graph.add_edge(START, "agent")
graph.add_edge("agent", END)

compiled = graph.compile()
result = compiled.invoke({
    "messages": [{"role": "user", "content": "What's 25 * 4 + fetch https://api.example.com/data?"}]
})
```

---

## Key Concepts in 30 Seconds

| Concept | What It Is |
|---------|------------|
| **StateGraph** | Flowchart builder |
| **AgentState** | Your data schema (extend it) |
| **Node** | Plain Python function `state -> state` |
| **Edge** | Connection between nodes |
| **CompiledGraph** | Runnable, compiled version |
| **Checkpointer** | Saves state for resume/audit |

---

## Next Steps

| Need | Read |
|------|------|
| All imports | [IMPORTS.md](IMPORTS.md) |
| Write custom nodes/state | [CORE_PATTERNS.md](CORE_PATTERNS.md) |
| Use LLM agents | [PREBUILT_AGENTS.md](PREBUILT_AGENTS.md) |
| Add tools | [TOOLS.md](TOOLS.md) |
| Add persistence | [PERSISTENCE.md](PERSISTENCE.md) |
| Add streaming | [STREAMING.md](STREAMING.md) |
| Write tests | [TESTING.md](TESTING.md) |
| Deploy to prod | [DEPLOYMENT.md](DEPLOYMENT.md) |