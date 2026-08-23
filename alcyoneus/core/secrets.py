"""Secret Manager Integrations for Alcyoneus OS.

Supports HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager, Azure Key Vault.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


try:
    import aiohttp
except ImportError:  # pragma: no cover - optional dependency
    aiohttp = None  # type: ignore[assignment]


logger = logging.getLogger("alcyoneus.secrets")


class SecretNotFoundError(Exception):
    pass


class SecretBackendError(Exception):
    pass


@dataclass
class Secret:
    """Secret value with metadata."""

    key: str
    value: str
    version: str | None = None
    metadata: dict | None = None


class SecretManager(ABC):
    """Abstract base class for secret managers."""

    @abstractmethod
    async def get_secret(self, key: str) -> Secret:
        pass

    @abstractmethod
    async def set_secret(self, key: str, value: str, metadata: dict | None = None) -> Secret:
        pass

    @abstractmethod
    async def delete_secret(self, key: str) -> bool:
        pass

    @abstractmethod
    async def list_secrets(self, prefix: str = "") -> list[str]:
        pass

    @abstractmethod
    async def get_secrets(self, keys: list[str]) -> dict[str, Secret]:
        pass

    async def close(self) -> None:  # noqa: B027
        pass


class VaultSecretManager(SecretManager):
    """HashiCorp Vault secret manager."""

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        mount_point: str = "secret",
        kv_version: int = 2,
        namespace: str | None = None,
        timeout: float = 10.0,
    ):
        self.url = url or os.getenv("VAULT_ADDR", "http://localhost:8200")
        self.token = token or os.getenv("VAULT_TOKEN")
        self.mount_point = mount_point
        self.kv_version = kv_version
        self.namespace = namespace
        self.timeout = timeout
        self._session: aiohttp.ClientSession | None = None

        if not self.token:
            raise ValueError("Vault token required: set VAULT_TOKEN or pass token=")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"X-Vault-Token": self.token}
            if self.namespace:
                headers["X-Vault-Namespace"] = self.namespace
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )
        return self._session

    def _secret_path(self, key: str) -> str:
        if self.kv_version == 1:
            return f"/v1/{self.mount_point}/{key}"
        return f"/v1/{self.mount_point}/data/{key}"

    async def get_secret(self, key: str) -> Secret:
        session = await self._get_session()
        path = self._secret_path(key)
        async with session.get(f"{self.url}{path}") as resp:
            if resp.status == 404:
                raise SecretNotFoundError(f"Secret not found: {key}")
            resp.raise_for_status()
            data = await resp.json()

        if self.kv_version == 1:
            secret_data = data.get("data", {})
            version = None
        else:
            secret_data = data.get("data", {}).get("data", {})
            version = str(data.get("data", {}).get("metadata", {}).get("version"))

        return Secret(key=key, value=json.dumps(secret_data), version=version)

    async def set_secret(self, key: str, value: str, metadata: dict | None = None) -> Secret:
        session = await self._get_session()
        path = self._secret_path(key)

        if self.kv_version == 1:
            payload = {"value": value}
            if metadata:
                payload.update(metadata)
        else:
            payload = {"data": json.loads(value) if isinstance(value, str) else value}
            if metadata:
                payload["metadata"] = metadata

        async with session.post(f"{self.url}{path}", json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()

        version = str(data.get("data", {}).get("version", 1)) if self.kv_version == 2 else "1"
        return Secret(key=key, value=value, version=version)

    async def delete_secret(self, key: str) -> bool:
        session = await self._get_session()
        path = self._secret_path(key)
        async with session.delete(f"{self.url}{path}") as resp:
            if resp.status == 404:
                return False
            resp.raise_for_status()
            return True

    async def list_secrets(self, prefix: str = "") -> list[str]:
        session = await self._get_session()
        list_path = f"/v1/{self.mount_point}/metadata/{prefix}?list=true"
        async with session.get(f"{self.url}{list_path}") as resp:
            if resp.status == 404:
                return []
            resp.raise_for_status()
            data = await resp.json()
            return data.get("data", {}).get("keys", [])

    async def get_secrets(self, keys: list[str]) -> dict[str, Secret]:
        results = {}
        for key in keys:
            try:
                results[key] = await self.get_secret(key)
            except SecretNotFoundError:
                pass
        return results

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


class AWSSecretsManager(SecretManager):
    """AWS Secrets Manager integration."""

    def __init__(
        self,
        region: str | None = None,
        endpoint_url: str | None = None,
        kms_key_id: str | None = None,
        timeout: float = 10.0,
    ):
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.endpoint_url = endpoint_url
        self.kms_key_id = kms_key_id or os.getenv("AWS_SECRETS_KMS_KEY")
        self.timeout = timeout
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "secretsmanager",
                region_name=self.region,
                endpoint_url=self.endpoint_url,
            )
        return self._client

    async def get_secret(self, key: str) -> Secret:
        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _get():
            resp = client.get_secret_value(SecretId=key)
            return Secret(
                key=key,
                value=resp.get("SecretString", ""),
                version=resp.get("VersionId"),
                metadata=resp.get("Description"),
            )

        try:
            return await loop.run_in_executor(None, _get)
        except client.exceptions.ResourceNotFoundException:
            raise SecretNotFoundError(f"Secret not found: {key}")

    async def set_secret(self, key: str, value: str, metadata: dict | None = None) -> Secret:
        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _put():
            kwargs = {"SecretId": key, "SecretString": value}
            if metadata:
                kwargs["Description"] = json.dumps(metadata)
            if self.kms_key_id:
                kwargs["KmsKeyId"] = self.kms_key_id

            try:
                resp = client.put_secret_value(**kwargs)
            except client.exceptions.ResourceNotFoundException:
                resp = client.create_secret(Name=key, **kwargs)
            return Secret(
                key=key,
                value=value,
                version=resp.get("VersionId"),
                metadata=metadata,
            )

        return await loop.run_in_executor(None, _put)

    async def delete_secret(self, key: str) -> bool:
        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _delete():
            try:
                client.delete_secret(SecretId=key, ForceDeleteWithoutRecovery=True)
                return True
            except client.exceptions.ResourceNotFoundException:
                return False

        return await loop.run_in_executor(None, _delete)

    async def list_secrets(self, prefix: str = "") -> list[str]:
        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _list():
            paginator = client.get_paginator("list_secrets")
            keys = []
            for page in paginator.paginate(Filters=[{"Key": "name", "Values": [f"{prefix}*"]}]):
                for secret in page.get("SecretList", []):
                    keys.append(secret["Name"])
            return keys

        return await loop.run_in_executor(None, _list)

    async def get_secrets(self, keys: list[str]) -> dict[str, Secret]:
        results = {}
        for key in keys:
            try:
                results[key] = await self.get_secret(key)
            except SecretNotFoundError:
                pass
        return results


class GCPSecretManager(SecretManager):
    """Google Cloud Secret Manager integration."""

    def __init__(
        self,
        project_id: str | None = None,
        location: str = "global",
        timeout: float = 10.0,
    ):
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = location
        self.timeout = timeout
        self._client = None

        if not self.project_id:
            raise ValueError(
                "GCP project ID required: set GOOGLE_CLOUD_PROJECT or pass project_id="
            )

    def _get_client(self):
        if self._client is None:
            from google.cloud import secretmanager

            self._client = secretmanager.SecretManagerServiceClient()
        return self._client

    def _secret_path(self, key: str, version: str = "latest") -> str:
        return (
            f"projects/{self.project_id}/locations/{self.location}/secrets/{key}/versions/{version}"
        )

    async def get_secret(self, key: str) -> Secret:
        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _get():
            resp = client.access_secret_version(name=self._secret_path(key))
            return Secret(
                key=key,
                value=resp.payload.data.decode("UTF-8"),
                version=resp.name.split("/")[-1],
            )

        try:
            return await loop.run_in_executor(None, _get)
        except Exception as e:
            if "NOT_FOUND" in str(e):
                raise SecretNotFoundError(f"Secret not found: {key}")
            raise

    async def set_secret(self, key: str, value: str, metadata: dict | None = None) -> Secret:
        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _put():
            parent = f"projects/{self.project_id}/locations/{self.location}"
            try:
                client.get_secret(name=f"{parent}/secrets/{key}")
                # Secret exists, add version
                resp = client.add_secret_version(
                    parent=f"{parent}/secrets/{key}",
                    payload={"data": value.encode("UTF-8")},
                )
            except Exception:
                # Create new secret
                secret = client.create_secret(
                    parent=parent,
                    secret_id=key,
                    secret={"replication": {"automatic": {}}},
                )
                resp = client.add_secret_version(
                    parent=secret.name,
                    payload={"data": value.encode("UTF-8")},
                )
            return Secret(
                key=key,
                value=value,
                version=resp.name.split("/")[-1],
                metadata=metadata,
            )

        return await loop.run_in_executor(None, _put)

    async def delete_secret(self, key: str) -> bool:
        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _delete():
            try:
                client.delete_secret(
                    name=f"projects/{self.project_id}/locations/{self.location}/secrets/{key}"
                )
                return True
            except Exception:
                return False

        return await loop.run_in_executor(None, _delete)

    async def list_secrets(self, prefix: str = "") -> list[str]:
        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _list():
            parent = f"projects/{self.project_id}/locations/{self.location}"
            keys = []
            for secret in client.list_secrets(parent=parent, filter=f"name:{prefix}"):
                keys.append(secret.name.split("/")[-1])
            return keys

        return await loop.run_in_executor(None, _list)

    async def get_secrets(self, keys: list[str]) -> dict[str, Secret]:
        results = {}
        for key in keys:
            try:
                results[key] = await self.get_secret(key)
            except SecretNotFoundError:
                pass
        return results


class AzureKeyVaultManager(SecretManager):
    """Azure Key Vault integration."""

    def __init__(
        self,
        vault_url: str | None = None,
        credential: Any | None = None,
        timeout: float = 10.0,
    ):
        self.vault_url = vault_url or os.getenv("AZURE_KEYVAULT_URL")
        self.credential = credential
        self.timeout = timeout
        self._client = None

        if not self.vault_url:
            raise ValueError(
                "Azure Key Vault URL required: set AZURE_KEYVAULT_URL or pass vault_url="
            )

    def _get_client(self):
        if self._client is None:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            cred = self.credential or DefaultAzureCredential()
            self._client = SecretClient(vault_url=self.vault_url, credential=cred)
        return self._client

    async def get_secret(self, key: str) -> Secret:
        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _get():
            secret = client.get_secret(key)
            return Secret(
                key=key,
                value=secret.value,
                version=secret.properties.version,
                metadata=secret.properties.tags,
            )

        try:
            return await loop.run_in_executor(None, _get)
        except Exception as e:
            if "not found" in str(e).lower():
                raise SecretNotFoundError(f"Secret not found: {key}")
            raise

    async def set_secret(self, key: str, value: str, metadata: dict | None = None) -> Secret:
        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _set():
            secret = client.set_secret(key, value, tags=metadata)
            return Secret(
                key=key,
                value=value,
                version=secret.properties.version,
                metadata=metadata,
            )

        return await loop.run_in_executor(None, _set)

    async def delete_secret(self, key: str) -> bool:
        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _delete():
            try:
                poller = client.begin_delete_secret(key)
                poller.result()
                return True
            except Exception:
                return False

        return await loop.run_in_executor(None, _delete)

    async def list_secrets(self, prefix: str = "") -> list[str]:
        loop = asyncio.get_event_loop()
        client = self._get_client()

        def _list():
            keys = []
            for secret in client.list_properties_of_secrets():
                if secret.name.startswith(prefix):
                    keys.append(secret.name)
            return keys

        return await loop.run_in_executor(None, _list)

    async def get_secrets(self, keys: list[str]) -> dict[str, Secret]:
        results = {}
        for key in keys:
            try:
                results[key] = await self.get_secret(key)
            except SecretNotFoundError:
                pass
        return results


class EnvSecretManager(SecretManager):
    """Environment variable secret manager (fallback)."""

    def __init__(self, prefix: str = "ALCYONEUS_SECRET_"):
        self.prefix = prefix

    async def get_secret(self, key: str) -> Secret:
        env_key = f"{self.prefix}{key.upper().replace('.', '_')}"
        value = os.getenv(env_key)
        if not value:
            raise SecretNotFoundError(f"Secret not found in env: {env_key}")
        return Secret(key=key, value=value)

    async def set_secret(self, key: str, value: str, metadata: dict | None = None) -> Secret:
        env_key = f"{self.prefix}{key.upper().replace('.', '_')}"
        os.environ[env_key] = value
        return Secret(key=key, value=value)

    async def delete_secret(self, key: str) -> bool:
        env_key = f"{self.prefix}{key.upper().replace('.', '_')}"
        if env_key in os.environ:
            del os.environ[env_key]
            return True
        return False

    async def list_secrets(self, prefix: str = "") -> list[str]:
        prefix_full = f"{self.prefix}{prefix.upper().replace('.', '_')}"
        return [k[len(self.prefix) :].lower() for k in os.environ if k.startswith(prefix_full)]

    async def get_secrets(self, keys: list[str]) -> dict[str, Secret]:
        results = {}
        for key in keys:
            try:
                results[key] = await self.get_secret(key)
            except SecretNotFoundError:
                pass
        return results


class CompositeSecretManager(SecretManager):
    """Composite secret manager that tries multiple backends in order."""

    def __init__(self, backends: list[SecretManager]):
        self.backends = backends

    async def get_secret(self, key: str) -> Secret:
        for backend in self.backends:
            try:
                return await backend.get_secret(key)
            except SecretNotFoundError:
                continue
        raise SecretNotFoundError(f"Secret not found in any backend: {key}")

    async def set_secret(self, key: str, value: str, metadata: dict | None = None) -> Secret:
        # Write to first backend that supports writing
        for backend in self.backends:
            try:
                return await backend.set_secret(key, value, metadata)
            except Exception as e:
                logger.debug("Backend %s failed to set secret %s: %s", type(backend).__name__, key, e)  # noqa: E501
                continue
        raise SecretBackendError("No backend available for writing")

    async def delete_secret(self, key: str) -> bool:
        for backend in self.backends:
            try:
                if await backend.delete_secret(key):
                    return True
            except Exception as e:
                logger.debug("Backend %s failed to delete secret %s: %s", type(backend).__name__, key, e)  # noqa: E501
                continue
        return False

    async def list_secrets(self, prefix: str = "") -> list[str]:
        all_keys = set()
        for backend in self.backends:
            try:
                keys = await backend.list_secrets(prefix)
                all_keys.update(keys)
            except Exception as e:
                logger.debug("Backend %s failed to list secrets: %s", type(backend).__name__, e)
                continue
        return list(all_keys)

    async def get_secrets(self, keys: list[str]) -> dict[str, Secret]:
        results = {}
        for key in keys:
            try:
                results[key] = await self.get_secret(key)
            except SecretNotFoundError:
                pass
        return results

    async def close(self) -> None:
        for backend in self.backends:
            await backend.close()


# Global secret manager instance
_secret_manager: SecretManager | None = None


def get_secret_manager() -> SecretManager:
    """Get global secret manager, auto-detecting available backends."""
    global _secret_manager
    if _secret_manager is not None:
        return _secret_manager

    backends = []

    # Try Vault
    if os.getenv("VAULT_ADDR") and os.getenv("VAULT_TOKEN"):
        try:
            backends.append(VaultSecretManager())
            logger.info("Vault secret manager enabled")
        except Exception as e:
            logger.warning(f"Failed to initialize Vault: {e}")

    # Try AWS
    if os.getenv("AWS_REGION"):
        try:
            backends.append(AWSSecretsManager())
            logger.info("AWS Secrets Manager enabled")
        except Exception as e:
            logger.warning(f"Failed to initialize AWS: {e}")

    # Try GCP
    if os.getenv("GOOGLE_CLOUD_PROJECT"):
        try:
            backends.append(GCPSecretManager())
            logger.info("GCP Secret Manager enabled")
        except Exception as e:
            logger.warning(f"Failed to initialize GCP: {e}")

    # Try Azure
    if os.getenv("AZURE_KEYVAULT_URL"):
        try:
            backends.append(AzureKeyVaultManager())
            logger.info("Azure Key Vault enabled")
        except Exception as e:
            logger.warning(f"Failed to initialize Azure: {e}")

    # Always add env as fallback
    backends.append(EnvSecretManager())

    if len(backends) == 1:
        _secret_manager = backends[0]
    else:
        _secret_manager = CompositeSecretManager(backends)

    return _secret_manager


def set_secret_manager(manager: SecretManager) -> None:
    """Set custom secret manager."""
    global _secret_manager
    _secret_manager = manager


async def get_secret(key: str) -> str:
    """Convenience function to get secret value."""
    manager = get_secret_manager()
    secret = await manager.get_secret(key)
    return secret.value


async def get_secrets(keys: list[str]) -> dict[str, str]:
    """Convenience function to get multiple secrets."""
    manager = get_secret_manager()
    secrets = await manager.get_secrets(keys)
    return {k: v.value for k, v in secrets.items()}


__all__ = [
    "AWSSecretsManager",
    "AzureKeyVaultManager",
    "CompositeSecretManager",
    "EnvSecretManager",
    "GCPSecretManager",
    "Secret",
    "SecretBackendError",
    "SecretManager",
    "SecretNotFoundError",
    "VaultSecretManager",
    "get_secret",
    "get_secret_manager",
    "get_secrets",
    "set_secret_manager",
]
