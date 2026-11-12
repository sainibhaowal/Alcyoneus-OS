# CHANGELOG

<!-- version list -->

## v1.2.0 (2026-09-23)

> **Major Enterprise Hardening Release**: Complete type-safety rigor (0 mypy errors across 379 files), unified 9-tier declarative safety & policy engine with path sandboxing, enterprise SIP telephony for voice agents, interactive Unix PTY terminal sandboxing, full-featured developer CLI (`doctor`, `init`, completion, multi-format output), universal storage checkpointer conformance testing, and 100% green zero-skip test suite.

### 🌟 Highlights & Major Features

- **Unified Safety & Policy Engine (`alcyoneus.core.policy`)**:
  - Re-architected authorization into a **9-tier evaluation priority hierarchy**:
    1. Specific Deny (`tool="shell_command"`, `DENY`)
    2. Specific Ask (`tool="shell_command"`, `ASK_USER`)
    3. Specific Allow (`tool="shell_command"`, `APPROVE`)
    4. Prefix Deny (`tool="fs/*"`, `DENY`)
    5. Prefix Ask (`tool="fs/*"`, `ASK_USER`)
    6. Prefix Allow (`tool="fs/*"`, `APPROVE`)
    7. Global Deny (`tool="*"`, `DENY`)
    8. Global Ask (`tool="*"`, `ASK_USER`)
    9. Global Allow (`tool="*"`, `APPROVE`)
  - **Fail-Closed Default**: Unknown tools or unmatched execution requests evaluate strictly to `DENY`.
  - **`workspace_only` Path Sandboxing**: Path-traversal proof confinement for filesystem tools (`file_read`, `file_write`, `list_directory`, etc.) verifying that resolved canonical target paths strictly reside within the configured directory.
  - **Scoped Access Control**: Fine-grained filtering support for `tenant_ids`, `user_ids`, and `mcp_server` prefixes.
  - **Async Human-In-The-Loop (HITL) Interception**: First-class async callable approval handlers (`ask_user(..., handler=custom_handler)`) with `default_ask_user_handler` fallback.
  - Direct integration into `ToolNode` and `CompiledGraph` via `ToolExecutionPolicy` and `PolicyConfig`.

- **Native Voice & SIP Telephony (`alcyoneus.core.voice.sip`)**:
  - Enterprise VoIP and Public Switched Telephone Network (PSTN) connectivity for voice agents.
  - Standardized `SIPCallConfig` dataclass and async lifecycle operations: `initiate_call()`, `get_call_status()`, and `hangup()`.
  - Strict input validation requiring destination numbers, SID, and credentials in production mode.
  - Zero-cost testability with deterministic `mock=True` simulation mode for CI/CD pipelines without incurring carrier fees.
  - Resilient exception hierarchy: `SIPTelephonyError`, `SIPConfigurationError`, and `SIPCallFailedError` (with HTTP status codes, error codes, and body details).

- **Interactive Pseudo-Terminal Sandbox (`alcyoneus.sandbox.pty_sandbox`)**:
  - Native `UnixPTYSandbox` providing full interactive TTY terminal emulation (`pty.openpty()`).
  - Asynchronous non-blocking streaming I/O leveraging `asyncio` event loop readers with threaded cross-platform fallbacks.
  - Granular execution timeout guardrails raising `ExecTimeoutError` with clean process termination and file descriptor reclamation.

- **Developer Experience & CLI Suite (`alcyoneus.cli`)**:
  - **Interactive Project Wizard (`alcyoneus init`)**: Scaffold production-ready agent projects with support for 5 agent architectures (ReAct, Plan-Act-Reflect, Swarm, Supervisor, RAG), 4 storage backends (InMemory, SQLite, PostgreSQL, Qdrant), and 4 LLM providers (OpenAI, Gemini, Anthropic, Ollama). Generates `agent.py`, `pyproject.toml`, `.env.example`, `tests/test_agent.py`, and `README.md`.
  - **System Health Diagnostics (`alcyoneus doctor`)**: Automated validation of Python runtime compliance (>= 3.12), Docker daemon readiness, PTY subsystem availability, 12 ecosystem optional dependencies, and masked API credentials with formatted Rich tables.
  - **Structured Machine Output**: Added `--json` and `--yaml` flags across `version`, `doctor`, `agent list`, `tool list`, and `graph inspect`.
  - **Shell Completion**: Added `alcyoneus completion --shell {bash|zsh|fish} [--install]` for CLI tab auto-completion.
  - **CLI Module Entrypoint**: Added `alcyoneus/cli/__main__.py` allowing execution via `python -m alcyoneus.cli`.

