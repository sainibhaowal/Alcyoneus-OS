"""Multi-tenancy support for Alcyoneus OS.

Provides tenant isolation, quota enforcement, RBAC, and per-tenant checkpointer/store.
"""

from __future__ import annotations

import asyncio
import contextvars
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from alcyoneus.storage.checkpointer import BaseCheckpointer
from alcyoneus.storage.store import BaseStore


class TenantTier(str, Enum):
    """Tenant subscription tiers."""

    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class ResourceType(str, Enum):
    """Resource types for quota tracking."""

    GRAPH_RUNS = "graph_runs"
    LLM_CALLS = "llm_calls"
    LLM_TOKENS = "llm_tokens"
    TOOL_CALLS = "tool_calls"
    STORAGE_BYTES = "storage_bytes"
    CHECKPOINT_COUNT = "checkpoint_count"
    CONCURRENT_SESSIONS = "concurrent_sessions"
    API_REQUESTS = "api_requests"


@dataclass
class TenantQuota:
    """Quota limits for a tenant."""

    tier: TenantTier = TenantTier.FREE
    limits: dict[ResourceType, int] = field(default_factory=dict)
    custom_limits: dict[str, int] = field(default_factory=dict)

    # Default limits per tier
    TIER_DEFAULTS = {
        TenantTier.FREE: {
            ResourceType.GRAPH_RUNS: 1000,
            ResourceType.LLM_CALLS: 10000,
            ResourceType.LLM_TOKENS: 1_000_000,
            ResourceType.TOOL_CALLS: 5000,
            ResourceType.STORAGE_BYTES: 100 * 1024 * 1024,  # 100MB
            ResourceType.CHECKPOINT_COUNT: 100,
            ResourceType.CONCURRENT_SESSIONS: 5,
            ResourceType.API_REQUESTS: 10000,
        },
        TenantTier.STARTER: {
            ResourceType.GRAPH_RUNS: 10000,
            ResourceType.LLM_CALLS: 100000,
            ResourceType.LLM_TOKENS: 10_000_000,
            ResourceType.TOOL_CALLS: 50000,
            ResourceType.STORAGE_BYTES: 1024 * 1024 * 1024,  # 1GB
            ResourceType.CHECKPOINT_COUNT: 1000,
            ResourceType.CONCURRENT_SESSIONS: 20,
            ResourceType.API_REQUESTS: 100000,
        },
        TenantTier.PROFESSIONAL: {
            ResourceType.GRAPH_RUNS: 100000,
            ResourceType.LLM_CALLS: 1_000_000,
            ResourceType.LLM_TOKENS: 100_000_000,
            ResourceType.TOOL_CALLS: 500000,
            ResourceType.STORAGE_BYTES: 10 * 1024 * 1024 * 1024,  # 10GB
            ResourceType.CHECKPOINT_COUNT: 10000,
            ResourceType.CONCURRENT_SESSIONS: 100,
            ResourceType.API_REQUESTS: 1_000_000,
        },
        TenantTier.ENTERPRISE: {
            ResourceType.GRAPH_RUNS: -1,  # Unlimited
            ResourceType.LLM_CALLS: -1,
            ResourceType.LLM_TOKENS: -1,
            ResourceType.TOOL_CALLS: -1,
            ResourceType.STORAGE_BYTES: -1,
            ResourceType.CHECKPOINT_COUNT: -1,
            ResourceType.CONCURRENT_SESSIONS: -1,
            ResourceType.API_REQUESTS: -1,
        },
    }

    def __post_init__(self):
        defaults = self.TIER_DEFAULTS.get(self.tier, {})
        for rt, limit in defaults.items():
            if rt not in self.limits:
                self.limits[rt] = limit

    def get_limit(self, resource: ResourceType) -> int:
        return self.limits.get(resource, 0)

    def is_unlimited(self, resource: ResourceType) -> bool:
        return self.get_limit(resource) < 0


