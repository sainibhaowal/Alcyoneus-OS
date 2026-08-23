"""Audit and Compliance for Alcyoneus OS.

Provides audit logging, GDPR compliance, data lineage, policy-as-code (OPA/Rego), SBOM generation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import aiofiles


logger = logging.getLogger("alcyoneus.audit")


class AuditEventType(str, Enum):
    """Types of audit events."""

    # Authentication
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    TOKEN_REFRESH = "token_refresh"  # noqa: S105
    MFA_CHALLENGE = "mfa_challenge"

    # Authorization
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REVOKED = "role_revoked"

    # Data access
    DATA_READ = "data_read"
    DATA_WRITE = "data_write"
    DATA_DELETE = "data_delete"
    DATA_EXPORT = "data_export"
    DATA_IMPORT = "data_import"

    # Graph operations
    GRAPH_CREATE = "graph_create"
    GRAPH_UPDATE = "graph_update"
    GRAPH_DELETE = "graph_delete"
    GRAPH_EXECUTE = "graph_execute"
    GRAPH_EXECUTE_FAILED = "graph_execute_failed"

    # Model operations
    MODEL_INVOKE = "model_invoke"
    MODEL_INVOKE_FAILED = "model_invoke_failed"

    # Tool operations
    TOOL_INVOKE = "tool_invoke"
    TOOL_INVOKE_FAILED = "tool_invoke_failed"

    # Tenant operations
    TENANT_CREATE = "tenant_create"
    TENANT_UPDATE = "tenant_update"
    TENANT_DELETE = "tenant_delete"

    # Configuration
    CONFIG_CHANGE = "config_change"
    SECRET_ACCESS = "secret_access"  # noqa: S105
    SECRET_ROTATE = "secret_rotate"  # noqa: S105

    # Security
    SECURITY_INCIDENT = "security_incident"
    VULNERABILITY_DETECTED = "vulnerability_detected"
    PENETRATION_TEST = "penetration_test"

    # Compliance
    GDPR_REQUEST = "gdpr_request"
    DATA_RETENTION_APPLIED = "data_retention_applied"
    POLICY_VIOLATION = "policy_violation"


class AuditSeverity(str, Enum):
    """Audit event severity."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Audit event record."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_type: AuditEventType = AuditEventType.DATA_READ
    severity: AuditSeverity = AuditSeverity.INFO

    # Actor
    actor_id: str | None = None
    actor_type: str = "user"  # user, service, system
    actor_ip: str | None = None
    actor_user_agent: str | None = None

    # Tenant context
    tenant_id: str | None = None

    # Resource
    resource_type: str | None = None
    resource_id: str | None = None
    resource_name: str | None = None

    # Action details
    action: str | None = None
    outcome: str = "success"  # success, failure, partial
    error_message: str | None = None

    # Request context
    request_id: str | None = None
    session_id: str | None = None
    correlation_id: str | None = None

    # Additional data
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    # Compliance
    gdpr_relevant: bool = False
    data_categories: list[str] = field(default_factory=list)
    legal_basis: str | None = None

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "actor_ip": self.actor_ip,
            "actor_user_agent": self.actor_user_agent,
            "tenant_id": self.tenant_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "resource_name": self.resource_name,
            "action": self.action,
            "outcome": self.outcome,
            "error_message": self.error_message,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
            "tags": self.tags,
            "gdpr_relevant": self.gdpr_relevant,
            "data_categories": self.data_categories,
            "legal_basis": self.legal_basis,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


class AuditSink(ABC):
    """Abstract audit log sink."""

    @abstractmethod
    async def write(self, event: AuditEvent) -> None:
        pass

    @abstractmethod
    async def flush(self) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass


