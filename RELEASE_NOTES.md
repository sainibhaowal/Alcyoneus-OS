# Alcyoneus OS v1.2.0 — Enterprise Hardening Release Notes

> **Comprehensive End-to-End Release Document**  
> **Target Release:** `v1.2.0`  
> **Previous Release Baseline:** `v1.1.1` (September 03, 2026)  
> **Scope:** 144 files changed, +6,065 insertions, -2,014 deletions  
> **Build Status:** 100% Green CI (Multi-OS Linux / macOS / Windows), 0 skipped tests, 0 mypy type errors across 379 source files  

---

## 🚀 Release Summary & Architectural Impact

Alcyoneus OS **v1.2.0** represents a comprehensive hardening and enterprise-expansion release. Designed to bridge low-level agent state machines with enterprise infrastructure, this release eliminates technical debt, introduces strict type safety, unifies tool execution security under a 9-tier priority policy engine with path sandboxing, adds native carrier VoIP/SIP telephony for voice agents, introduces true interactive PTY terminal isolation, delivers an automated developer CLI (`init`, `doctor`, shell completions), and guarantees cross-backend storage invariants via a unified conformance test suite.

---

## 🌟 Major Highlights & Deep-Dive Feature Breakdown

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Alcyoneus OS v1.2.0                                │
├───────────────────────────────┬─────────────────────────────┬───────────────┤
│  Pillar 1: Security & Policy  │  Pillar 2: Runtime & Voice  │ Pillar 3: Dev │
│  • 9-Tier Policy Engine       │  • Native SIP/VoIP Gateway  │ • CLI doctor  │
│  • workspace_only Sandboxing  │  • Interactive Unix PTY     │ • CLI init    │
│  • Human-in-the-Loop Intercept│  • Async Non-blocking I/O   │ • Shell Comps │
├───────────────────────────────┴─────────────────────────────┴───────────────┤
│                     Foundation: Type Safety & Conformance                   │
│   • 0 Mypy Errors across 379 source files (check_untyped_defs = true)       │
│   • Universal Storage Conformance Matrix (InMemory, SQLite, PostgreSQL)     │
│   • 3,273+ Unit & Integration Tests Passing (0 Skipped, fail_under = 90)    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1. Unified 9-Tier Safety & Policy Engine (`alcyoneus.core.policy` & `alcyoneus.core.graph.tool_node`)
Prior to v1.2.0, tool policy logic was fragmented between legacy `tool_node/policy.py` and experimental guards. v1.2.0 completely unifies policy enforcement into a declarative, mathematical evaluation engine.

* **9-Tier Priority Bucket Hierarchy**: Rules are evaluated strictly by specificity and action:
  1. **Specific Deny** (`tool="run_command"`, `DENY`): Blocks a single tool regardless of wildcards.
  2. **Specific Ask (HITL)** (`tool="run_command"`, `ASK_USER`): Triggers approval for a specific tool.
  3. **Specific Allow** (`tool="run_command"`, `APPROVE`): Unconditionally approves a specific tool.
  4. **Prefix Deny** (`tool="fs/*"`, `DENY`): Blocks all tools under a namespace prefix.
  5. **Prefix Ask (HITL)** (`tool="fs/*"`, `ASK_USER`): Triggers approval for a namespace prefix.
  6. **Prefix Allow** (`tool="fs/*"`, `APPROVE`): Approves all tools under a namespace prefix.
  7. **Global Deny** (`tool="*"`, `DENY`): Global fallback rejection.
  8. **Global Ask (HITL)** (`tool="*"`, `ASK_USER`): Global fallback prompt.
  9. **Global Allow** (`tool="*"`, `APPROVE`): Permissive fallback.
