# CLI Reference — Alcyoneus OS

> **Complete command reference for the `alcyoneus` CLI toolkit.**

---

## Overview

| Command | Purpose |
|---------|---------|
| `alcyoneus init` | Scaffold a new agent project interactively |
| `alcyoneus doctor` | Run system health diagnostics |
| `alcyoneus version` | Display version information |
| `alcyoneus graph inspect` | Inspect graph structure from a Python file |
| `alcyoneus graph validate` | Validate a graph compiles successfully |
| `alcyoneus agent list` | List available agent architectures |
| `alcyoneus agent create` | Generate an agent template |
| `alcyoneus tool list` | List built-in tools |
| `alcyoneus completion` | Generate shell auto-completion scripts |

All data-returning commands support `--json` and `--yaml` for CI/CD pipelines.

---

## Installation

```bash
pip install "alcyoneus[cli]"

# Or run via module
python -m alcyoneus.cli
```

---

## 1. `alcyoneus init` — Project Scaffolding

Scaffold a fully wired, production-ready agent project with typed graph definitions, tests, and configuration.

### Interactive Mode

```bash
alcyoneus init
```

The wizard prompts for:

| Prompt | Options | Default |
|--------|---------|---------|
| **Project name** | Free text | `my-alcyoneus-agent` |
| **Agent architecture** | `react`, `plan-act-reflect`, `swarm`, `supervisor`, `rag` | `react` |
| **Storage backend** | `memory`, `sqlite`, `postgres`, `qdrant` | `memory` |
| **LLM provider** | `openai`, `gemini`, `anthropic`, `ollama` | `openai` |

### Non-Interactive Mode (CI/CD)

```bash
alcyoneus init my-project \
  --agent-type react \
  --storage sqlite \
  --llm-provider gemini \
  --output ./projects/my-project
```

### Generated Files

```
my-project/
├── agent.py           # Fully typed, runnable graph definition
├── pyproject.toml     # Dependencies tailored to your selections
├── .env.example       # API keys & database URLs
├── README.md          # Getting started guide
└── tests/
    └── test_agent.py  # Pytest suite for invocation & streaming
```

### Agent Architecture Patterns

| Pattern | Description |
|---------|-------------|
| `react` | Tool-using reasoning + acting agent with ReAct loop |
| `plan-act-reflect` | Autonomous planning, execution, and reflection cycles |
| `swarm` | Multi-agent cooperative handoff network |
| `supervisor` | Hierarchical team coordinated by a supervisor agent |
| `rag` | Knowledge-retrieval augmented generation with vector store |

### CLI Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--agent-type` | `-a` | Agent architecture pattern |
| `--storage` | `-s` | Persistence / checkpointer backend |
| `--llm-provider` | `-p` | Primary LLM provider |
| `--output` | `-o` | Target directory for the new project |

---

## 2. `alcyoneus doctor` — System Diagnostics

Comprehensive system health check for development environments and CI.

```bash
alcyoneus doctor
```

### What It Inspects

| Category | Checks |
|----------|--------|
| **Python Environment** | Version compliance (≥ 3.12), executable path, platform |
| **Docker Daemon** | Docker CLI availability, daemon status (`ONLINE` / `OFFLINE` / `NOT INSTALLED`) |
| **PTY Subsystem** | Pseudo-terminal allocation for interactive execution |
| **Optional Dependencies** | 12 packages: `google-genai`, `openai`, `fastmcp`, `mcp`, `qdrant-client`, `asyncpg`, `redis`, `piexif`, `playwright`, `aiokafka`, `aio-pika`, `mem0ai` |
| **API Credentials** | `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `QDRANT_API_KEY` (masked) |

### Output Formats

```bash
# Rich formatted table (default)
alcyoneus doctor

