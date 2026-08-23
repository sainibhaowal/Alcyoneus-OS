"""Distributed Rate Limiting for Alcyoneus OS.

Redis-backed rate limiting with per-tenant/key quotas, priority queues,
and sliding window algorithms.
"""

from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import redis.asyncio as redis
from redis.asyncio import Redis

from .multitenancy import QuotaEnforcer, ResourceType, TenantRegistry


logger = logging.getLogger("alcyoneus.ratelimit")


class RateLimitAlgorithm(str, Enum):
    """Rate limiting algorithms."""

    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW = "sliding_window"
    SLIDING_WINDOW_LOG = "sliding_window_log"
    TOKEN_BUCKET = "token_bucket"  # noqa: S105
    LEAKY_BUCKET = "leaky_bucket"


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(
        self, message: str, retry_after: float, limit: int, remaining: int, reset_at: float
    ):
        super().__init__(message)
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining
        self.reset_at = reset_at


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""

    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.SLIDING_WINDOW
    requests: int = 100  # Max requests
    window_seconds: float = 60.0  # Time window
    burst: int | None = None  # Token bucket burst capacity
    refill_rate: float | None = None  # Tokens per second
    key_prefix: str = "ratelimit"
    block_duration: float = 0.0  # Seconds to block after limit exceeded


@dataclass
class RateLimitResult:
    """Result of rate limit check."""

    allowed: bool
    limit: int
    remaining: int
    reset_at: float
    retry_after: float = 0.0
    retry_after_seconds: float = 0.0


class RateLimiter(ABC):
    """Abstract rate limiter."""

    @abstractmethod
    async def check_limit(self, key: str, cost: int = 1) -> RateLimitResult:
        pass

    @abstractmethod
    async def get_current_usage(self, key: str) -> int:
        pass

    @abstractmethod
    async def reset(self, key: str) -> bool:
        pass