* **Fail-Closed Guarantee**: Any tool invocation that fails to match an explicit policy bucket evaluates immediately to `DENY`.
* **Path-Traversal Proof Sandboxing (`workspace_only`)**:
  * Prevents arbitrary host filesystem tampering by resolving absolute canonical paths (`os.path.realpath`) for file arguments (`path`, `filepath`, `target`, `src`, `dest`).
  * Rejects parent path escapes (`../`), hidden directory breakouts, and symlink redirects pointing outside the designated root.
* **Human-in-the-Loop Interception (`ask_user`)**:
  * First-class asynchronous callback handler support (`ask_user(..., handler=async_callable)`).
  * Out-of-the-box terminal prompt fallback via `default_ask_user_handler()`.
* **Tenant & MCP Origin Scoping**:
  * Policies support granular constraint matching against `tenant_ids`, `user_ids`, and `mcp_server` origins.
* **Direct Integration into `ToolNode`**:
  * `ToolNode` now natively accepts `policy=PolicyEngine(...)`, `policy=safe_defaults(workspace_path=...)`, or custom lists of `Policy` objects.

```python
from alcyoneus.core import ToolNode
from alcyoneus.core.policy import PolicyEngine, allow, ask_user, deny, workspace_only

# Production-grade agent tool authorization
policy_engine = PolicyEngine(
    policies=[
        # Restrict filesystem access to /app/sandbox
        workspace_only(workspace_path="/app/sandbox", tools=["file_read", "file_write"]),
        # Require human sign-off for dangerous bash execution
        ask_user("shell_command"),
        # Explicitly ban process destruction
        deny("kill_process"),
        # Pure computation is allowed
        allow("calculator"),
        # Fail-closed default
        deny("*"),
    ]
)

tool_node = ToolNode(tools=[...], policy=policy_engine)
```

---

### 2. Native Voice & SIP Telephony (`alcyoneus.core.voice.sip`)
v1.2.0 introduces first-class telecommunications primitives, allowing conversational agents to interact directly with standard telephone networks (PSTN) and VoIP gateways.

* **Standardized Session Architecture**:
  * Powered by `SIPTelephony` and `SIPCallConfig` supporting E.164 phone numbers, SIP domain endpoints, custom caller IDs, account credentials, and configurable HTTP timeouts.
* **Full Async Call Lifecycle**:
  * `initiate_call()`: Posts call creation to upstream trunking gateways (e.g. Twilio Voice API).
  * `get_call_status(call_id)`: Queries live gateway state (`queued`, `ringing`, `in-progress`, `completed`).
  * `hangup(call_id)`: Gracefully terminates active sessions and releases audio channels.
* **Deterministic Mock Engine (`mock=True`)**:
  * When `mock=True` is passed to `SIPCallConfig`, simulated telephone sessions with synthetic call SIDs (`sip_mock_*`) are executed locally.
  * Allows end-to-end integration testing in CI/CD without API keys, live carrier accounts, or telecommunications billing.
* **Typed Error Hierarchy**:
  * `SIPTelephonyError`: Base telephony exception.
  * `SIPConfigurationError`: Raised on missing credentials or empty destination phone numbers.
  * `SIPCallFailedError`: Raised when the gateway returns HTTP 4xx/5xx or rejected SIP INVITE responses (exposing `.status_code`, `.error_code`, and `.response_body`).

---

### 3. Interactive Pseudo-Terminal Sandboxing (`alcyoneus.sandbox.pty_sandbox`)
While `DockerSandbox` and `K8sSandbox` provide complete container boundary isolation, certain agent workloads require lightweight interactive terminals (handling ANSI color codes, tab completion, bash sessions, and ncurses TUIs).

* **True PTY Terminal Emulation**:
  * Uses `pty.openpty()` to generate real OS pseudo-terminal pairs.
* **Asynchronous Non-Blocking Streaming**:
  * Leverages `asyncio.get_running_loop().add_reader(master_fd, ...)` on Unix systems for event-driven stdout/stderr capture without thread starvation.
  * Includes resilient fallback threading for environments where file descriptor loop readers are restricted.