- **Strict Type Rigor & Architecture (Zero Mypy Overrides)**:
  - Removed all `[[tool.mypy.overrides]] ignore_errors = true` blocks from `pyproject.toml` — achieving **0 mypy errors across 379 source files**.
  - Strict type checking enabled with `check_untyped_defs = true`.
  - Full typing coverage across graph nodes, checkpointers, vector stores, sandboxes, QA simulation suites, and LLM converter adapters.

- **Storage Conformance Matrix & Universal Testing**:
  - Added universal checkpointer conformance test suite (`tests/storage/test_conformance_matrix.py`) validating `InMemoryCheckpointer`, `SqliteCheckpointer`, and `PgCheckpointer` under unified state persistence, thread isolation, and deletion invariants.
  - Added sandbox isolation and failure injection tests (`tests/sandbox/test_sandboxes.py`).
  - Added graph lifecycle, cyclic routing, and HITL interrupt tests (`tests/graph/test_graph_lifecycle.py`).
  - Enforced zero-skip policy across repository: **3,273+ passed, 0 skipped, 0 failed** with code coverage baseline enforced at `>= 90%`.

---

### 🐛 Bug Fixes & Hardening (Since v1.1.1)

- **Circular Imports**:
  - Fixed circular dependency chain between `alcyoneus.core.graph.agent`, `alcyoneus.core.graph.state_graph`, and `alcyoneus.storage.store.long_term_memory` using delayed import resolution and module encapsulation ([`218489d`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/218489d36bec6d9bad29db92c8e6cf2698617b1f)).
- **CodeQL Static Analysis & Security**:
  - Fixed 19 CodeQL static analysis alerts across core graph execution, multi-tenancy, PTY sandboxing, and telephony:
    - Safely handled non-blocking file descriptor cleanup and pre-exited processes in `UnixPTYSandbox` ([`bf30004`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/bf300048093c41a495acfc1f37dea58781faacda)).
    - Fixed multitenant store key leakage and attribute routing in `TenantAwareStore` and `TenantCheckpointer` ([`bf30004`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/bf300048093c41a495acfc1f37dea58781faacda)).
    - Fixed typing protocol conformance for Google and OpenAI agent mixins (`_extract_prompt` signature) ([`bf30004`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/bf300048093c41a495acfc1f37dea58781faacda)).
    - Removed redundant local imports inside `ACPInMemoryTransport` ([`bf30004`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/bf300048093c41a495acfc1f37dea58781faacda)).
- **CI / Concurrency & Formatting**:
  - Resolved macOS async task race condition during unit tests ([`81dd9eb`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/81dd9ebb9c16fc01d1d6e1ea8a82ca7029580ef5)).
  - Corrected A2A protocol mypy type annotations in client executor ([`81dd9eb`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/81dd9ebb9c16fc01d1d6e1ea8a82ca7029580ef5)).
  - Applied repository-wide Ruff formatting and linting alignments ([`81dd9eb`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/81dd9ebb9c16fc01d1d6e1ea8a82ca7029580ef5)).
- **Graph State Isolation & Caching**:
  - Fixed singleton scope cache invalidation in `StateGraph.compile()` ensuring test doubles and multi-graph executions do not leak shared runtime state ([`f83c3fc`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/f83c3fcb0a50f0e9c0c938a22cb4885c60dda9f7)).
  - Added cache update hook in `CompiledGraph.update_state()` ensuring thread state caches stay in sync ([`f83c3fc`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/f83c3fcb0a50f0e9c0c938a22cb4885c60dda9f7)).
