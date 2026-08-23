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

"""Computer Use (GUI OS Control) Tool for Alcyoneus OS.

Provides computer control actions: screenshot capture, mouse movement, mouse clicks,
keyboard typing, key pressing, scrolling, and drag-and-drop. Hardened with:
- Coordinate bounds validation against the current screen size
- pyautogui failsafe enabled
- Safe text typing (per-char with special-key escaping)
- All documented actions implemented (triple_click, mouse_down/up, drag_and_drop, key_down/up)
"""

from __future__ import annotations

import base64
import io
from typing import Any, Literal

from alcyoneus.utils.decorators import tool


ComputerAction = Literal[
    "screenshot",
    "mouse_move",
    "left_click",
    "right_click",
    "double_click",
    "triple_click",
    "middle_click",
    "mouse_down",
    "mouse_up",
    "type",
    "key_press",
    "key_down",
    "key_up",
    "drag_and_drop",
    "scroll",
]

# Characters that need special-key handling when typing.
_SPECIAL_CHARS = {
    " ": "space",
    "\n": "enter",
    "\t": "tab",
    ".": "period",
    ",": "comma",
    ":": "colon",
    ";": "semicolon",
    "/": "slash",
    "\\": "backslash",
    "[": "lbracket",
    "]": "rbracket",
    "-": "minus",
    "=": "equals",
    "!": "exclaim",
    "?": "question",
    "@": "at",
    "#": "hash",
    "$": "dollar",
    "%": "percent",
    "^": "caret",
    "&": "ampersand",
    "*": "asterisk",
    "(": "leftparen",
    ")": "rightparen",
    "_": "underscore",
    "+": "plus",
    "|": "pipe",
    "~": "tilde",
    "'": "apostrophe",
    '"': "doublequote",
    "{": "leftbrace",
    "}": "rightbrace",
    "<": "less",
    ">": "greater",
}


def _load_pyautogui():
    """Import pyautogui and enable the failsafe."""
    try:
        import pyautogui
    except Exception as err:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "pyautogui package is required for computer_use tool. "
            "Install via `pip install pyautogui`."
        ) from err
    try:
        pyautogui.FAILSAFE = True
    except Exception:  # pragma: no cover - not all builds expose failsafe  # noqa: S110
        pass
    return pyautogui


def _validate_coordinate(pa, coordinate: tuple[int, int]) -> tuple[int, int]:
    """Clamp/validate a coordinate against the screen bounds."""
    width, height = pa.size()
    x, y = int(coordinate[0]), int(coordinate[1])
    if x < 0 or y < 0 or x >= width or y >= height:
        raise ValueError(f"coordinate ({x}, {y}) is outside screen bounds ({width}x{height})")
    return x, y


def _safe_type(pa, text: str) -> None:
    """Type text, mapping special characters to their key names."""
    for char in text:
        if char in _SPECIAL_CHARS:
            pa.press(_SPECIAL_CHARS[char])
        else:
            pa.write(char, interval=0.005)


@tool(
    name="computer_use",
    description="Controls computer GUI: takes screenshots, moves mouse, clicks, types text, presses keys, and scrolls.",  # noqa: E501
)
def computer_use(
    action: ComputerAction,
    coordinate: tuple[int, int] | None = None,
    text: str | None = None,
    key: str | None = None,
    scroll_amount: int | None = None,
) -> dict[str, Any]:
    """Executes OS computer GUI interaction.

        Args:
            action: The GUI action to perform (screenshot, mouse_move,
    left_click, type, key_press, etc.).
            coordinate: Optional (x, y) pixel coordinate tuple.
            text: Optional text string for typing action.
            key: Optional key name for key press action (e.g. 'Return', 'BackSpace', 'Tab').
            scroll_amount: Optional integer scroll amount (positive for up, negative for down).

        Returns:
            Dict containing action result status and optional screenshot base64.
    """
    try:
        pa = _load_pyautogui()
    except RuntimeError as err:
        return {"action": action, "status": "error", "error": str(err)}

    try:
        if action == "screenshot":
            screenshot = pa.screenshot()
            buf = io.BytesIO()
            screenshot.save(buf, format="PNG")
            b64_img = base64.b64encode(buf.getvalue()).decode("utf-8")
            return {
                "action": action,
                "status": "success",
                "image_base64": b64_img,
                "width": screenshot.width,
                "height": screenshot.height,
            }

        if action == "mouse_move" and coordinate:
            x, y = _validate_coordinate(pa, coordinate)
            pa.moveTo(x, y)
        elif action == "left_click":
            if coordinate:
                x, y = _validate_coordinate(pa, coordinate)
                pa.click(x, y, button="left")
            else:
                pa.click(button="left")
        elif action == "right_click":
            if coordinate:
                x, y = _validate_coordinate(pa, coordinate)
                pa.click(x, y, button="right")
            else:
                pa.click(button="right")
        elif action == "double_click":
            if coordinate:
                x, y = _validate_coordinate(pa, coordinate)
                pa.doubleClick(x, y)
            else:
                pa.doubleClick()
        elif action == "triple_click":
            if coordinate:
                x, y = _validate_coordinate(pa, coordinate)
                pa.tripleClick(x, y)
            else:
                pa.tripleClick()
        elif action == "middle_click":
            if coordinate:
                x, y = _validate_coordinate(pa, coordinate)
                pa.middleClick(x, y)
            else:
                pa.middleClick()
        elif action == "mouse_down":
            pa.mouseDown(
                x=None if coordinate is None else _validate_coordinate(pa, coordinate)[0],
                y=None if coordinate is None else _validate_coordinate(pa, coordinate)[1],
                button="left",
            )
        elif action == "mouse_up":
            pa.mouseUp(
                x=None if coordinate is None else _validate_coordinate(pa, coordinate)[0],
                y=None if coordinate is None else _validate_coordinate(pa, coordinate)[1],
                button="left",
            )
        elif action == "drag_and_drop" and coordinate:
            start_x, start_y = pa.position()
            end_x, end_y = _validate_coordinate(pa, coordinate)
            pa.moveTo(start_x, start_y)
            pa.dragTo(end_x, end_y, duration=0.3, button="left")
        elif action == "type" and text:
            _safe_type(pa, text)
        elif action == "key_press" and key:
            pa.press(key)
        elif action == "key_down" and key:
            pa.keyDown(key)
        elif action == "key_up" and key:
            pa.keyUp(key)
        elif action == "scroll" and scroll_amount is not None:
            pa.scroll(int(scroll_amount))
        else:
            return {
                "action": action,
                "status": "error",
                "error": f"Invalid arguments for action '{action}'.",
            }

        return {"action": action, "status": "success", "coordinate": coordinate}

    except Exception as err:
        return {"action": action, "status": "error", "error": str(err)}


class ComputerTool:
    """Class wrapper for Computer Use tool."""

    def __call__(self, action: ComputerAction, **kwargs: Any) -> dict[str, Any]:
        return computer_use(action=action, **kwargs)


__all__ = ["ComputerAction", "ComputerTool", "computer_use"]