* **Execution Timeout Guardrails**:
  * Enforces wall-clock execution limits via `timeout_seconds`.
  * Automatically sends `SIGKILL` to hanging child processes, reaps zombie process entries, and ensures master/slave file descriptors are reclaimed on `ExecTimeoutError`.

---

### 4. Developer Experience & CLI Toolchain (`alcyoneus.cli`)
A completely reimagined CLI turning Alcyoneus OS into a production-grade developer platform.

* **Interactive Project Wizard (`alcyoneus init`)**:
  * Scaffolds complete, runnable agent architectures via interactive prompts or non-interactive CI flags (`--agent-type`, `--storage`, `--llm-provider`, `--output`):
    * **5 Architectural Blueprints**: `react` (ReAct Reasoning), `plan-act-reflect` (Iterative Planner), `swarm` (Multi-Agent Swarm), `supervisor` (Supervisor & Workers), `rag` (Retrieval-Augmented Generation).
    * **4 Storage Connectors**: `memory` (InMemory), `sqlite` (SqliteCheckpointer), `postgres` (PgCheckpointer & Redis), `qdrant` (QdrantStore).
    * **4 LLM Providers**: `openai` (GPT-4o), `gemini` (Gemini 2.5/3 Flash), `anthropic` (Claude 3.5 Sonnet), `ollama` (Local LLMs).
  * Automatically generates:
    * `agent.py`: Runnable, typed workflow script.
    * `pyproject.toml`: Dependency specification tailored to the chosen architecture and storage backend.
    * `.env.example`: Provider-specific environment variable templates.
    * `tests/test_agent.py`: Automated Pytest test suite ready for execution.
    * `README.md`: Architecture guide and run instructions.
