# Skills — Dynamic Capability Injection

> **Add capabilities to agents at runtime without code changes.**

---

## Overview

Skills let you inject capabilities into agents dynamically — no code changes, no redeploys.

```
Skill File (YAML) → SkillsRegistry → Agent → LLM calls set_skill()
```

---

## 1. Skill File Format

Create `skills/sql_analysis.yaml`:

```yaml
name: sql_analysis
description: "Analyze data using SQL queries"
version: "1.0"
trigger:
  type: "keyword"
  keywords: ["analyze", "query", "sql", "database"]
instructions: |
  You have access to a PostgreSQL database with the following schema:
  
  - users(id, name, email, created_at)
  - orders(id, user_id, total, status, created_at)
  - products(id, name, price, category)
  
  Use the `sql_query` tool to run SELECT queries only.
  Always explain your query before executing.
  Return results in a clear, formatted table.

tools:
  - sql_query
```

### Skill Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | ✅ | Unique identifier |
| `description` | ✅ | What the skill does |
| `version` | ❌ | Semver (default: "1.0") |
| `trigger` | ✅ | When to auto-activate |
| `instructions` | ✅ | System prompt for skill |
| `tools` | ❌ | Tool names to enable |
| `params` | ❌ | Schema for skill parameters |

### Trigger Types

```yaml
# Keyword-based
trigger:
  type: "keyword"
  keywords: ["analyze", "query", "data"]

# Pattern-based (regex)
trigger:
  type: "pattern"
  pattern: "analyze\s+\w+"

# Always available (manual activation)
trigger:
  type: "manual"

# Conditional
trigger:
  type: "condition"
  condition: "state.user_role == 'admin'"
```

---

## 2. Register Skills

```python
from alcyoneus.core.skills import SkillConfig, SkillsRegistry

# Load from directory
skills = SkillConfig(
    skills_dir="./skills",  # directory with .yaml files
    mode="on-demand",       # or "session"
)

# Or programmatically
registry = SkillsRegistry()
registry.register_skill("sql_analysis", {
    "name": "sql_analysis",
    "description": "Analyze data with SQL",
    "trigger": {"type": "keyword", "keywords": ["analyze", "sql"]},
    "instructions": "You can run SQL queries...",
    "tools": ["sql_query"],
})
```

---

## 3. Use in Agent

```python
from alcyoneus.core import Agent
from alcyoneus.core.skills import SkillConfig

skills = SkillConfig(skills_dir="./skills", mode="on-demand")

agent = Agent(
    model="google/gemini-2.5-flash",
    skills=skills,
    # Agent now has access to `set_skill()` tool
)

# In graph
graph.add_node("agent", agent)
```

---

## 4. Skill Modes

### On-Demand Mode (Default)

```python
skills = SkillConfig(
    skills_dir="./skills",
    mode="on-demand",  # LLM decides when to activate
)

# LLM calls set_skill() when trigger matches
# Agent: "I'll analyze that data for you."
# → calls set_skill("sql_analysis")
# → skill instructions + tools injected
# → agent can now use sql_query tool
```

### Session Mode (Pre-loaded)

```python
skills = SkillConfig(
    skills_dir="./skills",
    mode="session",
    preload=["sql_analysis", "data_export"],  # always loaded
)

# Skills active from graph start
# No set_skill() calls needed
```

---

## 5. Using Skills in Agent

```python
# Agent automatically gets set_skill tool
agent = Agent(
    model="google/gemini-2.5-flash",
    skills=skills,
)

# In node
async def analyze_data(state: MyState) -> MyState:
    # Agent can call set_skill("skill_name") when needed
    # Skill instructions + tools become available
    return state
```

### Manual Skill Control

```python
# In node, manually activate
async def setup_analysis(state: MyState) -> MyState:
    # Inject skill manually
    state.active_skills = ["sql_analysis"]
    return state

# Or from LLM (it calls set_skill tool)
# No code needed - LLM decides when to activate
```

---

## 6. Skill Parameters

```yaml
# skills/data_export.yaml
name: data_export
description: "Export data to various formats"
params:
  format:
    type: string
    enum: ["csv", "json", "xlsx", "parquet"]
    default: "csv"
  include_headers:
    type: boolean
    default: true
instructions: |
  Export data using the specified format.
  Use the `export_data` tool with format parameter.
tools:
  - export_data
```

```python
# Agent receives params when skill activated
# LLM calls: set_skill("data_export", {"format": "json"})
```

---

## 6. Skill Discovery

```python
from alcyoneus.core.skills import SkillsRegistry

registry = SkillsRegistry(skills)

# List all skills
skills_list = registry.list_skills()
# [{"name": "sql_analysis", "description": "..."}, ...]

# Get skill details
skill = registry.get_skill("sql_analysis")
# {"name": "sql_analysis", "description": "...", "tools": ["sql_query"], ...}

# Check if skill exists
if registry.has_skill("sql_analysis"):
    ...
```

---

## 7. Skill File Organization

```
project/
├── skills/
│   ├── sql_analysis.yaml
│   ├── data_export.yaml
│   ├── report_generation.yaml
│   ├── api_integration.yaml
│   └── code_review.yaml
```

---

## 8. Hot Reload (Development)

```python
skills = SkillConfig(
    skills_dir="./skills",
    mode="on-demand",
    watch=True,  # auto-reload on file change
)
```

---

## Best Practices

| Practice | Why |
|----------|-----|
| One skill per file | Easy to manage, version, test |
| Clear trigger keywords | LLM activates correctly |
| Limit tools per skill | Reduces confusion |
| Test skills independently | Use TestAgent with skill |
| Version skills | Track changes, rollback |
| Document parameters | LLM uses correctly |

---

## Example: Complete Skill

```yaml
# skills/customer_lookup.yaml
name: customer_lookup
description: "Look up customer details by ID or email"
version: "1.1"
trigger:
  type: "keyword"
  keywords: ["customer", "lookup", "find user", "user details"]
params:
  identifier:
    type: string
    description: "Customer ID or email"
    required: true
  include_orders:
    type: boolean
    default: false
instructions: |
  You can look up customer information using the `customer_lookup` tool.
  Provide the identifier (ID or email) and optionally include order history.
  Return results in a clear format.
tools:
  - customer_lookup
```