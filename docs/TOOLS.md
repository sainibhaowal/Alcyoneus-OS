# Tools — Prebuilt & Custom

> **All tooling capabilities in Alcyoneus OS.**

---

## Prebuilt Tools (Import & Use)

```python
from alcyoneus.prebuilt.tools import (
    # Core
    safe_calculator, fetch_url, file_search,
    # Memory
    memory_tool, create_memory_preload_node,
    # Handoff
    create_handoff_tool, is_handoff_tool,
    # Files
    file_read, file_write, list_directory,
    # Shell
    shell_command, ShellPolicy, ShellPolicyError,
    # Code
    code_interpreter, CodeInterpreterTool,
    # Search
    google_web_search, bing_search, brave_search,
    duckduckgo_search, serpapi_search, tavily_search, exa_search,
    multi_search,
    # Image
    generate_image, dalle_generate, imagen_generate, midjourney_generate, sdxl_generate,
    create_image_generator, ImageProvider,
    # Scheduler
    Scheduler, schedule_job, cancel_scheduled_job, list_scheduled_jobs,
    # Subagents
    start_subagent, SubagentManager,
    # Browser
    browser_navigate, browser_click, browser_fill, browser_extract, browser_screenshot, browser_close,
    BrowserController, BrowserPolicy,
    # Calendar
    calendar_create_event, calendar_update_event, calendar_delete_event, calendar_list_events,
    CalendarEvent, CalendarProvider, InMemoryCalendarProvider, HttpCalendarProvider,
    # Human
    ask_question, HumanQuestionBroker,
    # Finish
    finish,
    # Custom
    CustomTool, ToolCaller,
)
```

---

## Core Tools

### Calculator

```python
from alcyoneus.prebuilt.tools import safe_calculator

# Safe evaluation (no eval())
result = safe_calculator("2 + 3 * 4")  # "14"
result = safe_calculator("(10 + 5) / 3")  # "5.0"
```

### Web Fetch

```python
from alcyoneus.prebuilt.tools import fetch_url

result = await fetch_url("https://api.example.com/data")
# Returns: {"content": "...", "status": 200, "headers": {...}}
```

### File Search (RAG)

```python
from alcyoneus.prebuilt.tools import file_search, file_search_build_index

# Build index
await file_search_build_index("/path/to/docs")

# Search
results = await file_search("API documentation", top_k=5)
# Returns: [{"path": "...", "content": "...", "score": 0.95}, ...]
```

---

## Memory Tools

```python
from alcyoneus.prebuilt.tools import memory_tool, create_memory_preload_node

# Memory tool (read/write long-term memory)
agent = Agent(model="...", tools=[memory_tool])

# Preload memory at graph start
preload_node = create_memory_preload_node(
    query="user preferences",
    namespace="user_{user_id}",
)
graph.add_node("preload_memory", preload_node)
```

---

## Shell Tools (with Policy)

```python
from alcyoneus.prebuilt.tools import shell_command, ShellPolicy

# Restrictive policy
policy = ShellPolicy(
    allowed_commands=["ls", "cat", "grep", "python", "pip"],
    blocked_commands=["rm", "sudo", "chmod", "chown"],
    allowed_paths=["/workspace", "/tmp"],
    timeout=30,
)

tool = shell_command(policy=policy)

# In agent
agent = Agent(model="...", tools=[shell_command(policy=policy)])
```

**Policy Options:**

| Option | Type | Description |
|--------|------|-------------|
| `allowed_commands` | List[str] | Commands allowed (default: all) |
| `blocked_commands` | List[str] | Commands blocked (default: none) |
| `allowed_paths` | List[str] | Paths allowed (default: all) |
| `blocked_paths` | List[str] | Paths blocked (default: none) |
| `timeout` | int | Seconds (default: 30) |
| `env` | dict | Environment variables |

---

## Code Interpreter

```python
from alcyoneus.prebuilt.tools import code_interpreter, CodeInterpreterTool

tool = code_interpreter  # or CodeInterpreterTool()

# In agent
agent = Agent(model="...", tools=[code_interpreter])

# Executes Python code safely in sandbox
```

---

## Search Tools