class FixedWindowRateLimiter(RateLimiter):
    """Fixed window rate limiter using Redis."""

    def __init__(self, redis_client: Redis, config: RateLimitConfig):
        self.redis = redis_client
        self.config = config

    def _window_key(self, key: str) -> tuple[str, int]:
        window = int(time.time() // self.config.window_seconds)
        return f"{self.config.key_prefix}:{key}:{window}", window

    async def check_limit(self, key: str, cost: int = 1) -> RateLimitResult:
        redis_key, window = self._window_key(key)
        ttl = int(self.config.window_seconds) + 1

        pipe = self.redis.pipeline()
        pipe.incrby(redis_key, cost)
        pipe.expire(redis_key, ttl)
        results = await pipe.execute()

        current = results[0]
        limit = self.config.requests
        remaining = max(0, limit - current)
        reset_at = (window + 1) * self.config.window_seconds

        if current > limit:
            retry_after = reset_at - time.time()
            return RateLimitResult(
                allowed=False,
                limit=limit,
                remaining=0,
                reset_at=reset_at,
                retry_after=retry_after,
            )

        return RateLimitResult(
            allowed=True,
            limit=limit,
            remaining=remaining,
            reset_at=reset_at,
        )

    async def get_current_usage(self, key: str) -> int:
        redis_key, _ = self._window_key(key)
        val = await self.redis.get(redis_key)
        return int(val) if val else 0

    async def reset(self, key: str) -> bool:
        redis_key, _ = self._window_key(key)
        result = await self.redis.delete(redis_key)
        return result > 0


class SlidingWindowRateLimiter(RateLimiter):
    """Sliding window rate limiter using Redis sorted sets."""

    def __init__(self, redis_client: Redis, config: RateLimitConfig):
        self.redis = redis_client
        self.config = config

    async def check_limit(self, key: str, cost: int = 1) -> RateLimitResult:
        redis_key = f"{self.config.key_prefix}:{key}"
        now = time.time()
        window_start = now - self.config.window_seconds

        pipe = self.redis.pipeline()
        # Remove expired entries
        pipe.zremrangebyscore(redis_key, 0, window_start)
        # Count current requests
        pipe.zcard(redis_key)
        # Add new request(s)
        for _ in range(cost):
            pipe.zadd(redis_key, {f"{now}:{uuid.uuid4().hex}": now})
        # Set expiry
        pipe.expire(redis_key, int(self.config.window_seconds) + 1)
        results = await pipe.execute()

        current = results[1] + cost
        limit = self.config.requests
        remaining = max(0, limit - current)
        reset_at = now + self.config.window_seconds

        if current > limit:
            # Remove the entries we just added
            await self.redis.zremrangebyscore(redis_key, now, now)
            retry_after = (
                self.config.window_seconds
                - (current - limit) / max(1, limit) * self.config.window_seconds
            )
            return RateLimitResult(
                allowed=False,
                limit=limit,
                remaining=0,
                reset_at=reset_at,
                retry_after=retry_after,
            )

        return RateLimitResult(
            allowed=True,
            limit=limit,
            remaining=remaining,
            reset_at=reset_at,
        )

    async def get_current_usage(self, key: str) -> int:
        redis_key = f"{self.config.key_prefix}:{key}"
        now = time.time()
        window_start = now - self.config.window_seconds
        await self.redis.zremrangebyscore(redis_key, 0, window_start)
        return await self.redis.zcard(redis_key)

    async def reset(self, key: str) -> bool:
        redis_key = f"{self.config.key_prefix}:{key}"
        result = await self.redis.delete(redis_key)
        return result > 0


class TokenBucketRateLimiter(RateLimiter):
    """Token bucket rate limiter with Redis."""

    def __init__(self, redis_client: Redis, config: RateLimitConfig):
        self.redis = redis_client
        self.config = config
        self.burst = config.burst or config.requests
        self.refill_rate = config.refill_rate or (config.requests / config.window_seconds)

    async def check_limit(self, key: str, cost: int = 1) -> RateLimitResult:
        redis_key = f"{self.config.key_prefix}:{key}:bucket"
        now = time.time()

        # Lua script for atomic token bucket
        lua_script = """
        local key = KEYS[1]
        local capacity = tonumber(ARGV[1])
        local refill_rate = tonumber(ARGV[2])
        local cost = tonumber(ARGV[3])
        local now = tonumber(ARGV[4])
        local ttl = tonumber(ARGV[5])

        local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
        local tokens = tonumber(bucket[1]) or capacity
        local last_refill = tonumber(bucket[2]) or now

        -- Refill tokens
        local elapsed = now - last_refill
        tokens = math.min(capacity, tokens + elapsed * refill_rate)

        local allowed = false
        local remaining = 0
        if tokens >= cost then
            tokens = tokens - cost
            allowed = true
            remaining = math.floor(tokens)
        else
            remaining = math.floor(tokens)
        end

        redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
        redis.call('EXPIRE', key, ttl)

        return {allowed and 1 or 0, remaining, capacity}
        """

        script = self.redis.register_script(lua_script)
        result = await script(
            keys=[redis_key],
            args=[self.burst, self.refill_rate, cost, now, int(self.config.window_seconds) + 1],
        )

        allowed = bool(result[0])
        remaining = int(result[1])
        limit = int(result[2])
        reset_at = (
            now + (cost - (limit - remaining)) / self.refill_rate
            if not allowed
            else now + (limit - remaining) / self.refill_rate
        )

        if not allowed:
            retry_after = (cost - (limit - remaining)) / self.refill_rate
            return RateLimitResult(
                allowed=False,
                limit=limit,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=retry_after,
            )

        return RateLimitResult(
            allowed=True,
            limit=limit,
            remaining=remaining,
            reset_at=reset_at,
        )

    async def get_current_usage(self, key: str) -> int:
        redis_key = f"{self.config.key_prefix}:{key}:bucket"
        bucket = await self.redis.hmget(redis_key, "tokens")
        tokens = float(bucket[0]) if bucket[0] else self.burst
        return self.burst - int(tokens)

    async def reset(self, key: str) -> bool:
        redis_key = f"{self.config.key_prefix}:{key}:bucket"
        result = await self.redis.delete(redis_key)
        return result > 0


class DistributedRateLimiter:
    """High-level distributed rate limiter with tenant support."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        default_config: RateLimitConfig | None = None,
        tenant_registry: TenantRegistry | None = None,
    ):
        self.redis_url = redis_url
        self.default_config = default_config or RateLimitConfig()
        self.tenant_registry = tenant_registry
        self._redis: Redis | None = None
        self._limiters: dict[str, RateLimiter] = {}

    async def _get_redis(self) -> Redis:
        if self._redis is None:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def _get_limiter(self, config: RateLimitConfig) -> RateLimiter:
        key = f"{config.algorithm}:{config.requests}:{config.window_seconds}"
        if key not in self._limiters:
            redis_client = await self._get_redis()
            if config.algorithm == RateLimitAlgorithm.FIXED_WINDOW:
                self._limiters[key] = FixedWindowRateLimiter(redis_client, config)
            elif config.algorithm == RateLimitAlgorithm.SLIDING_WINDOW:
                self._limiters[key] = SlidingWindowRateLimiter(redis_client, config)
            elif config.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
                self._limiters[key] = TokenBucketRateLimiter(redis_client, config)
            else:
                self._limiters[key] = SlidingWindowRateLimiter(redis_client, config)
        return self._limiters[key]

    async def check_limit(
        self,
        key: str,
        cost: int = 1,
        config: RateLimitConfig | None = None,
        tenant_id: str | None = None,
    ) -> RateLimitResult:
        """Check rate limit for a key."""
        cfg = config or self.default_config
        limiter = self._get_limiter(cfg)

        # Build composite key with tenant
        if tenant_id:
            composite_key = f"tenant:{tenant_id}:{key}"
        else:
            composite_key = key

        # Check tenant quota if registry available
        if self.tenant_registry and tenant_id:
            quota_enforcer = QuotaEnforcer(self.tenant_registry)
            try:
                await quota_enforcer.check_and_increment(tenant_id, ResourceType.API_REQUESTS, cost)
            except Exception:
                return RateLimitResult(
                    allowed=False,
                    limit=0,
                    remaining=0,
                    reset_at=time.time() + 60,
                    retry_after=60,
                )

        return await limiter.check_limit(composite_key, cost)

    async def check_limit_with_priority(
        self,
        key: str,
        priority: int = 5,  # 1=highest, 10=lowest
        cost: int = 1,
        config: RateLimitConfig | None = None,
    ) -> RateLimitResult:
        """Check rate limit with priority (higher priority = more lenient)."""
        cfg = config or self.default_config

        # Adjust cost based on priority (higher priority = lower effective cost)
        priority_factor = (11 - priority) / 10.0  # 1.0 for priority 1, 0.1 for priority 10
        effective_cost = max(1, int(cost / priority_factor))

        return await self.check_limit(key, effective_cost, cfg)

    async def get_usage(self, key: str, config: RateLimitConfig | None = None) -> int:
        cfg = config or self.default_config
        limiter = self._get_limiter(cfg)
        return await limiter.get_current_usage(key)

    async def reset_limit(self, key: str, config: RateLimitConfig | None = None) -> bool:
        cfg = config or self.default_config
        limiter = self._get_limiter(cfg)
        return await limiter.reset(key)

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._redis = None


class RateLimitMiddleware:
    """ASGI middleware for rate limiting."""

    def __init__(
        self,
        app,
        rate_limiter: DistributedRateLimiter,
        key_extractor: Callable[[dict], str] | None = None,
        excluded_paths: list[str] = None,
        default_config: RateLimitConfig | None = None,
    ):
        self.app = app
        self.rate_limiter = rate_limiter
        self.key_extractor = key_extractor or self._default_key_extractor
        self.excluded_paths = excluded_paths or ["/health", "/ready", "/metrics"]
        self.default_config = default_config

    def _default_key_extractor(self, scope: dict) -> str:
        """Extract rate limit key from request scope."""
        client = scope.get("client")
        if client:
            return f"ip:{client[0]}"
        return "unknown"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path.startswith(p) for p in self.excluded_paths):
            await self.app(scope, receive, send)
            return

        key = self.key_extractor(scope)
        result = await self.rate_limiter.check_limit(key, config=self.default_config)

        # Add rate limit headers
        headers = [
            (b"x-ratelimit-limit", str(result.limit).encode()),
            (b"x-ratelimit-remaining", str(result.remaining).encode()),
            (b"x-ratelimit-reset", str(int(result.reset_at)).encode()),
        ]

        if not result.allowed:
            headers.append((b"retry-after", str(int(result.retry_after)).encode()))
            await self._send_error(send, 429, "Rate limit exceeded", headers)
            return

        # Wrap send to add headers
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                message["headers"] = message.get("headers", []) + headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

    async def _send_error(self, send, status: int, message: str, headers: list):
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": headers + [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps(
                    {
                        "error": message,
                        "retry_after": headers[3][1].decode() if len(headers) > 3 else "60",
                    }
                ).encode(),
            }
        )


import json  # noqa: E402


__all__ = [
    "DistributedRateLimiter",
    "FixedWindowRateLimiter",
    "QuotaEnforcer",
    "RateLimitAlgorithm",
    "RateLimitConfig",
    "RateLimitExceeded",
    "RateLimitMiddleware",
    "RateLimitResult",
    "RateLimiter",
    "SlidingWindowRateLimiter",
    "TokenBucketRateLimiter",
]
