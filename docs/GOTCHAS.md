# Gotchas & Common Issues

> **Save hours of debugging — common pitfalls and fixes.**

---

## Import Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: alcyoneus.graph` | Old import path | Use `from alcyoneus.core import StateGraph` |
| `ModuleNotFoundError: alcyoneus.state` | Old import path | Use `from alcyoneus.core import AgentState` |
| `ModuleNotFoundError: alcyoneus.checkpointer` | Old import path | Use `from alcyoneus.storage.checkpointer import ...` |
| `ModuleNotFoundError: alcyoneus.skills` | Old import path | Use `from alcyoneus.core.skills import ...` |
| `ModuleNotFoundError: alcyoneus.evaluation` | Old import path | Use `from alcyoneus.qa.evaluation import ...` |
| `ModuleNotFoundError: alcyoneus.testing` | Old import path | Use `from alcyoneus.qa.testing import ...` |
| `ModuleNotFoundError: alcyoneus.adapters` | Old import path | Use `from alcyoneus.runtime.adapters.llm import ...` |
| `ModuleNotFoundError: alcyoneus.publisher` | Old import path | Use `from alcyoneus.runtime.publisher import ...` |

---

## State & Messages

| Issue | Cause | Fix |
|-------|-------|-----|
| `Message.from_text()` doesn't exist | Old API | Use `Message.text_message("content")` |
| `Message.content` is list, not string | New format | Use `msg.content[0].text` or `msg.content[0].get("text")` |
| State not persisting | Missing `thread_id` | Pass `config={"thread_id": "..."}` |
| State not updating | Forgot to return state | Always `return state` in nodes |
| `add_messages` not merging | Wrong reducer | Use `add_messages` from `alcyoneus.core.state` |

```python
# ❌ Wrong
msg = Message.from_text("hello")

# ✅ Correct
msg = Message.text_message("hello")
# or
msg = Message(role="user", content=[TextBlock(text="hello")])
```

---

## Graph & Compilation

| Issue | Cause | Fix |
|-------|-------|-----|
| Graph won't compile | Missing `START`/`END` | Import from `alcyoneus.core` or `alcyoneus.utils.constants` |
| `interrupt_before` not working | Wrong node name | Use exact node name from `graph.add_node()` |
| Recursion error | Infinite loop | Check conditional edges, add `recursion_limit` |
| Graph won't serialize | Non-JSON-serializable in state | Use Pydantic models, avoid functions in state |
| Nodes running twice | Duplicate edges | Check `add_edge` calls, use `graph.get_graph()` to debug |

---

## Tools

| Issue | Cause | Fix |
|-------|-------|-----|
| Tool not called | Wrong schema | Check `@tool` decorator, validate schema |
| `ToolNode(functions=[...])` error | Wrong param | Use `ToolNode(tools=[...])` |
| Tool not found | Wrong name | Match exact function name |
| Tool args wrong | Schema mismatch | Check `@tool` signature matches call |
| Tool timeout | Long running | Increase `ToolExecutionPolicy.timeout` |
| Tool results not in state | Wrong state field | Use `ToolResultBlock` in state messages |

```python
# ❌ Wrong
ToolNode(functions=[my_tool])

# ✅ Correct
ToolNode(tools=[my_tool])
```

---

## LLM / Model

| Issue | Cause | Fix |
|-------|-------|-----|
| Model not found | Wrong string | Use `google/gemini-2.5-flash` not `gemini-2.5-flash` |
| Provider not detected | No prefix | Use `openai/gpt-4o` or `google/gemini-2.5-flash` |
| Vertex AI not working | Wrong config | Set `use_vertex_ai=True` in `Agent` |
| Rate limited | No backoff | Add `RetryConfig` to `Agent` |
| Fallback not working | Wrong list | Use `fallback_models=["gpt-4o", "gpt-4o-mini"]` |

---

## Persistence

| Issue | Cause | Fix |
|-------|-------|-----|
| State not saving | No `thread_id` | Pass `config={"thread_id": "..."}` |
| Can't resume | Wrong `thread_id` | Use exact same `thread_id` |
| Checkpoint huge | Large state | Reduce state size, use `store` for large data |
| `PgCheckpointer` fails | Missing tables | Run migrations, check `conn_str` |
| Redis connection fails | Wrong URL | Check `redis_url` format |

