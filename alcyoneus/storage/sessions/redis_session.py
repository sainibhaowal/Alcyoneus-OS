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

"""Redis-backed session storage backend for high-performance distributed sessions."""

from __future__ import annotations

import json
import logging
from typing import Any

from .base import Session, SessionABC, SessionSettings


logger = logging.getLogger("alcyoneus.storage.sessions.redis")


class RedisSession(SessionABC):
    """Production-grade Redis list-backed session storage backend."""

    def __init__(
        self,
        session_id: str,
        redis_url: str = "redis://localhost:6379/0",
        ttl_seconds: int | None = 86400,
        settings: SessionSettings | None = None,
        redis_client: Any | None = None,
    ) -> None:
        super().__init__(session_id, settings)
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self.redis_key = f"alcyoneus:session:{session_id}"
        self._client = redis_client
        self._fallback_memory = Session(session_id, settings)

    async def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(self.redis_url)
            return self._client
        except ImportError:
            logger.debug("redis-py not installed, using in-memory store")
            return None

    async def get_items(self) -> list[Any]:
        client = await self._get_client()
        if client is None:
            return await self._fallback_memory.get_items()
        try:
            raw_items = await client.lrange(self.redis_key, 0, -1)
            result = []
            for item in raw_items:
                decoded = item.decode("utf-8") if isinstance(item, bytes) else item
                try:
                    result.append(json.loads(decoded))
                except Exception:
                    result.append(decoded)
            return result
        except Exception as err:
            logger.warning("Redis get_items failed (%s), falling back to memory", err)
            return await self._fallback_memory.get_items()

    async def add_items(self, items: list[Any]) -> None:
        client = await self._get_client()
        if client is None:
            await self._fallback_memory.add_items(items)
            return
        try:
            dumped = [json.dumps(i) if not isinstance(i, str) else i for i in items]
            if dumped:
                await client.rpush(self.redis_key, *dumped)
                if self.ttl_seconds:
                    await client.expire(self.redis_key, self.ttl_seconds)
        except Exception as err:
            logger.warning("Redis add_items failed (%s), falling back to memory", err)
            await self._fallback_memory.add_items(items)

    async def clear(self) -> None:
        client = await self._get_client()
        if client is None:
            await self._fallback_memory.clear()
            return
        try:
            await client.delete(self.redis_key)
        except Exception as err:
            logger.warning("Redis clear failed (%s)", err)
            await self._fallback_memory.clear()


__all__ = ["RedisSession"]
