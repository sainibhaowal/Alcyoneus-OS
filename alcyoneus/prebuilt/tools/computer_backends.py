# Copyright 2026 Alcyoneus Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Computer Use backends: X11 (pyautogui), Wayland (ydotool/wlroot), VNC (vncdotool),
headless (xvfb), remote desktop streaming, and accessibility API integrations."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


logger = logging.getLogger("alcyoneus.computer.backends")


@dataclass
class ScreenInfo:
    width: int
    height: int
    backend: str
    display: str | None = None


class ComputerBackend(ABC):
    """Abstract computer-use backend."""

    @abstractmethod
    async def initialize(self) -> None: ...

    @abstractmethod
    async def get_screen_info(self) -> ScreenInfo: ...

    @abstractmethod
    async def screenshot(self) -> bytes: ...

    @abstractmethod
    async def mouse_move(self, x: int, y: int) -> None: ...

    @abstractmethod
    async def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None: ...

    @abstractmethod
    async def type_text(self, text: str) -> None: ...

    @abstractmethod
    async def press_key(self, key: str) -> None: ...

    @abstractmethod
    async def scroll(self, amount: int) -> None: ...

    @abstractmethod
    async def shutdown(self) -> None: ...


class X11Backend(ComputerBackend):
    """X11 backend using pyautogui."""

    def __init__(self) -> None:
        self._pa = None

    async def initialize(self) -> None:
        import pyautogui

        try:
            pyautogui.FAILSAFE = True
        except Exception:  # noqa: S110
            pass
        self._pa = pyautogui

    async def get_screen_info(self) -> ScreenInfo:
        w, h = self._pa.size()
        return ScreenInfo(width=w, height=h, backend="x11", display=os.environ.get("DISPLAY"))

    async def screenshot(self) -> bytes:
        img = self._pa.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    async def mouse_move(self, x: int, y: int) -> None:
        self._pa.moveTo(x, y)

    async def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        if clicks == 2:
            self._pa.doubleClick(x, y, button=button)
        elif clicks == 3:
            self._pa.tripleClick(x, y)
        else:
            self._pa.click(x, y, button=button, clicks=clicks)

    async def type_text(self, text: str) -> None:
        self._pa.write(text, interval=0.005)

    async def press_key(self, key: str) -> None:
        self._pa.press(key)

    async def scroll(self, amount: int) -> None:
        self._pa.scroll(int(amount))

    async def shutdown(self) -> None:
        pass


class WaylandBackend(ComputerBackend):
    """Wayland backend using ydotool (input) and grim/wl-screenrec/wayland-screenshot (capture)."""

    def __init__(self) -> None:
        self._display = os.environ.get("WAYLAND_DISPLAY", "wayland-0")

    def _check_tool(self, tool: str) -> str | None:
        from shutil import which

        return which(tool)

    async def initialize(self) -> None:
        if not self._check_tool("ydotool"):
            raise RuntimeError("ydotool not installed; install ydotool for Wayland input")
        # ydotool needs the ydotoold daemon running
        try:
            subprocess.run(["ydotool", "version"], check=True, capture_output=True, timeout=2)  # noqa: S607
        except Exception as exc:
            logger.debug("ydotool check failed: %s", exc)

    async def get_screen_info(self) -> ScreenInfo:
        # Use wlr-randr or parse grim output
        info = subprocess.run(
            ["grim", "-g", "0,0+0+0", "/tmp/_grim_test.png"], capture_output=True, timeout=5  # noqa: S108,S607
        )
        if info.returncode == 0:
            try:
                from PIL import Image

                img = Image.open("/tmp/_grim_test.png")  # noqa: S108
                w, h = img.size
                return ScreenInfo(width=w, height=h, backend="wayland", display=self._display)
            except Exception:  # noqa: S110
                pass
        return ScreenInfo(width=1920, height=1080, backend="wayland", display=self._display)

    async def screenshot(self) -> bytes:
        out = subprocess.run(["grim", "-"], capture_output=True, timeout=10)  # noqa: S607
        return out.stdout

    async def mouse_move(self, x: int, y: int) -> None:
        subprocess.run(["ydotool", "mousemove", "-a", str(x), str(y)], check=False, timeout=5)  # noqa: S607,S603

    async def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        # Move then click
        await self.mouse_move(x, y)
        for _ in range(clicks):
            subprocess.run(["ydotool", "click", button], check=False, timeout=5)  # noqa: S607,S603
            time.sleep(0.05)

    async def type_text(self, text: str) -> None:
        subprocess.run(["ydotool", "type", "--", text], check=False, timeout=10)  # noqa: S607,S603

    async def press_key(self, key: str) -> None:
        subprocess.run(["ydotool", "key", key], check=False, timeout=5)  # noqa: S607,S603

    async def scroll(self, amount: int) -> None:
        direction = "scroll" if amount > 0 else "scrollback"
        subprocess.run(["ydotool", direction, str(abs(int(amount)))], check=False, timeout=5)  # noqa: S607,S603

    async def shutdown(self) -> None:
        pass


