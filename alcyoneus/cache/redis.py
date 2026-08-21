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

"""Distributed Redis cache implementation."""

from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseCache
from .memory import InMemoryCache


logger = logging.getLogger("alcyoneus.cache.redis")


class RedisCache(BaseCache):
    """Production-grade Redis-backed distributed cache store."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        default_ttl: int | None = 86400,
        redis_client: Any | None = None,
    ) -> None:
        self.redis_url = redis_url
        self.default_ttl = default_ttl
        self._client = redis_client
        self._fallback = InMemoryCache(default_ttl=default_ttl)

    def _get_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        try:
            import redis

            self._client = redis.from_url(self.redis_url)
            return self._client
        except Exception:
            logger.debug("redis package unavailable, using fallback in-memory store")
            return None

    def get(self, key: str) -> Any | None:
        client = self._get_client()
        if client is None:
            return self._fallback.get(key)
        try:
            val = client.get(f"cache:{key}")
            if val is None:
                return None
            decoded = val.decode("utf-8") if isinstance(val, bytes) else val
            try:
                return json.loads(decoded)
            except Exception:
                return decoded
        except Exception as err:
            logger.warning("RedisCache get failed (%s), using fallback", err)
            return self._fallback.get(key)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        client = self._get_client()
        if client is None:
            self._fallback.set(key, value, ttl=ttl)
            return
        try:
            eff_ttl = ttl if ttl is not None else self.default_ttl
            val_str = json.dumps(value) if not isinstance(value, str) else value
            if eff_ttl:
                client.setex(f"cache:{key}", eff_ttl, val_str)
            else:
                client.set(f"cache:{key}", val_str)
        except Exception as err:
            logger.warning("RedisCache set failed (%s), using fallback", err)
            self._fallback.set(key, value, ttl=ttl)

    def clear(self) -> None:
        client = self._get_client()
        if client is None:
            self._fallback.clear()
            return
        try:
            keys = client.keys("cache:*")
            if keys:
                client.delete(*keys)
        except Exception as err:
            logger.warning("RedisCache clear failed (%s)", err)
            self._fallback.clear()


__all__ = ["RedisCache"]
