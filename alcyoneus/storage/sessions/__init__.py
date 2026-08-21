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

"""Multi-Backend Session Storage System for Alcyoneus OS."""

from .base import Session, SessionABC, SessionSettings
from .compaction import CompactionEvent, OnCompactionHook, on_compaction
from .dapr_session import DaprSession
from .encrypted_session import EncryptedSession
from .mongodb_session import MongoDBSession
from .redis_session import RedisSession
from .sqlalchemy_session import SQLAlchemySession
from .sqlite_session import SQLiteSession


__all__ = [
    "CompactionEvent",
    "DaprSession",
    "EncryptedSession",
    "MongoDBSession",
    "OnCompactionHook",
    "RedisSession",
    "SQLAlchemySession",
    "SQLiteSession",
    "Session",
    "SessionABC",
    "SessionSettings",
    "on_compaction",
]