class FileAuditSink(AuditSink):
    """File-based audit sink with rotation."""

    def __init__(
        self,
        log_dir: str = "/var/log/alcyoneus/audit",
        max_file_size: int = 100 * 1024 * 1024,  # 100MB
        max_files: int = 10,
        compress: bool = True,
    ):
        self.log_dir = log_dir
        self.max_file_size = max_file_size
        self.max_files = max_files
        self.compress = compress
        self._current_file: aiofiles.threadpool.TextIOWrapper | None = None
        self._current_size = 0
        self._file_count = 0
        os.makedirs(log_dir, exist_ok=True)

    async def _get_file(self) -> aiofiles.threadpool.TextIOWrapper:
        if self._current_file is None or self._current_size >= self.max_file_size:
            await self._rotate()
        return self._current_file

    async def _rotate(self) -> None:
        if self._current_file:
            await self._current_file.close()

        # Rotate existing files
        for i in range(self.max_files - 1, 0, -1):
            old = os.path.join(self.log_dir, f"audit.{i}.log")
            new = os.path.join(self.log_dir, f"audit.{i + 1}.log")
            if os.path.exists(old):
                if self.compress and i == self.max_files - 1:
                    import gzip

                    with open(old, "rb") as f_in:
                        with gzip.open(f"{new}.gz", "wb") as f_out:
                            f_out.write(f_in.read())
                    os.remove(old)
                else:
                    os.rename(old, new)

        # Create new file
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(self.log_dir, f"audit.{timestamp}.log")
        self._current_file = await aiofiles.open(filepath, "a")
        self._current_size = 0

    async def write(self, event: AuditEvent) -> None:
        f = await self._get_file()
        line = event.to_json() + "\n"
        await f.write(line)
        await f.flush()
        self._current_size += len(line.encode())

    async def flush(self) -> None:
        if self._current_file:
            await self._current_file.flush()

    async def close(self) -> None:
        await self.flush()
        if self._current_file:
            await self._current_file.close()
            self._current_file = None


class ElasticsearchAuditSink(AuditSink):
    """Elasticsearch audit sink."""

    def __init__(
        self,
        hosts: list[str] | None = None,
        index_pattern: str = "alcyoneus-audit-%Y.%m.%d",
        username: str | None = None,
        password: str | None = None,
        api_key: str | None = None,
        batch_size: int = 100,
        flush_interval: float = 5.0,
    ):
        self.hosts = hosts if hosts is not None else ["http://localhost:9200"]
        self.index_pattern = index_pattern
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._buffer: list[AuditEvent] = []
        self._client = None
        self._flush_task: asyncio.Task | None = None

        # Auth
        self._auth = None
        if api_key:
            self._auth = ("", api_key)
        elif username and password:
            self._auth = (username, password)

    async def _get_client(self):
        if self._client is None:
            from elasticsearch import AsyncElasticsearch

            self._client = AsyncElasticsearch(
                hosts=self.hosts,
                basic_auth=self._auth[0] if self._auth else None,
                api_key=self._auth[1] if self._auth and len(self._auth) > 1 else None,
            )
            self._flush_task = asyncio.create_task(self._periodic_flush())
        return self._client

    async def _periodic_flush(self) -> None:
        while True:
            await asyncio.sleep(self.flush_interval)
            await self.flush()

    async def write(self, event: AuditEvent) -> None:
        self._buffer.append(event)
        if len(self._buffer) >= self.batch_size:
            await self.flush()

    async def flush(self) -> None:
        if not self._buffer:
            return

        client = await self._get_client()
        index = datetime.now(UTC).strftime(self.index_pattern)

        body = []
        for event in self._buffer:
            body.append({"index": {"_index": index}})
            body.append(event.to_dict())

        try:
            await client.bulk(body=body, refresh=False)
            self._buffer.clear()
        except Exception as e:
            logger.error(f"Failed to write audit events to Elasticsearch: {e}")

    async def close(self) -> None:
        await self.flush()
        if self._flush_task:
            self._flush_task.cancel()
        if self._client:
            await self._client.close()


