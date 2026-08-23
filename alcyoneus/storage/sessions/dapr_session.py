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

"""Dapr state store session backend for cloud-native microservices."""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

from .base import Session, SessionABC, SessionSettings


logger = logging.getLogger("alcyoneus.storage.sessions.dapr")


class DaprSession(SessionABC):
    """Production-grade Dapr HTTP/gRPC state store session storage backend."""

    def __init__(
        self,
        session_id: str,
        state_store_name: str = "statestore",
        dapr_http_port: int = 3500,
        settings: SessionSettings | None = None,
    ) -> None:
        super().__init__(session_id, settings)
        self.state_store_name = state_store_name
        self.dapr_http_port = dapr_http_port
        self.dapr_url = f"http://localhost:{dapr_http_port}/v1.0/state/{state_store_name}"
        self._fallback_memory = Session(session_id, settings)

    async def get_items(self) -> list[Any]:
        url = f"{self.dapr_url}/session_{self.session_id}"
        try:
            req = urllib.request.Request(url, method="GET")  # noqa: S310  # nosec: B310
            with urllib.request.urlopen(req, timeout=3) as resp:  # noqa: S310
                if resp.status == 200:
                    data = resp.read().decode("utf-8")
                    if data:
                        parsed = json.loads(data)
                        return parsed if isinstance(parsed, list) else [parsed]
        except Exception as err:
            logger.debug("Dapr state store read fallback (%s)", err)
        return await self._fallback_memory.get_items()

    async def add_items(self, items: list[Any]) -> None:
        url = f"{self.dapr_url}"
        try:
            current = await self.get_items()
            updated = current + items
            payload = json.dumps([{"key": f"session_{self.session_id}", "value": updated}]).encode(
                "utf-8"
            )
            req = urllib.request.Request(  # noqa: S310  # nosec: B310
                url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(req, timeout=3) as resp:  # noqa: S310  # nosec: B310
                if resp.status in (200, 204):
                    return
        except Exception as err:
            logger.debug("Dapr state store write fallback (%s)", err)
        await self._fallback_memory.add_items(items)

    async def clear(self) -> None:
        url = f"{self.dapr_url}/session_{self.session_id}"
        try:
            req = urllib.request.Request(url, method="DELETE")  # noqa: S310
            with urllib.request.urlopen(req, timeout=3) as resp:  # noqa: S310  # nosec: B310
                if resp.status in (200, 204):
                    return
        except Exception as err:
            logger.debug("Dapr state store delete fallback (%s)", err)
        await self._fallback_memory.clear()


__all__ = ["DaprSession"]