class HeadlessBackend(ComputerBackend):
    """Headless backend using Xvfb + X11 tools."""

    def __init__(self, display: str = ":99", width: int = 1920, height: int = 1080) -> None:
        self.display = display
        self.width = width
        self.height = height
        self._xvfb_proc: subprocess.Popen | None = None

    async def initialize(self) -> None:
        from shutil import which

        if which("Xvfb") is None:
            raise RuntimeError("Xvfb not installed")
        os.environ["DISPLAY"] = self.display
        self._xvfb_proc = subprocess.Popen(  # noqa: S603
            ["Xvfb", self.display, "-screen", "0", f"{self.width}x{self.height}x24"],  # noqa: S607
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1)
        # Switch to X11 backend
        self._inner = X11Backend()
        await self._inner.initialize()

    async def get_screen_info(self) -> ScreenInfo:
        return ScreenInfo(
            width=self.width, height=self.height, backend="headless", display=self.display
        )

    async def screenshot(self) -> bytes:
        return await self._inner.screenshot()

    async def mouse_move(self, x: int, y: int) -> None:
        await self._inner.mouse_move(x, y)

    async def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        await self._inner.click(x, y, button=button, clicks=clicks)

    async def type_text(self, text: str) -> None:
        await self._inner.type_text(text)

    async def press_key(self, key: str) -> None:
        await self._inner.press_key(key)

    async def scroll(self, amount: int) -> None:
        await self._inner.scroll(amount)

    async def shutdown(self) -> None:
        if self._xvfb_proc:
            self._xvfb_proc.terminate()
            self._xvfb_proc.wait()


class VNCBackend(ComputerBackend):
    """VNC client backend using vncdotool for remote desktop control."""

    def __init__(self, host: str, port: int = 5900, password: str | None = None) -> None:
        self.host = host
        self.port = port
        self.password = password
        self._client = None

    async def initialize(self) -> None:
        try:
            from vncdotool import api as vnc_api

            loop = asyncio.get_event_loop()
            # vncdotool is sync; we wrap with run_in_executor
            self._client = await loop.run_in_executor(
                None, lambda: vnc_api.connect(f"{self.host}::{self.port}", password=self.password)
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to connect VNC: {exc}")

    async def get_screen_info(self) -> ScreenInfo:
        # VNC doesn't natively expose size without capturing
        screen = await self.screenshot()
        import io as _io

        from PIL import Image

        img = Image.open(_io.BytesIO(screen))
        return ScreenInfo(
            width=img.width, height=img.height, backend="vnc", display=f"{self.host}:{self.port}"
        )

    async def screenshot(self) -> bytes:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._client.captureScreen)

    async def mouse_move(self, x: int, y: int) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._client.mouseMove(x, y))

    async def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        loop = asyncio.get_event_loop()
        for _ in range(clicks):
            await loop.run_in_executor(None, lambda: self._client.mousePress(button))
            time.sleep(0.05)

    async def type_text(self, text: str) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._client.sendText(text))

    async def press_key(self, key: str) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._client.keyPress(key))

    async def scroll(self, amount: int) -> None:
        # VNC protocol doesn't have native scroll; emulate
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._client.mouseWheel(abs(int(amount))))

    async def shutdown(self) -> None:
        if self._client:
            try:
                self._client.disconnect()
            except Exception:  # noqa: S110
                pass