@dataclass
class TenantUsage:
    """Current usage for a tenant."""

    tenant_id: str
    usage: dict[ResourceType, int] = field(default_factory=dict)
    last_reset: float = field(default_factory=time.time)
    period: str = "monthly"  # monthly, daily, hourly

    def get_usage(self, resource: ResourceType) -> int:
        return self.usage.get(resource, 0)

    def increment(self, resource: ResourceType, amount: int = 1) -> int:
        self.usage[resource] = self.usage.get(resource, 0) + amount
        return self.usage[resource]

    def check_quota(self, quota: TenantQuota, resource: ResourceType, amount: int = 1) -> bool:
        """Check if adding amount would exceed quota."""
        limit = quota.get_limit(resource)
        if limit < 0:  # Unlimited
            return True
        current = self.get_usage(resource)
        return current + amount <= limit

    def reset_if_needed(self) -> None:
        """Reset usage based on period."""
        now = time.time()
        if (
            (self.period == "daily" and now - self.last_reset > 86400)
            or (self.period == "hourly" and now - self.last_reset > 3600)
            or (self.period == "monthly" and now - self.last_reset > 2592000)
        ):
            self.usage.clear()
            self.last_reset = now


class Permission(str, Enum):
    """RBAC permissions."""

    GRAPH_READ = "graph:read"
    GRAPH_WRITE = "graph:write"
    GRAPH_EXECUTE = "graph:execute"
    GRAPH_DELETE = "graph:delete"
    TENANT_ADMIN = "tenant:admin"
    USER_MANAGE = "user:manage"
    QUOTA_VIEW = "quota:view"
    QUOTA_MANAGE = "quota:manage"
    AUDIT_VIEW = "audit:view"
    SYSTEM_ADMIN = "system:admin"


class Role(str, Enum):
    """Predefined roles."""

    VIEWER = "viewer"
    DEVELOPER = "developer"
    ADMIN = "admin"
    OWNER = "owner"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.VIEWER: {Permission.GRAPH_READ, Permission.QUOTA_VIEW},
    Role.DEVELOPER: {
        Permission.GRAPH_READ,
        Permission.GRAPH_WRITE,
        Permission.GRAPH_EXECUTE,
        Permission.QUOTA_VIEW,
    },
    Role.ADMIN: {
        Permission.GRAPH_READ,
        Permission.GRAPH_WRITE,
        Permission.GRAPH_EXECUTE,
        Permission.GRAPH_DELETE,
        Permission.USER_MANAGE,
        Permission.QUOTA_VIEW,
        Permission.QUOTA_MANAGE,
        Permission.AUDIT_VIEW,
    },
    Role.OWNER: set(Permission),  # All permissions
}


@dataclass
class Tenant:
    """Tenant configuration."""

    id: str
    name: str
    tier: TenantTier = TenantTier.FREE
    quota: TenantQuota = field(default_factory=TenantQuota)
    usage: TenantUsage | None = None
    roles: dict[str, Role] = field(default_factory=dict)  # user_id -> role
    settings: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    active: bool = True

    def __post_init__(self):
        if self.usage is None:
            self.usage = TenantUsage(tenant_id=self.id)
        self.quota.tier = self.tier

    def has_permission(self, user_id: str, permission: Permission) -> bool:
        role = self.roles.get(user_id, Role.VIEWER)
        return permission in ROLE_PERMISSIONS.get(role, set())

    def assign_role(self, user_id: str, role: Role) -> None:
        self.roles[user_id] = role
        self.updated_at = time.time()

    def revoke_role(self, user_id: str) -> None:
        self.roles.pop(user_id, None)
        self.updated_at = time.time()


class TenantRegistry:
    """Registry for managing tenants."""

    def __init__(self):
        self._tenants: dict[str, Tenant] = {}
        self._lock = asyncio.Lock()

    async def create_tenant(
        self,
        tenant_id: str,
        name: str,
        tier: TenantTier = TenantTier.FREE,
        owner_id: str | None = None,
    ) -> Tenant:
        async with self._lock:
            if tenant_id in self._tenants:
                raise ValueError(f"Tenant {tenant_id} already exists")
            tenant = Tenant(id=tenant_id, name=name, tier=tier)
            if owner_id:
                tenant.assign_role(owner_id, Role.OWNER)
            self._tenants[tenant_id] = tenant
            return tenant

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        return self._tenants.get(tenant_id)

    async def update_tenant(self, tenant_id: str, **kwargs) -> Tenant | None:
        async with self._lock:
            tenant = self._tenants.get(tenant_id)
            if tenant:
                for k, v in kwargs.items():
                    if hasattr(tenant, k):
                        setattr(tenant, k, v)
                tenant.updated_at = time.time()
            return tenant

    async def delete_tenant(self, tenant_id: str) -> bool:
        async with self._lock:
            if tenant_id in self._tenants:
                del self._tenants[tenant_id]
                return True
            return False

    async def list_tenants(self, active_only: bool = True) -> list[Tenant]:
        tenants = list(self._tenants.values())
        if active_only:
            tenants = [t for t in tenants if t.active]
        return tenants