class KafkaAuditSink(AuditSink):
    """Kafka audit sink."""

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        topic: str = "alcyoneus.audit",
        batch_size: int = 100,
        flush_interval: float = 5.0,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._buffer: list[AuditEvent] = []
        self._producer = None
        self._flush_task: asyncio.Task | None = None

    async def _get_producer(self):
        if self._producer is None:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: v.to_json().encode(),
            )
            await self._producer.start()
            self._flush_task = asyncio.create_task(self._periodic_flush())
        return self._producer

    async def _periodic_flush(self) -> None:
        while True:
            await asyncio.sleep(self.flush_interval)
            await self.flush()

    async def write(self, event: AuditEvent) -> None:
        self._buffer.append(event)
        if len(self._buffer) >= self.batch_size:
            await self.flush()

    async def flush(self) -> None:
        if not self._buffer:
            return

        producer = await self._get_producer()
        try:
            for event in self._buffer:
                await producer.send_and_wait(
                    self.topic,
                    value=event,
                    key=event.tenant_id.encode() if event.tenant_id else None,
                )
            self._buffer.clear()
        except Exception as e:
            logger.error(f"Failed to write audit events to Kafka: {e}")

    async def close(self) -> None:
        await self.flush()
        if self._flush_task:
            self._flush_task.cancel()
        if self._producer:
            await self._producer.stop()


class AuditLogger:
    """High-level audit logger."""

    def __init__(self, sinks: list[AuditSink] | None = None):
        self.sinks = sinks or [FileAuditSink()]
        self._context: dict[str, Any] = {}

    def set_context(self, **kwargs) -> None:
        self._context.update(kwargs)

    def clear_context(self) -> None:
        self._context.clear()

    @asynccontextmanager
    async def context(self, **kwargs):
        old_context = self._context.copy()
        self._context.update(kwargs)
        try:
            yield
        finally:
            self._context = old_context

    async def log(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity = AuditSeverity.INFO,
        **kwargs,
    ) -> AuditEvent:
        """Log an audit event."""
        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            **self._context,
            **kwargs,
        )

        for sink in self.sinks:
            try:
                await sink.write(event)
            except Exception as e:
                logger.error(f"Failed to write audit event to sink: {e}")

        return event

    async def log_login(self, actor_id: str, success: bool, **kwargs) -> AuditEvent:
        return await self.log(
            event_type=AuditEventType.LOGIN if success else AuditEventType.LOGIN_FAILED,
            severity=AuditEventType.INFO if success else AuditEventType.WARNING,
            actor_id=actor_id,
            action="login",
            outcome="success" if success else "failure",
            **kwargs,
        )

    async def log_data_access(
        self,
        event_type: AuditEventType,
        resource_type: str,
        resource_id: str,
        actor_id: str,
        **kwargs,
    ) -> AuditEvent:
        return await self.log(
            event_type=event_type,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            **kwargs,
        )

    async def log_gdpr_request(
        self,
        request_type: str,
        subject_id: str,
        tenant_id: str,
        **kwargs,
    ) -> AuditEvent:
        return await self.log(
            event_type=AuditEventType.GDPR_REQUEST,
            severity=AuditSeverity.INFO,
            actor_id=subject_id,
            tenant_id=tenant_id,
            action=request_type,
            gdpr_relevant=True,
            data_categories=kwargs.pop("data_categories", []),
            legal_basis=kwargs.pop("legal_basis", "consent"),
            **kwargs,
        )

    async def flush(self) -> None:
        for sink in self.sinks:
            await sink.flush()

    async def close(self) -> None:
        for sink in self.sinks:
            await sink.close()


