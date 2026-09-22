# CHANGELOG

<!-- version list -->

## v1.2.0 (2026-09-22)

### Type Safety & Rigor (Pillar 1)

- **BREAKING**: Remove all `[[tool.mypy.overrides]] ignore_errors = true` blocks from `pyproject.toml` — zero overrides remaining
- Enable `check_untyped_defs = true` for strict type checking across entire codebase
- Add explicit type annotations to 379 source files across all modules:
  prebuilt tools, storage connectors, sandbox backends, core graph engine,
  A2A/ACP protocols, QA evaluators, and real-time audio providers
- Achieve `mypy alcyoneus/` → **0 errors across 379 source files**

### Developer Experience & CLI (Pillar 2)

- **feat(cli)**: Add `alcyoneus init` interactive project scaffolding wizard
  - 5 agent architectures: ReAct, Plan-Act-Reflect, Swarm, Supervisor, RAG
  - 4 storage backends: InMemory, SQLite, PostgreSQL, Qdrant
  - 4 LLM providers: OpenAI, Google Gemini, Anthropic, Ollama
  - Generates: `agent.py`, `pyproject.toml`, `.env.example`, `tests/test_agent.py`, `README.md`
  - Full non-interactive CLI flag support for CI/CD: `--agent-type`, `--storage`, `--llm-provider`, `--output`
- **feat(cli)**: Add `alcyoneus doctor` system health and dependency diagnostics
  - Python version compliance, Docker daemon status, PTY subsystem, 12 optional dependencies, 4 API credentials
  - Supports `--json` / `--yaml` output for CI pipelines
- **feat(cli)**: Add `--json` / `--yaml` machine-readable output to `version`, `doctor`, `agent list`, `tool list`, `graph inspect`
- **feat(cli)**: Add `alcyoneus completion --shell {bash|zsh|fish} [--install]` for shell tab auto-completion
- **feat(cli)**: Add `alcyoneus/cli/__main__.py` enabling `python -m alcyoneus.cli`

### Test Suite Coverage & Conformance (Pillar 3)

- **feat(tests)**: Add universal storage conformance matrix (`tests/storage/test_conformance_matrix.py`)
  - Parametrized tests across InMemoryCheckpointer, SqliteCheckpointer, PgCheckpointer
  - Verifies: state persistence, thread isolation, state overwrite, thread deletion, message history
- **feat(tests)**: Add sandbox mock isolation suite (`tests/sandbox/test_sandboxes.py`)
  - DockerSandbox: SDK lifecycle, CLI fallback, TAR transfer, timeout handling
  - K8sSandbox: Pod lifecycle, exec streaming, base64 file I/O, failure phases
- **feat(tests)**: Add graph lifecycle & HITL test suite (`tests/graph/test_graph_lifecycle.py`)
  - Complex cyclic graphs, dynamic prompt interpolation, interrupt/resume workflows, stream transformers
- **chore(tests)**: Eliminate all `pytest.skip` / `@pytest.mark.skip` — zero skipped tests across entire repository
- **chore(config)**: Set `fail_under = 90` in `[tool.coverage.report]`
- **fix(graph)**: Fix singleton scope cache invalidation in `StateGraph.compile()` preventing cross-test state leakage
- Test suite: **3,273+ passed, 0 skipped, 0 failed**

### Documentation

- Add comprehensive CLI reference (`docs/CLI.md`)
- Expand testing documentation with conformance, sandbox, HITL, coverage, and zero-skip policy sections
- Update `docs/INDEX.md` with CLI navigation link
- Update `docs/QUICKSTART.md` with `alcyoneus init` fast-track

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
