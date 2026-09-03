# CHANGELOG

<!-- version list -->

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