# GDPR Compliance
class GDPRManager:
    """GDPR compliance manager."""

    def __init__(self, audit_logger: AuditLogger):
        self.audit = audit_logger

    async def handle_access_request(self, subject_id: str, tenant_id: str) -> dict:
        """Handle GDPR Article 15 - Right of access."""
        await self.audit.log_gdpr_request(
            request_type="access",
            subject_id=subject_id,
            tenant_id=tenant_id,
            data_categories=["personal", "behavioral", "technical"],
            legal_basis="consent",
        )
        # Implementation would collect all data for subject
        return {"status": "completed", "subject_id": subject_id}

    async def handle_rectification_request(
        self,
        subject_id: str,
        tenant_id: str,
        corrections: dict,
    ) -> dict:
        """Handle GDPR Article 16 - Right to rectification."""
        await self.audit.log_gdpr_request(
            request_type="rectification",
            subject_id=subject_id,
            tenant_id=tenant_id,
            metadata={"corrections": corrections},
        )
        return {"status": "completed", "subject_id": subject_id}

    async def handle_erasure_request(self, subject_id: str, tenant_id: str) -> dict:
        """Handle GDPR Article 17 - Right to erasure."""
        await self.audit.log_gdpr_request(
            request_type="erasure",
            subject_id=subject_id,
            tenant_id=tenant_id,
            data_categories=["personal", "behavioral", "technical"],
            legal_basis="consent_withdrawn",
        )
        # Implementation would delete all data for subject
        return {"status": "completed", "subject_id": subject_id}

    async def handle_portability_request(self, subject_id: str, tenant_id: str) -> dict:
        """Handle GDPR Article 20 - Right to data portability."""
        await self.audit.log_gdpr_request(
            request_type="portability",
            subject_id=subject_id,
            tenant_id=tenant_id,
            data_categories=["personal", "behavioral"],
        )
        return {"status": "completed", "subject_id": subject_id}

    async def handle_restriction_request(
        self,
        subject_id: str,
        tenant_id: str,
        restriction: str,
    ) -> dict:
        """Handle GDPR Article 18 - Right to restriction of processing."""
        await self.audit.log_gdpr_request(
            request_type="restriction",
            subject_id=subject_id,
            tenant_id=tenant_id,
            metadata={"restriction": restriction},
        )
        return {"status": "completed", "subject_id": subject_id}


# Data Lineage
@dataclass
class DataLineageNode:
    """Node in data lineage graph."""

    node_id: str
    node_type: str  # source, transform, sink
    name: str
    description: str | None = None
    metadata: dict = field(default_factory=dict)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class DataLineageTracker:
    """Track data lineage across pipeline stages."""

    def __init__(self):
        self._nodes: dict[str, DataLineageNode] = {}
        self._edges: dict[str, set[str]] = defaultdict(set)

    def register_node(self, node: DataLineageNode) -> None:
        self._nodes[node.node_id] = node

    def add_edge(self, from_id: str, to_id: str) -> None:
        self._edges[from_id].add(to_id)
        if from_id in self._nodes:
            self._nodes[from_id].outputs.append(to_id)
        if to_id in self._nodes:
            self._nodes[to_id].inputs.append(from_id)

    def get_upstream(self, node_id: str, max_depth: int = 10) -> list[DataLineageNode]:
        visited = set()
        result = []

        def dfs(nid: str, depth: int):
            if depth > max_depth or nid in visited:
                return
            visited.add(nid)
            if nid in self._nodes:
                result.append(self._nodes[nid])
            for parent in self._reverse_edges.get(nid, []):
                dfs(parent, depth + 1)

        # Build reverse edges
        self._reverse_edges = defaultdict(set)
        for src, dsts in self._edges.items():
            for dst in dsts:
                self._reverse_edges[dst].add(src)

        dfs(node_id, 0)
        return result

    def get_downstream(self, node_id: str, max_depth: int = 10) -> list[DataLineageNode]:
        visited = set()
        result = []

        def dfs(nid: str, depth: int):
            if depth > max_depth or nid in visited:
                return
            visited.add(nid)
            if nid in self._nodes:
                result.append(self._nodes[nid])
            for child in self._edges.get(nid, []):
                dfs(child, depth + 1)

        dfs(node_id, 0)
        return result

    def export_graphviz(self) -> str:
        lines = ["digraph lineage {"]
        for node in self._nodes.values():
            lines.append(f'  "{node.node_id}" [label="{node.name}\\n({node.node_type})"];')
        for src, dsts in self._edges.items():
            for dst in dsts:
                lines.append(f'  "{src}" -> "{dst}";')
        lines.append("}")
        return "\n".lines()


