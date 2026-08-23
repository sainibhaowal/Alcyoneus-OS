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

"""Pluggable Serde (Serializer Protocol) for custom object & state serialization."""

from __future__ import annotations

import abc
import datetime
import hmac
import json
import pickle
import uuid
from dataclasses import is_dataclass
from typing import Any


class SerializerProtocol(abc.ABC):
    """Abstract Base Class for state and object serialization protocols."""

    @abc.abstractmethod
    def dumps(self, obj: Any) -> bytes:
        """Serialize object to bytes."""

    @abc.abstractmethod
    def loads(self, data: bytes) -> Any:
        """Deserialize bytes to object."""


class JsonSerde(SerializerProtocol):
    """Production-grade JSON serializer supporting Pydantic models, datetimes, UUIDs, and dataclasses."""  # noqa: E501

    def _default_encoder(self, obj: Any) -> Any:
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        if is_dataclass(obj):
            import dataclasses

            return dataclasses.asdict(obj)
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return str(obj)

    def dumps(self, obj: Any) -> bytes:
        return json.dumps(obj, default=self._default_encoder).encode("utf-8")

    def loads(self, data: bytes) -> Any:
        return json.loads(data.decode("utf-8"))


class PickleSerde(SerializerProtocol):
    """Production-grade binary pickle serializer with optional HMAC signature security."""

    def __init__(self, secret_key: bytes | None = None) -> None:
        self.secret_key = secret_key

    def dumps(self, obj: Any) -> bytes:
        raw = pickle.dumps(obj)
        if self.secret_key:
            sig = hmac.new(self.secret_key, raw, "sha256").digest()
            return sig + raw
        return raw

    def loads(self, data: bytes) -> Any:
        if self.secret_key:
            sig = data[:32]
            raw = data[32:]
            expected_sig = hmac.new(self.secret_key, raw, "sha256").digest()
            if not hmac.compare_digest(sig, expected_sig):
                raise ValueError("PickleSerde signature verification failed!")
            return pickle.loads(raw)  # noqa: S301
        return pickle.loads(data)  # noqa: S301


__all__ = [
    "JsonSerde",
    "PickleSerde",
    "SerializerProtocol",
]