# Machine-readable for CI/CD
alcyoneus doctor --json
alcyoneus doctor --yaml
```

### Example JSON Output

```json
{
  "python": {
    "version": "3.12.3",
    "executable": "/usr/bin/python3",
    "platform": "linux"
  },
  "docker": {"status": "ONLINE", "version": "24.0.7"},
  "pty": {"available": true},
  "dependencies": {
    "google-genai": {"installed": true, "version": "1.14.0"},
    "openai": {"installed": true, "version": "1.82.0"},
    "redis": {"installed": false, "version": null}
  },
  "credentials": {
    "OPENAI_API_KEY": "configured",
    "GEMINI_API_KEY": "not set"
  }
}
```

---

## 3. `alcyoneus version` — Version Info

```bash
# Human-readable
alcyoneus version

# Machine-readable
alcyoneus version --json
alcyoneus version --yaml
```

---

## 4. `alcyoneus graph` — Graph Management

### Inspect a Graph

```bash
alcyoneus graph inspect path/to/my_graph.py
alcyoneus graph inspect path/to/my_graph.py --json
alcyoneus graph inspect path/to/my_graph.py --yaml
```

Reports nodes, edges, entry point, conditional routing, and handler functions.

### Validate a Graph

```bash
alcyoneus graph validate path/to/my_graph.py
```

Checks that the graph compiles successfully without errors.

### Create a Graph Template

```bash
alcyoneus graph create my_workflow --nodes "start,process,end"
```

---

## 5. `alcyoneus agent` — Agent Management

### List Agent Types

```bash
alcyoneus agent list
alcyoneus agent list --json
alcyoneus agent list --yaml
```

### Create an Agent Template

```bash
alcyoneus agent create my_agent --type react --model "gemini/gemini-2.5-flash"
```

---

## 6. `alcyoneus tool` — Tool Management

### List Available Tools

```bash
alcyoneus tool list
alcyoneus tool list --category web
alcyoneus tool list --json
```

### Test a Tool

```bash
alcyoneus tool test safe_calculator --input '{"expression": "2+2"}'
```

---

## 7. `alcyoneus completion` — Shell Auto-Completion

Generate or install tab auto-completion for all CLI commands, options, and arguments.

### View Completion Script

```bash
# Print the completion snippet for your shell
alcyoneus completion --shell bash
alcyoneus completion --shell zsh
alcyoneus completion --shell fish
```

### Auto-Install Completion

```bash
# Automatically append to your shell profile
alcyoneus completion --shell bash --install   # → ~/.bashrc
alcyoneus completion --shell zsh --install    # → ~/.zshrc
alcyoneus completion --shell fish --install   # → ~/.config/fish/completions/alcyoneus.fish
```

After installation, activate immediately:

```bash
source ~/.bashrc   # or ~/.zshrc
```

---

## Machine-Readable Output Flags

All data-returning commands support `--json` and `--yaml` for seamless CI/CD integration:

| Command | `--json` | `--yaml` |
|---------|----------|----------|
| `alcyoneus version` | ✅ | ✅ |
| `alcyoneus doctor` | ✅ | ✅ |
| `alcyoneus agent list` | ✅ | ✅ |
| `alcyoneus tool list` | ✅ | ✅ |
| `alcyoneus graph inspect` | ✅ | ✅ |

### Example: CI/CD Pipeline

```bash
# Check environment before deployment
alcyoneus doctor --json | jq '.python.version'

# Scaffold a project in CI
alcyoneus init ci-test-agent \
  --agent-type react \
  --storage memory \
  --llm-provider openai \
  --output /tmp/ci-test

# Validate graph compiles
alcyoneus graph validate /tmp/ci-test/agent.py
```

---

## Module Entrypoint

The CLI is also accessible as a Python module:

```bash
python -m alcyoneus.cli --help
python -m alcyoneus.cli version --json
python -m alcyoneus.cli doctor
```

---

## Configuration

The CLI stores user preferences in `~/.alcyoneus/config.yaml`:

```yaml
default_model: gemini/gemini-2.5-flash
default_storage: sqlite
default_provider: openai
```

Set values via:

```bash
alcyoneus config set default_model "openai/gpt-4o"
alcyoneus config get default_model
```