* **Automated System Doctor (`alcyoneus doctor`)**:
  * Validates developer workstation and CI runtime readiness across:
    * **Python Runtime**: Validates `>= 3.12` compliance.
    * **Docker Daemon**: Checks if the Docker engine binary exists and the daemon is reachable.
    * **PTY Subsystem**: Checks pseudo-terminal allocation capability.
    * **12 Optional Ecosystem Dependencies**: Reports installation status and versions for `google-genai`, `openai`, `fastmcp`, `mcp`, `qdrant-client`, `asyncpg`, `redis`, `piexif`, `playwright`, `aiokafka`, `aio-pika`, and `mem0ai`.
    * **API Credentials**: Safely checks presence of `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, and `QDRANT_API_KEY` with secure string masking.
* **Machine-Readable Formats**:
  * Added `--json` and `--yaml` flags to `version`, `doctor`, `agent list`, `tool list`, and `graph inspect`.
* **Shell Tab Auto-Completion**:
  * Added `alcyoneus completion --shell {bash|zsh|fish} [--install]` to generate shell completion scripts or append them directly to profile rc files.
* **Direct Module Invocation**:
  * Added `alcyoneus/cli/__main__.py` allowing execution via `python -m alcyoneus.cli`.

---

### 5. Type Safety & Rigor (0 Mypy Overrides)
* Removed every single `[[tool.mypy.overrides]] ignore_errors = true` configuration block from `pyproject.toml`.
* Enabled `check_untyped_defs = true` repository-wide.
* Added explicit type annotations and generics across 379 source files:
  * Checkpointer async signatures (`BaseCheckpointer[StateT]`).
  * LLM provider response converters (`OpenAIConverter`, `GoogleGenAIConverter`, `LiteLLMConverter`).
  * Sandbox process handlers and executor interfaces.
  * Graph stream transformer pipelines (`StreamChunk`, `StreamEvent`).
* Result: **0 typing errors across 379 source files** under strict mypy validation.

---

### 6. Storage Conformance Matrix & Test Verification
* **Universal Checkpointer Conformance Matrix (`tests/storage/test_conformance_matrix.py`)**:
  * Built a parametrized test suite that executes identical operational suites against `InMemoryCheckpointer`, `SqliteCheckpointer`, and `PgCheckpointer`.
  * Verifies: state persistence across steps, strict multi-thread isolation, thread deletion (`aclean_thread` / `adelete_thread`), state rollback, and message sequence integrity.
* **Sandbox Mock Isolation Suite (`tests/sandbox/test_sandboxes.py`)**:
  * Comprehensive testing for `DockerSandbox` (tar file transfer, container spinup, timeouts) and `K8sSandbox` (manifest construction, pod lifecycle, failure phases).
* **Graph Lifecycle & HITL Suite (`tests/graph/test_graph_lifecycle.py`)**:
  * Tests complex cyclic graphs, conditional routing, dynamic prompt templates, interrupt/resume workflows, and streaming transformers.
* **Zero-Skip Repository Policy**:
  * Removed all `pytest.skip` and `@pytest.mark.skip` calls.
  * Test suite status: **3,273+ passed, 0 skipped, 0 failed** with code coverage baseline enforced at `>= 90%`.

---

## 🐛 Complete Bug Fixes & Code Hardening (v1.1.1 ➔ v1.2.0)

Every bug fix merged since v1.1.1 has been verified against the commit log:

### 1. Core Graph Execution & Memory
* **Elimination of Circular Imports**: Fixed an import cycle where `alcyoneus.core.graph.agent` imported `StateGraph`, `StateGraph` imported `Agent`, and `long_term_memory` depended on both. Resolved using runtime import resolution and typing protocols ([`218489d`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/218489d36bec6d9bad29db92c8e6cf2698617b1f)).
* **State Graph Compile Singleton Cache Eviction**: Fixed an issue where `StateGraph.compile()` did not invalidate cached singleton scopes in the dependency injection container, which caused test doubles and sequential graph executions to leak stale checkpointers and stores ([`f83c3fc`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/f83c3fcb0a50f0e9c0c938a22cb4885c60dda9f7)).
* **CompiledGraph State Update Cache**: Added missing `aput_state_cache()` update during `update_state()`, preventing cache desynchronization when mutating graph state mid-run ([`f83c3fc`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/f83c3fcb0a50f0e9c0c938a22cb4885c60dda9f7)).

### 2. Security & CodeQL Static Analysis (19 Alerts Resolved)
* **PTY Sandbox Process & File Descriptor Cleanup**:
  * Handled `ProcessLookupError` gracefully when terminating timed-out PTY processes that exited just before `proc.kill()` was issued ([`bf30004`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/bf300048093c41a495acfc1f37dea58781faacda)).
  * Wrapped non-blocking buffer drains and `os.close(master_fd)` in exception guards to prevent double-close `OSError` crashes ([`bf30004`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/bf300048093c41a495acfc1f37dea58781faacda)).
* **Multi-Tenant Store Key Isolation**:
  * Resolved missing tenant prefix routing in `TenantAwareStore.get()` and `delete()` where dictionary configs could bypass tenant scoping ([`bf30004`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/bf300048093c41a495acfc1f37dea58781faacda)).
* **Agent Mixin Protocol Conformance**:
  * Updated `AgentGoogleMixin` and `AgentOpenAIMixin` to use typed callable members (`_extract_prompt: Callable[..., str]`) instead of abstract methods with `raise NotImplementedError`, resolving static type inspection failures in subclasses ([`bf30004`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/bf300048093c41a495acfc1f37dea58781faacda)).
* **Protocol Transport Redundant Imports**:
  * Removed redundant inline `import asyncio` calls inside `ACPInMemoryTransport` ([`bf30004`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/bf300048093c41a495acfc1f37dea58781faacda)).

### 3. Telephony & Sandbox Resiliency
* **SIP Telephony Production Validation**:
  * Fixed an issue in `SIPTelephony` where missing `account_sid` or `auth_token` in production mode (`mock=False`) would construct an unauthenticated request rather than raising an immediate `SIPConfigurationError` ([`f83c3fc`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/f83c3fcb0a50f0e9c0c938a22cb4885c60dda9f7)).
* **Docker Sandbox Subprocess Decoding**:
  * Replaced unsafe `proc.communicate()` decoding with safe null checks and `replace` error handlers, preventing container execution failures on non-UTF-8 binary output ([`f83c3fc`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/f83c3fcb0a50f0e9c0c938a22cb4885c60dda9f7)).
* **K8s Sandbox Resource Limits**:
  * Fixed resource specification parsing in Kubernetes pod manifests to ensure GPU requests are only injected when `gpu_config != GPUConfig.NONE` and `gpu_devices` are explicitly provisioned ([`f83c3fc`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/f83c3fcb0a50f0e9c0c938a22cb4885c60dda9f7)).

### 4. Continuous Integration & Concurrency
* **macOS Task Scheduling Race**:
  * Fixed an async race condition in `test_pty_sandbox.py` where background ticker tasks could hang the test runner on macOS runners ([`81dd9eb`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/81dd9ebb9c16fc01d1d6e1ea8a82ca7029580ef5)).
* **A2A Client Executor Typing**:
  * Resolved typing errors in A2A executor client when interfacing with the external `a2a-sdk` ([`81dd9eb`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/81dd9ebb9c16fc01d1d6e1ea8a82ca7029580ef5)).
* **Code Formatting**:
  * Applied repository-wide Ruff formatting and import ordering across all modified modules ([`81dd9eb`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/81dd9ebb9c16fc01d1d6e1ea8a82ca7029580ef5)).

---

## 📚 New & Updated Documentation Guides

| Guide | Path | Description |
|---|---|---|
| **CLI Reference Manual** | [`docs/CLI.md`](docs/CLI.md) | Full guide covering `init`, `doctor`, `graph inspect`, shell completion, and flags. |
| **Voice & SIP Telephony** | [`docs/VOICE.md`](docs/VOICE.md) | Guide for VoIP gateways, Twilio SIP trunking, call lifecycles, and mock testing. |
| **Sandboxes & Isolation** | [`docs/SANDBOX.md`](docs/SANDBOX.md) | Execution architectures for Unix PTY terminals, Docker containers, and Kubernetes pods. |
| **Security Architecture** | [`docs/SECURITY.md`](docs/SECURITY.md) | In-depth breakdown of the 9-tier priority policy engine and path sandboxing. |
| **Testing & Conformance** | [`docs/TESTING.md`](docs/TESTING.md) | Conformance test suite documentation, zero-skip enforcement, and coverage rules. |
| **Quickstart Guide** | [`docs/QUICKSTART.md`](docs/QUICKSTART.md) | Getting started in under 2 minutes with `alcyoneus init`. |

---

## 📦 Installation & Quick Upgrade

```bash
# Upgrade core library to v1.2.0
pip install --upgrade alcyoneus

# Or install with targeted enterprise extras:
pip install "alcyoneus[voice]"      # SIP telephony & audio providers
pip install "alcyoneus[sandbox]"    # Docker & Kubernetes runners
pip install "alcyoneus[storage]"    # PostgreSQL, Redis & Qdrant connectors
```

Check your environment health immediately:
```bash
alcyoneus doctor
```

Scaffold a new agentic application:
```bash
alcyoneus init
```

---

## 👥 Full Commit History (v1.1.1 ➔ v1.2.0)

* `218489d` — **fix(graph)**: eliminate circular imports between agent, state_graph, and long_term_memory (by @Ravi)
* `bf30004` — **fix(security)**: resolve 19 CodeQL static analysis alerts across core, sandbox, and telephony (by @Ravi)
* `81dd9eb` — **fix(ci)**: format code with ruff, resolve a2a mypy types, and fix macos task race (by @Ravi)
* `f83c3fc` — **feat(release)**: Alcyoneus OS v1.2.0 enterprise release (by @Ravi)

**Full Git Diff Comparison**: https://github.com/sainibhaowal/Alcyoneus-OS/compare/v1.1.1...v1.2.0
