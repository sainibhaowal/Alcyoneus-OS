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

"""Cloud storage volume mounts (AWS S3, Google Cloud Storage, Azure Blob) for Sandbox containers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StorageMount:
    """Base class for remote storage volume mounts into a sandbox container."""

    container_path: str
    read_only: bool = False


@dataclass
class S3Mount(StorageMount):
    """Amazon S3 bucket volume mount."""

    bucket_name: str = ""
    prefix: str = ""
    aws_region: str = "us-east-1"
    access_key_id: str | None = None
    secret_access_key: str | None = None


@dataclass
class GCSMount(StorageMount):
    """Google Cloud Storage bucket volume mount."""

    bucket_name: str = ""
    prefix: str = ""
    credentials_json: str | None = None


@dataclass
class AzureBlobMount(StorageMount):
    """Azure Blob Storage container volume mount."""

    container_name: str = ""
    storage_account_name: str = ""
    account_key: str | None = None


@dataclass
class R2Mount(StorageMount):
    """Cloudflare R2 bucket volume mount."""

    bucket_name: str = ""
    prefix: str = ""
    account_id: str = ""
    access_key_id: str | None = None
    secret_access_key: str | None = None
    region: str = "auto"


@dataclass
class BoxMount(StorageMount):
    """Box cloud storage folder mount."""

    folder_id: str = ""
    access_token: str | None = None
    refresh_token: str | None = None
    client_id: str | None = None
    client_secret: str | None = None


__all__ = [
    "AzureBlobMount",
    "BoxMount",
    "GCSMount",
    "R2Mount",
    "S3Mount",
    "StorageMount",
]