# Policy as Code (OPA/Rego)
class PolicyEngine:
    """OPA/Rego policy engine for authorization and compliance."""

    def __init__(self, policy_dir: str = "/etc/alcyoneus/policies"):
        self.policy_dir = policy_dir
        self._opa_path = "/usr/bin/opa"
        self._policies: dict[str, str] = {}
        self._load_policies()

    def _load_policies(self) -> None:
        if not os.path.exists(self.policy_dir):
            return
        for filename in os.listdir(self.policy_dir):
            if filename.endswith(".rego"):
                path = os.path.join(self.policy_dir, filename)
                with open(path) as f:
                    self._policies[filename] = f.read()

    async def evaluate(
        self,
        policy_name: str,
        input_data: dict,
        query: str = "data.alcyoneus.authz.allow",
    ) -> dict:
        """Evaluate a policy with input data."""
        if policy_name not in self._policies:
            raise ValueError(f"Policy not found: {policy_name}")

        # Write input to temp file
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(input_data, f)
            input_file = f.name

        policy_file = os.path.join(self.policy_dir, policy_name)

        try:
            proc = await asyncio.create_subprocess_exec(
                self._opa_path,
                "eval",
                "-i",
                input_file,
                "-d",
                policy_file,
                query,
                "--format",
                "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            os.unlink(input_file)

            if proc.returncode != 0:
                raise RuntimeError(f"OPA eval failed: {stderr.decode()}")

            result = json.loads(stdout.decode())
            return result.get("result", [{}])[0].get("expressions", [{}])[0].get("value", {})
        except Exception:
            os.unlink(input_file)
            raise

    async def authorize(
        self,
        actor: dict,
        action: str,
        resource: dict,
        context: dict | None = None,
    ) -> bool:
        """Check if action is allowed."""
        input_data = {
            "actor": actor,
            "action": action,
            "resource": resource,
            "context": context or {},
        }
        result = await self.evaluate("authz.rego", input_data)
        return result.get("allow", False)


# SBOM Generation
class SBOMGenerator:
    """Software Bill of Materials generator."""

    def __init__(self, project_root: str = "."):
        self.project_root = project_root

    async def generate_sbom(self, format: str = "spdx-json") -> str:  # noqa: A002
        """Generate SBOM using syft."""
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=f".{format.rsplit('-', maxsplit=1)[-1]}", delete=False
        ) as f:
            output_file = f.name

        try:
            proc = await asyncio.create_subprocess_exec(
                "syft",
                f"dir:{self.project_root}",
                "-o",
                format,
                "--file",
                output_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise RuntimeError(f"Syft failed: {stderr.decode()}")

            with open(output_file) as f:
                content = f.read()
            return content
        finally:
            os.unlink(output_file)

    async def generate_cyclonedx(self) -> str:
        return await self.generate_sbom("cyclonedx-json")

    async def generate_spdx(self) -> str:
        return await self.generate_sbom("spdx-json")

    async def check_vulnerabilities(self, sbom_content: str) -> list[dict]:
        """Check SBOM for vulnerabilities using grype."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(sbom_content)
            sbom_file = f.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            output_file = f.name

        try:
            proc = await asyncio.create_subprocess_exec(
                "grype",
                f"sbom:{sbom_file}",
                "-o",
                "json",
                "--file",
                output_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0 and proc.returncode != 1:  # grype returns 1 if vulns found
                raise RuntimeError(f"Grype failed: {stderr.decode()}")

            with open(output_file) as f:
                result = json.load(f)
            return result.get("matches", [])
        finally:
            os.unlink(sbom_file)
            os.unlink(output_file)


# Global instances
_audit_logger: AuditLogger | None = None
_gdpr_manager: GDPRManager | None = None
_policy_engine: PolicyEngine | None = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def set_audit_logger(logger: AuditLogger) -> None:
    global _audit_logger
    _audit_logger = logger


def get_gdpr_manager() -> GDPRManager:
    global _gdpr_manager
    if _gdpr_manager is None:
        _gdpr_manager = GDPRManager(get_audit_logger())
    return _gdpr_manager


def get_policy_engine() -> PolicyEngine:
    global _policy_engine
    if _policy_engine is None:
        _policy_engine = PolicyEngine()
    return _policy_engine


__all__ = [
    "AuditEvent",
    "AuditEventType",
    "AuditLogger",
    "AuditSeverity",
    "AuditSink",
    "DataLineageNode",
    "DataLineageTracker",
    "ElasticsearchAuditSink",
    "FileAuditSink",
    "GDPRManager",
    "KafkaAuditSink",
    "PolicyEngine",
    "SBOMGenerator",
    "get_audit_logger",
    "get_gdpr_manager",
    "get_policy_engine",
    "set_audit_logger",
]