- **Telephony & Sandbox Resiliency**:
  - Enforced strict credential checks in `SIPTelephony` preventing undefined payload dispatches when `mock=False` ([`f83c3fc`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/f83c3fcb0a50f0e9c0c938a22cb4885c60dda9f7)).
  - Guarded non-UTF8 binary outputs in `DockerSandbox` using safe decoding and fallback handlers ([`f83c3fc`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/f83c3fcb0a50f0e9c0c938a22cb4885c60dda9f7)).
  - Fixed K8s pod manifest resource specifications to inject GPU limits only when devices are provisioned ([`f83c3fc`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/f83c3fcb0a50f0e9c0c938a22cb4885c60dda9f7)).

---

### 📚 Documentation & Developer Guides

- Added comprehensive CLI reference manual ([`docs/CLI.md`](docs/CLI.md)) detailing all command options and scaffolding specs.
- Added Voice & SIP Telephony production deployment guide ([`docs/VOICE.md`](docs/VOICE.md)).
- Added Sandbox & Code Isolation guide ([`docs/SANDBOX.md`](docs/SANDBOX.md)) covering PTY, Docker, and K8s runners.
- Updated Security Architecture documentation ([`docs/SECURITY.md`](docs/SECURITY.md)) with 9-tier policy DSL specs and path sandboxing.
- Expanded Testing & Conformance guide ([`docs/TESTING.md`](docs/TESTING.md)) documenting the zero-skip policy and conformance test harness.
- Added quick project scaffolding fast-track in ([`docs/QUICKSTART.md`](docs/QUICKSTART.md)).

---

## v1.1.1 (2026-09-03)

### Bug Fixes

- **ci**: Resolve gitleaks false positives and add testing extra for CI matrix
  ([`e8beda7`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/e8beda7b7f11975e00e3e86a05305dfe35687c28))

- **core**: Add aiohttp to dependencies, ignore bandit false positives, fix mypy in skills loader
  ([`354346e`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/354346e8ff660a3bc08bc174c6ca7b15b45cc0c3))

- **realtime**: Lazy-load numpy in local_whisper_tts so base test suite runs without optional
  realtime extras
  ([`903e6dc`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/903e6dc0cbe73aa4296278a07c5448a64cab6dff))

- **test**: Patch HAS_MEM0 in test_mem0_store_async fixture
  ([`a935111`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/a935111f8f76fb846337ec3e5424bc40522ffaac))

### Chores

- Migrate license to Apache 2.0 and update v1.1.0 release badges
  ([`4116a4f`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/4116a4fc67552eff585be5cd910bfb26cf9c5990))

### Continuous Integration

- Expand multi-OS matrix runners and fix pip editable installs across GitHub runners
  ([`daaf1be`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/daaf1be77f21e50b0ef1856289fe5c6625315881))

- Fix pre-commit hooks, ruff formatting, and test slice configurations for 100% green CI
  ([`46007de`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/46007de714af565ead114d3f1bedba634261370a))

- Trigger full CI matrix across all platforms
  ([`46772ad`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/46772ad53b5e8da4e9ac72a36af26c7f9831a27d))

### Documentation

- Add PyPI package badge and official link to README
  ([`264cbb0`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/264cbb0fc14e70ddc607da649273cc32e449bb64))

- Use absolute raw GitHub CDN URL for banner to fix PyPI and external rendering
  ([`eb27b60`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/eb27b60d087a1a33bd726cd7d72500ebebb99809))

## v1.1.0 (2026-08-23)

### Continuous Integration

- Add automated PyPI publish step to release workflow
  ([`74821d2`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/74821d2af780eb7d185b3d6d715ea14af9566537))

### Documentation

- Add full-width responsive header banner and comprehensive logo asset suite
  ([`a0dd2fc`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/a0dd2fc0eba6c0a24ddae5f62aeddaa4a2d5b9fb))

- Update repository links to sainibhaowal/Alcyoneus-OS
  ([`5ecad81`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/5ecad819a11d296d1a30054c04129c0f3e68e9bd))

### Features

- **core**: Export START and END constants at top-level package
  ([`a1709ce`](https://github.com/sainibhaowal/Alcyoneus-OS/commit/a1709ceba8979c1fcdb6d24f54d7963d65569d99))


## v1.0.0 (2026-08-23)

- Initial Release
