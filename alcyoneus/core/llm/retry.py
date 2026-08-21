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

"""Retry policy system and exponential backoff configuration for LLM calls."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeAlias


@dataclass
class ModelRetryBackoffSettings:
    """Configuration for exponential backoff during model call retries."""

    initial_delay: float = 1.0
    """Initial delay in seconds before first retry."""

    max_delay: float = 60.0
    """Maximum cap on delay between retries in seconds."""

    multiplier: float = 2.0
    """Multiplier factor applied after each failed attempt."""

    jitter: bool = True
    """Whether to apply random jitter to delay times."""

    def compute_delay(self, attempt: int) -> float:
        """Compute backoff delay for given attempt index (1-based)."""
        delay = self.initial_delay * (self.multiplier ** (attempt - 1))
        delay = min(delay, self.max_delay)
        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)  # noqa: S311
        return delay


@dataclass
class ModelRetryNormalizedError:
    """Normalized error details exposed to retry policies."""

    status_code: int | None = None
    error_code: str | None = None
    message: str | None = None
    is_network_error: bool = False
    is_timeout: bool = False
    is_rate_limit: bool = False


@dataclass
class RetryDecision:
    """Result of evaluating a retry policy."""

    retry: bool
    delay: float | None = None
    reason: str | None = None


@dataclass
class RetryPolicyContext:
    """Context passed to a RetryPolicy function."""

    error: Exception
    attempt: int
    max_retries: int
    normalized_error: ModelRetryNormalizedError


RetryPolicy: TypeAlias = Callable[[RetryPolicyContext], bool | RetryDecision]


@dataclass
class ModelRetrySettings:
    """Complete retry configuration for an LLM provider or runner."""

    max_retries: int = 3
    backoff: ModelRetryBackoffSettings = field(default_factory=ModelRetryBackoffSettings)
    retry_policy: RetryPolicy | None = None


def default_retry_policy(ctx: RetryPolicyContext) -> RetryDecision:
    """Default policy retrying on network errors, timeouts, and 429/5xx status codes."""
    if ctx.attempt > ctx.max_retries:
        return RetryDecision(retry=False, reason="Max retries exceeded")

    norm = ctx.normalized_error
    if norm.is_network_error or norm.is_timeout or norm.is_rate_limit:
        return RetryDecision(retry=True, reason="Transient network/rate-limit error")

    if norm.status_code and (norm.status_code == 429 or norm.status_code >= 500):
        return RetryDecision(retry=True, reason=f"HTTP status {norm.status_code}")

    return RetryDecision(retry=False, reason="Non-retryable error")


__all__ = [
    "ModelRetryBackoffSettings",
    "ModelRetryNormalizedError",
    "ModelRetrySettings",
    "RetryDecision",
    "RetryPolicy",
    "RetryPolicyContext",
    "default_retry_policy",
]
