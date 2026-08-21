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

"""Kubernetes sandbox implementation for isolated code execution."""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any

from .base import BaseSandbox
from .errors import SandboxError, SandboxStartError
from .types import ExecResult, GPUConfig, SandboxConfig


logger = logging.getLogger("alcyoneus.sandbox.k8s")


class K8sSandbox(BaseSandbox):
    """Kubernetes Pod-based sandbox with resource limits, GPU, volume mounts, and exec."""

    def __init__(
        self,
        config: SandboxConfig | None = None,
        namespace: str = "default",
        pod_name_prefix: str = "alc-sandbox",
    ) -> None:
        super().__init__(config)
        self.namespace = namespace
        self.pod_name_prefix = pod_name_prefix
        self.pod_name: str | None = None
        self._client: Any | None = None

    def _get_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        try:
            from kubernetes import client, config

            config.load_incluster_config() if self._in_cluster() else config.load_kube_config()
            self._client = client.CoreV1Api()
            return self._client
        except Exception as exc:
            logger.debug("Kubernetes client not available: %s", exc)
            self._client = None
        return None

    def _in_cluster(self) -> bool:
        import os

        return os.getenv("KUBERNETES_SERVICE_HOST") is not None

    def _build_pod_manifest(self) -> dict[str, Any]:
        cfg = self.config
        container = {
            "name": "sandbox",
            "image": cfg.image,
            "workingDir": cfg.workdir,
            "env": [{"name": k, "value": v} for k, v in cfg.env.items()],
            "command": ["sh", "-c", "sleep infinity"],
            "resources": {
                "requests": {"cpu": str(cfg.cpu_limit), "memory": cfg.memory_limit},
                "limits": {"cpu": str(cfg.cpu_limit), "memory": cfg.memory_limit},
            },
        }

        # GPU
        if cfg.gpu_config != GPUConfig.NONE and cfg.gpu_devices:
            container["resources"]["limits"]["nvidia.com/gpu"] = str(len(cfg.gpu_devices))
            container["resources"]["requests"]["nvidia.com/gpu"] = str(len(cfg.gpu_devices))

        # Volume mounts
        volumes = []
        volume_mounts = []
        for i, vol in enumerate(cfg.volumes):
            vol_name = f"vol-{i}"
            volumes.append({"name": vol_name, "hostPath": {"path": vol.source}})
            volume_mounts.append(
                {"name": vol_name, "mountPath": vol.target, "readOnly": vol.read_only}
            )
        if volume_mounts:
            container["volumeMounts"] = volume_mounts

        pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": self.pod_name, "labels": {"app": "alcyoneus-sandbox"}},
            "spec": {
                "containers": [container],
                "restartPolicy": "Never",
                "volumes": volumes,
                "securityContext": {"runAsNonRoot": True},
            },
        }
        return pod

    async def start(self) -> None:
        if self._client is None:
            raise SandboxStartError("Kubernetes client not configured")
        import uuid

        self.pod_name = f"{self.pod_name_prefix}-{uuid.uuid4().hex[:8]}"
        manifest = self._build_pod_manifest()
        try:
            from kubernetes import client as k8s_client

            body = k8s_client.V1Pod(**self._dict_to_v1pod(manifest))
            self._client.create_namespaced_pod(namespace=self.namespace, body=body)
            # Wait for Running
            for _ in range(60):
                pod = self._client.read_namespaced_pod(name=self.pod_name, namespace=self.namespace)
                phase = pod.status.phase
                if phase == "Running":
                    logger.info("K8s sandbox pod running: %s", self.pod_name)
                    return
                if phase in ("Failed", "Unknown"):
                    raise SandboxStartError(f"Pod failed with phase {phase}")
                await asyncio.sleep(1)
            raise SandboxStartError("Pod did not start in time")
        except Exception as exc:
            raise SandboxStartError(str(exc))

    def _dict_to_v1pod(self, d: dict[str, Any]) -> Any:
        from kubernetes import client as k8s_client

        # Simplified conversion – real implementation would map fully
        metadata = k8s_client.V1ObjectMeta(
            name=d["metadata"]["name"], labels=d["metadata"].get("labels")
        )
        spec = k8s_client.V1PodSpec(
            containers=[
                k8s_client.V1Container(
                    name=d["spec"]["containers"][0]["name"],
                    image=d["spec"]["containers"][0]["image"],
                    working_dir=d["spec"]["containers"][0].get("workingDir"),
                    env=[
                        k8s_client.V1EnvVar(name=e["name"], value=e["value"])
                        for e in d["spec"]["containers"][0].get("env", [])
                    ],
                    command=d["spec"]["containers"][0].get("command"),
                    resources=k8s_client.V1ResourceRequirements(
                        requests=d["spec"]["containers"][0]["resources"]["requests"],
                        limits=d["spec"]["containers"][0]["resources"]["limits"],
                    ),
                )
            ],
            restart_policy=d["spec"].get("restartPolicy", "Never"),
        )
        return k8s_client.V1Pod(metadata=metadata, spec=spec)

    async def stop(self) -> None:
        if not self.pod_name:
            return
        client = self._get_client()
        if client is None:
            return
        try:
            client.delete_namespaced_pod(name=self.pod_name, namespace=self.namespace)
            logger.info("K8s sandbox pod deleted: %s", self.pod_name)
        except Exception as exc:
            logger.warning("Failed to delete pod: %s", exc)
        self.pod_name = None

    async def exec(self, command: str, timeout: float | None = None) -> ExecResult:
        if not self.pod_name:
            raise SandboxError("Pod not running")
        client = self._get_client()
        if client is None:
            raise SandboxError("K8s client not configured")
        start_t = time.monotonic()
        try:
            from kubernetes.stream import stream

            resp = stream(
                client,
                client.api_client,
                f"/api/v1/namespaces/{self.namespace}/pods/{self.pod_name}/exec",
                params={
                    "command": ["sh", "-c", command],
                    "stdin": False,
                    "stdout": True,
                    "stderr": True,
                    "tty": False,
                },
            )
            stdout = resp
            exit_code = 0
        except Exception as exc:
            logger.warning("K8s exec failed: %s", exc)
            stdout = ""
            exit_code = 1
        return ExecResult(
            exit_code=exit_code,
            stdout=stdout if isinstance(stdout, str) else str(stdout),
            stderr="",
            duration_seconds=time.monotonic() - start_t,
        )

    async def read_file(self, path: str) -> bytes:
        if not self.pod_name:
            raise SandboxError("Pod not running")
        # Read via exec cat
        res = await self.exec(f"cat {path}")
        return res.stdout.encode()

    async def write_file(self, path: str, content: bytes | str) -> None:
        text = content.decode() if isinstance(content, bytes) else content
        await self.exec(f"mkdir -p $(dirname {path}) && cat > {path}", timeout=None)
        # Actually write via exec with base64
        b64 = base64.b64encode(text.encode()).decode()
        await self.exec(f"mkdir -p $(dirname {path}) && echo '{b64}' | base64 -d > {path}")

    __all__ = ["K8sSandbox"]