```python
# ❌ Wrong
compiled.invoke(input_data)

# ✅ Correct (with persistence)
compiled.invoke(input_data, config={"thread_id": "thread_123"})
```

---

## Streaming

| Issue | Cause | Fix |
|-------|-------|-----|
| `astream` not yielding | Not async | Use `async for` in async function |
| Events not streaming | Wrong method | Use `astream_events()` not `stream()` |
| Events duplicated | Multiple yields | Check for duplicate `add_edge` |
| UI not updating | Sync context | Use `asyncio.run()` or run in async |

---

## Testing

| Issue | Cause | Fix |
|-------|-------|-----|
| `QuickTest` fails | Wrong expected | Use exact expected string |
| `TestAgent` mock fails | Wrong mock | Match exact tool names/args |
| `MockMCPClient` not working | Wrong setup | Use `add_tool()` before running |
| Tests slow | Live LLM calls | Use `MockLLM` and `MockToolRegistry` |

---

## Evaluation

| Issue | Cause | Fix |
|-------|-------|-----|
| Evaluator hangs | LLM judge timeout | Reduce `num_runs`, increase timeout |
| Criteria not matching | Wrong name | Match exact criterion name |
| Reporter fails | Missing deps | Install `pip install "alcyoneus[eval]"` |

---

## Deployment

| Issue | Cause | Fix |
|-------|-------|-----|
| `pre-commit` fails | Hook env | Run `pre-commit install` in venv |
| Docker build fails | Missing deps | Add system deps to Dockerfile |
| K8s pod crashes | OOM | Increase memory limits |
| Health check fails | Wrong path | Check `/health` endpoint |
| Secrets not loading | Wrong env | Check `.env` and secret names |

---

## MyPy / Type Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `arg-type` | Wrong type | Add type annotations |
| `union-attr` | Optional not handled | Use `Optional[T]` and check `None` |
| `attr-defined` | Dynamic attr | Add `# type: ignore` or fix type |
| `override` mismatch | Signature drift | Match parent signature exactly |
| `call-overload` | Wrong args | Match overload signature |

```python
# ❌ Wrong
def func(x: dict) -> str: ...

# ✅ Correct
def func(x: dict[str, Any]) -> str: ...
```

---

## Performance

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Slow invoke | No checkpointer | Add checkpointer |
| High memory | Large state | Use `store` for large data |
| Slow tools | No timeout | Add tool timeouts |
| High CPU | Recursion | Add `recursion_limit` |
| Slow startup | Heavy imports | Lazy import in nodes |

---

## Common Error Messages

| Error | Meaning | Fix |
|-------|---------|-----|
| `GraphRecursionError` | Infinite loop | Check conditional edges |
| `NodeError` | Node raised | Check node function |
| `SchemaVersionError` | State version | Migrate state or reset |
| `SerializationError` | Can't pickle | Use JSON-serializable state |
| `StorageError` | DB error | Check DB connection |
| `TransientStorageError` | Temporary | Retry with backoff |

---

## Quick Debug Checklist

1. **Import errors?** → Check import paths (use `alcyoneus.core.*`)
2. **State not persisting?** → Add `thread_id` to config
3. **Tool not called?** → Check `@tool` decorator and schema
4. **Streaming not working?** → Use `astream_events()` in async
5. **Mypy errors?** → Add module to `pyproject.toml` overrides
6. **Tests flaky?** → Use `MockLLM` and `MockToolRegistry`
7. **Slow performance?** → Check checkpointer, add timeouts
7. **Import errors in examples?** → Examples use old paths; use this guide's imports

---

## Debugging Commands

```bash
# Check ruff
ruff check .

# Check mypy
mypy alcyoneus/

# Run tests with output
pytest tests/ -v -s

# Run with coverage
pytest tests/ --cov=alcyoneus --cov-report=term-missing

# Check graph
python -c "from myapp.graphs import g; print(g.get_graph())"

# Debug checkpoint
python -c "from alcyoneus.storage.checkpointer import InMemoryCheckpointer; c=InMemoryCheckpointer(); print(c.list())"
```