class QuotaEnforcer:
    """Enforces tenant quotas."""

    def __init__(self, registry: TenantRegistry):
        self.registry = registry

    async def check_and_increment(
        self,
        tenant_id: str,
        resource: ResourceType,
        amount: int = 1,
    ) -> bool:
        """Check quota and increment usage atomically."""
        tenant = await self.registry.get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")

        tenant.usage.reset_if_needed()

        if not tenant.usage.check_quota(tenant.quota, resource, amount):
            raise QuotaExceededError(
                f"Quota exceeded for {resource.value}: "
                f"limit={tenant.quota.get_limit(resource)}, "
                f"current={tenant.usage.get_usage(resource)}, "
                f"requested={amount}"
            )

        tenant.usage.increment(resource, amount)
        return True

    async def get_usage(self, tenant_id: str) -> dict[str, Any]:
        """Get current usage for tenant."""
        tenant = await self.registry.get_tenant(tenant_id)
        if not tenant:
            return {}
        return {
            "tenant_id": tenant_id,
            "tier": tenant.tier.value,
            "usage": {k.value: v for k, v in tenant.usage.usage.items()},
            "limits": {k.value: v for k, v in tenant.quota.limits.items()},
            "period": tenant.usage.period,
        }


class QuotaExceededError(Exception):
    """Raised when quota is exceeded."""


class TenantAwareCheckpointer(BaseCheckpointer):
    """Checkpointer wrapper that isolates checkpoints per tenant."""

    def __init__(self, base_checkpointer: BaseCheckpointer, tenant_id: str):
        self.base = base_checkpointer
        self.tenant_id = tenant_id

    def _tenant_key(self, key: str) -> str:
        return f"tenant:{self.tenant_id}:{key}"

    async def put(self, key: str, value: bytes) -> None:
        await self.base.put(self._tenant_key(key), value)

    async def get(self, key: str) -> bytes | None:
        return await self.base.get(self._tenant_key(key))

    async def delete(self, key: str) -> None:
        await self.base.delete(self._tenant_key(key))

    async def list(self, prefix: str = "") -> list[str]:
        return await self.base.list(f"tenant:{self.tenant_id}:{prefix}")


class TenantAwareStore(BaseStore):
    """Store wrapper that isolates data per tenant."""

    def __init__(self, base_store: BaseStore, tenant_id: str):
        self.base = base_store
        self.tenant_id = tenant_id

    def _tenant_key(self, key: str) -> str:
        return f"tenant:{self.tenant_id}:{key}"

    async def put(self, key: str, value: bytes, metadata: dict | None = None) -> str:
        return await self.base.put(self._tenant_key(key), value, metadata)

    async def get(self, key: str) -> bytes | None:
        return await self.base.get(self._tenant_key(key))

    async def delete(self, key: str) -> bool:
        return await self.base.delete(self._tenant_key(key))

    async def search(self, query: str, top_k: int = 10, **kwargs) -> list[dict]:
        # Add tenant filter to search
        kwargs.setdefault("filter", {})["tenant_id"] = self.tenant_id
        return await self.base.search(query, top_k, **kwargs)


# Context variable for current tenant
tenant_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "tenant_context", default=None
)


def get_current_tenant() -> str | None:
    """Get current tenant ID from context."""
    return tenant_context.get()


def set_current_tenant(tenant_id: str | None) -> contextvars.Token:
    """Set current tenant ID in context."""
    return tenant_context.set(tenant_id)


@asynccontextmanager
async def tenant_scope(tenant_id: str):
    """Context manager for tenant-scoped operations."""
    token = tenant_context.set(tenant_id)
    try:
        yield
    finally:
        tenant_context.reset(token)


__all__ = [
    "ROLE_PERMISSIONS",
    "Permission",
    "QuotaEnforcer",
    "QuotaExceededError",
    "ResourceType",
    "Role",
    "Tenant",
    "TenantAwareCheckpointer",
    "TenantAwareStore",
    "TenantQuota",
    "TenantRegistry",
    "TenantTier",
    "TenantUsage",
    "get_current_tenant",
    "set_current_tenant",
    "tenant_context",
    "tenant_scope",
]