```python
from alcyoneus.prebuilt.tools import (
    google_web_search, bing_search, brave_search,
    duckduckgo_search, serpapi_search, tavily_search, exa_search,
    multi_search,
)

# Single provider
results = await google_web_search("Alcyoneus OS", max_results=5)

# Multi-provider (deduplicated)
results = await multi_search("AI agents", providers=["google", "bing", "brave"], max_results=10)
```

---

## Image Generation

```python
from alcyoneus.prebuilt.tools import (
    generate_image, dalle_generate, imagen_generate, midjourney_generate, sdxl_generate,
    create_image_generator, ImageProvider,
)

# Simple
images = await generate_image("A sunset over mountains", size="1024x1024", count=2)

# Specific provider
images = await dalle_generate("A cat in space", size="1024x1024")
images = await imagen_generate("A futuristic city", count=4)

# Custom provider
from alcyoneus.prebuilt.tools import ImageProvider
class MyImageProvider(ImageProvider):
    async def generate(self, prompt: str, **kwargs) -> List[str]:
        ...

provider = MyImageProvider()
images = await provider.generate("Custom prompt")
```

---

## Scheduler

```python
from alcyoneus.prebuilt.tools import Scheduler, schedule_job, cancel_scheduled_job

scheduler = Scheduler()

# Schedule recurring job
job_id = await schedule_job(
    "daily_report",
    cron="0 9 * * *",  # 9 AM daily
    func=generate_daily_report,
    args=("team_a",),
)

# Cancel
await cancel_scheduled_job(job_id)

# List jobs
jobs = await list_scheduled_jobs()
```

---

## Custom Tools (Write Your Own)

### Basic Tool

```python
from alcyoneus.utils import tool

@tool
def lookup_customer(customer_id: str) -> dict:
    """Look up customer by ID."""
    return db.customers.find_one(customer_id)
```

### Tool with State Injection

```python
from alcyoneus.utils import tool
from alcyoneus.core import AgentState

@tool
def update_order_total(
    order_id: str,
    amount: float,
    state: AgentState,  # injected automatically
) -> dict:
    state.total += amount
    return {"new_total": state.total}
```

### Tool with Config Injection

```python
@tool
async def call_external_api(
    endpoint: str,
    payload: dict,
    config: dict,  # runtime config from compile config
) -> dict:
    api_key = config.get("api_key")
    return await http.post(endpoint, json=payload, headers={"Authorization": api_key})
```

### Tool with Handoff

```python
from alcyoneus.prebuilt.tools import create_handoff_tool
from alcyoneus.prebuilt.agent import ReactAgent

researcher = ReactAgent(model="...", tools=[...], name="researcher")
handoff_to_researcher = create_handoff_tool(researcher, name="researcher")

# Agent can call handoff_to_researcher to delegate
agent = Agent(model="...", tools=[handoff_to_researcher])
```

### Async Tool with Error Handling

```python
@tool
async def robust_api_call(url: str, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            return await http.get(url)
        except Exception as e:
            if attempt == retries - 1:
                return {"error": str(e)}
            await asyncio.sleep(2 ** attempt)  # exponential backoff
```

---

## Tool Configuration in Agent

```python
from alcyoneus.core import Agent

agent = Agent(
    model="google/gemini-2.5-flash",
    tools=[
        safe_calculator,
        fetch_url,
        my_custom_tool,
    ],
    tool_node=ToolNode(tools=[...]),  # optional custom ToolNode
    tool_node_name="tools",
    max_tool_iterations=10,
    tool_choice="auto",  # "auto" | "any" | "none" | specific tool name
)
```

---

## Tool Node (Advanced)

```python
from alcyoneus.core import ToolNode
from alcyoneus.core.graph.tool_node.policy import ToolExecutionPolicy

tool_node = ToolNode(
    tools=[safe_calculator, fetch_url],
    policy=ToolExecutionPolicy(
        timeout=30,
        max_retries=3,
        retry_on_failure=True,
    ),
    client=None,  # optional MCP client
)

graph.add_node("tools", tool_node)
```

---

## Tool Schema (Auto-generated)

```python
from alcyoneus.utils.validators import validate_tool_schema

@tool
def my_tool(name: str, count: int = 1) -> dict:
    """Does something."""
    return {"result": name * count}

schema = validate_tool_schema(my_tool)
# Returns OpenAI-compatible function schema
```