class RemoteDesktopStreamer:
    """Stream desktop to remote viewers via WebRTC/HTTP."""

    def __init__(self, backend: ComputerBackend, port: int = 8080) -> None:
        self.backend = backend
        self.port = port
        self._streams: dict[str, asyncio.Queue[bytes]] = {}

    async def add_viewer(self, viewer_id: str) -> asyncio.Queue[bytes]:
        q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=30)
        self._streams[viewer_id] = q
        return q

    async def remove_viewer(self, viewer_id: str) -> None:
        self._streams.pop(viewer_id, None)

    async def broadcast_frame(self, frame: bytes) -> None:
        for q in self._streams.values():
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
                pass

    async def stream_loop(self, fps: int = 10) -> None:
        while True:
            frame = await self.backend.screenshot()
            await self.broadcast_frame(frame)
            await asyncio.sleep(1.0 / fps)


class AccessibilityBridge:
    """Accessibility API bridge for inspecting UI elements (AT-SPI on Linux, UIA on Windows)."""

    def __init__(self) -> None:
        self._platform = os.name  # 'posix' or 'nt'

    async def get_focused_element(self) -> dict[str, Any] | None:
        if self._platform == "posix":
            return await self._atspi_focused()
        return None

    async def _atspi_focused(self) -> dict[str, Any] | None:
        # Use AT-SPI via D-Bus
        try:
            import subprocess

            result = subprocess.run(
                [  # noqa: S607
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    "org.a11y.Bus",
                    "--object-path",
                    "/org/a11y/bus",
                    "--method",
                    "org.a11y.Bus.GetAddress",
                ],
                capture_output=True,
                timeout=2,
            )
            if result.returncode == 0:
                return {"backend": "atspi", "bus": result.stdout.decode()}
        except Exception:  # noqa: S110
            pass
        return None

    async def enumerate_windows(self) -> list[dict[str, Any]]:
        try:
            import subprocess

            result = subprocess.run(
                ["xdotool", "search", "--name", ""], capture_output=True, timeout=2  # noqa: S607
            )
            if result.returncode == 0:
                ids = result.stdout.decode().splitlines()
                return [{"xdotool_id": int(i), "backend": "x11"} for i in ids if i.strip()]
        except Exception:  # noqa: S110
            pass
        return []


class ActionVerifier:
    """Verify GUI actions succeeded via screenshot diffing."""

    @staticmethod
    def diff_screenshots(before: bytes, after: bytes, threshold: float = 0.02) -> float:
        """Return change ratio (0-1). >threshold = changed."""
        try:
            import io as _io

            from PIL import Image, ImageChops

            a = Image.open(_io.BytesIO(before)).convert("RGB")
            b = Image.open(_io.BytesIO(after)).convert("RGB")
            if a.size != b.size:
                return 1.0
            diff = ImageChops.difference(a, b)
            hist = diff.histogram()
            total = sum(hist)
            non_zero = sum(hist[i] for i in range(1, 256))
            return non_zero / max(total, 1)
        except Exception:
            return 0.0

    @staticmethod
    async def verify_action(
        backend: ComputerBackend, before: bytes, after: bytes, min_change: float = 0.005
    ) -> bool:
        diff = ActionVerifier.diff_screenshots(before, after)
        return diff > min_change


__all__ = [
    "AccessibilityBridge",
    "ActionVerifier",
    "ComputerBackend",
    "HeadlessBackend",
    "RemoteDesktopStreamer",
    "ScreenInfo",
    "VNCBackend",
    "WaylandBackend",
    "X11Backend",
]
