"""Policy-controlled browser automation and screenshots.

Playwright is optional.  The tool never launches a browser unless the host
supplies a configured :class:`BrowserController`; this keeps browser access
explicit, auditable, and safe for server deployments.
"""

from __future__ import annotations

import inspect
import ipaddress
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from alcyoneus.utils.decorators import tool


@dataclass(slots=True)
class BrowserPolicy:
    """Allowlist and resource limits for browser sessions."""

    allowed_domains: set[str] = field(default_factory=set)
    blocked_domains: set[str] = field(default_factory=set)
    allow_http: bool = False
    allow_private_network: bool = False
    max_pages: int = 4
    navigation_timeout_ms: int = 30_000
    max_text_chars: int = 100_000

    def check_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"https", "http"}:
            raise ValueError("browser only supports http(s) URLs")
        if parsed.scheme == "http" and not self.allow_http:
            raise PermissionError("plain HTTP is disabled by browser policy")
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host:
            raise ValueError("URL must include a hostname")
        if parsed.username or parsed.password:
            raise PermissionError("URLs with embedded credentials are not allowed")
        if not self.allow_private_network:
            if host in {"localhost", "localhost.localdomain"}:
                raise PermissionError("private browser destinations are disabled")
            try:
                if ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback:
                    raise PermissionError("private browser destinations are disabled")
            except ValueError:
                pass
        if host in self.blocked_domains or any(
            host.endswith("." + d.lstrip("*.")) for d in self.blocked_domains
        ):
            raise PermissionError(f"browser domain is blocked: {host}")
        if self.allowed_domains and not (
            host in self.allowed_domains
            or any(host.endswith("." + d.lstrip("*.")) for d in self.allowed_domains)
        ):
            raise PermissionError(f"browser domain is not allowlisted: {host}")


class BrowserController:
    """Async Playwright-backed controller with bounded page state."""

    def __init__(self, *, policy: BrowserPolicy | None = None, browser: Any = None) -> None:
        self.policy = policy or BrowserPolicy()
        self._browser = browser
        self._playwright = None
        self._contexts: dict[str, Any] = {}
        self._pages: dict[str, Any] = {}

    async def _page(self, session_id: str) -> Any:
        page = self._pages.get(session_id)
        if page is not None:
            return page
        if len(self._pages) >= self.policy.max_pages:
            raise RuntimeError("browser page limit reached")
        if self._browser is None:
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:
                raise RuntimeError("browser automation requires 'playwright'") from exc
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
        context = await self._browser.new_context()
        page = await context.new_page()
        page.set_default_navigation_timeout(self.policy.navigation_timeout_ms)
        self._contexts[session_id] = context
        self._pages[session_id] = page
        return page

    async def navigate(self, session_id: str, url: str) -> dict[str, Any]:
        self.policy.check_url(url)
        page = await self._page(session_id)
        response = await page.goto(url, wait_until="domcontentloaded")
        return {
            "session_id": session_id,
            "url": page.url,
            "status": response.status if response else None,
            "title": await page.title(),
        }

    async def click(self, session_id: str, selector: str) -> dict[str, Any]:
        page = await self._page(session_id)
        await page.locator(selector).click()
        return {"session_id": session_id, "url": page.url, "clicked": selector}

    async def fill(self, session_id: str, selector: str, value: str) -> dict[str, Any]:
        page = await self._page(session_id)
        await page.locator(selector).fill(value)
        return {"session_id": session_id, "url": page.url, "filled": selector}

    async def extract(self, session_id: str, selector: str | None = None) -> dict[str, Any]:
        page = await self._page(session_id)
        text = await (
            page.locator(selector).inner_text() if selector else page.locator("body").inner_text()
        )
        return {
            "session_id": session_id,
            "url": page.url,
            "text": text[: self.policy.max_text_chars],
        }

    async def screenshot(self, session_id: str, *, full_page: bool = False) -> bytes:
        page = await self._page(session_id)
        return await page.screenshot(full_page=full_page, type="png")

    async def close(self, session_id: str | None = None) -> None:
        ids = [session_id] if session_id else list(self._contexts)
        for item in ids:
            context = self._contexts.pop(item, None)
            self._pages.pop(item, None)
            if context is not None:
                await context.close()
        if not self._contexts and self._browser is not None and self._playwright is not None:
            await self._browser.close()
            await self._playwright.stop()
            self._browser = self._playwright = None


def _controller(config: dict[str, Any] | None) -> BrowserController:
    controller = (config or {}).get("browser_controller")
    if not isinstance(controller, BrowserController):
        raise RuntimeError("configure config['browser_controller'] with BrowserController")
    return controller


@tool(
    name="browser_navigate",
    description="Navigate an allowlisted browser session to a URL.",
    tags=["browser", "web"],
    capabilities=["browser_navigation"],
)
async def browser_navigate(
    url: str, session_id: str = "default", config: dict[str, Any] | None = None
) -> str:
    return json.dumps(await _controller(config).navigate(session_id, url))


@tool(
    name="browser_click",
    description="Click a CSS selector in a browser session.",
    tags=["browser"],
    capabilities=["browser_interaction"],
)
async def browser_click(
    selector: str, session_id: str = "default", config: dict[str, Any] | None = None
) -> str:
    return json.dumps(await _controller(config).click(session_id, selector))


@tool(
    name="browser_fill",
    description="Fill a form control in a browser session.",
    tags=["browser"],
    capabilities=["browser_interaction"],
)
async def browser_fill(
    selector: str, value: str, session_id: str = "default", config: dict[str, Any] | None = None
) -> str:
    return json.dumps(await _controller(config).fill(session_id, selector, value))


@tool(
    name="browser_extract",
    description="Extract bounded text from a browser page.",
    tags=["browser"],
    capabilities=["browser_read"],
)
async def browser_extract(
    selector: str | None = None, session_id: str = "default", config: dict[str, Any] | None = None
) -> str:
    return json.dumps(await _controller(config).extract(session_id, selector))


@tool(
    name="browser_screenshot",
    description="Capture a PNG screenshot from a browser session.",
    tags=["browser", "screenshot"],
    capabilities=["capture_screenshot"],
)
async def browser_screenshot(
    session_id: str = "default", full_page: bool = False, config: dict[str, Any] | None = None
) -> str:
    data = await _controller(config).screenshot(session_id, full_page=full_page)
    store = (config or {}).get("media_store")
    if store is None:
        raise RuntimeError("configure config['media_store'] for screenshot persistence")
    key = store.store(data, "image/png", {"session_id": session_id})
    key = await key if inspect.isawaitable(key) else key
    return json.dumps(
        {"kind": "screenshot", "media": store.to_media_ref(key, "image/png").model_dump()}
    )


@tool(
    name="browser_close",
    description="Close one browser session or all sessions.",
    tags=["browser"],
    capabilities=["browser_close"],
)
async def browser_close(session_id: str | None = None, config: dict[str, Any] | None = None) -> str:
    await _controller(config).close(session_id)
    return json.dumps({"closed": session_id or "all"})


__all__ = [
    "BrowserController",
    "BrowserPolicy",
    "browser_click",
    "browser_close",
    "browser_extract",
    "browser_fill",
    "browser_navigate",
    "browser_screenshot",
]
