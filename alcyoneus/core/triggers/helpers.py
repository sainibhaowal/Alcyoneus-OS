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

"""Helper factories for common trigger patterns (intervals, file watching)."""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Awaitable, Callable, Sequence

from alcyoneus.core.triggers import triggers as triggers_module


_WATCHFILES_CHANGE_MAP = {
    1: triggers_module.FileChangeKind.ADDED,
    2: triggers_module.FileChangeKind.MODIFIED,
    3: triggers_module.FileChangeKind.DELETED,
}


def every(
    interval_seconds: float,
    callback: Callable[[triggers_module.TriggerContext], Awaitable[None]],
) -> triggers_module.Trigger:
    """Creates a trigger that invokes `callback` repeatedly every `interval_seconds`."""
    if interval_seconds <= 0:
        raise ValueError(f"interval_seconds must be positive, got {interval_seconds}")

    async def _trigger(ctx: triggers_module.TriggerContext) -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            await callback(ctx)

    _trigger.__name__ = f"every_{interval_seconds}s"
    _trigger.__doc__ = f"Interval trigger: runs every {interval_seconds}s."
    return _trigger


def on_file_change(
    path: str | pathlib.Path,
    callback: Callable[
        [triggers_module.TriggerContext, Sequence[triggers_module.FileChange]],
        Awaitable[None],
    ],
) -> triggers_module.Trigger:
    """Creates a trigger that calls `callback` whenever files under `path` change."""
    watch_path = str(path)

    async def _trigger(ctx: triggers_module.TriggerContext) -> None:
        try:
            import watchfiles
        except ImportError:
            raise ImportError(
                "watchfiles package is required for on_file_change trigger. Install via `pip install watchfiles`."  # noqa: E501
            )

        async for changes in watchfiles.awatch(watch_path):
            file_changes = []
            for change_type, file_path in changes:
                kind = _WATCHFILES_CHANGE_MAP.get(
                    int(change_type), triggers_module.FileChangeKind.MODIFIED
                )
                file_changes.append(triggers_module.FileChange(kind=kind, path=file_path))

            if file_changes:
                await callback(ctx, file_changes)

    _trigger.__name__ = f"on_file_change_{pathlib.Path(path).name}"
    _trigger.__doc__ = f"File change trigger watching {path}."
    return _trigger


__all__ = ["every", "on_file_change"]
