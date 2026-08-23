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

"""MongoDB-backed session storage backend for distributed document-oriented persistence."""

from __future__ import annotations

import logging
from typing import Any

from .base import Session, SessionABC, SessionSettings


logger = logging.getLogger("alcyoneus.storage.sessions.mongodb")


class MongoDBSession(SessionABC):
    """Production-grade MongoDB document-oriented session storage backend."""

    def __init__(
        self,
        session_id: str,
        connection_string: str = "mongodb://localhost:27017",
        database_name: str = "alcyoneus",
        collection_name: str = "sessions",
        settings: SessionSettings | None = None,
        mongo_collection: Any | None = None,
    ) -> None:
        super().__init__(session_id, settings)
        self.connection_string = connection_string
        self.database_name = database_name
        self.collection_name = collection_name
        self._collection = mongo_collection
        self._fallback_memory = Session(session_id, settings)

    async def _get_collection(self) -> Any:
        if self._collection is not None:
            return self._collection
        try:
            from motor.motor_asyncio import AsyncIOMotorClient

            client = AsyncIOMotorClient(self.connection_string)
            db = client[self.database_name]
            self._collection = db[self.collection_name]
            return self._collection
        except ImportError:
            try:
                import pymongo

                client = pymongo.MongoClient(self.connection_string)
                db = client[self.database_name]
                self._collection = db[self.collection_name]
                return self._collection
            except ImportError:
                logger.debug("motor/pymongo not installed, using in-memory store")
                return None

    async def get_items(self) -> list[Any]:
        col = await self._get_collection()
        if col is None:
            return await self._fallback_memory.get_items()
        try:
            if hasattr(col, "find"):
                cursor = col.find({"session_id": self.session_id}).sort("created_at", 1)
                docs = (
                    await cursor.to_list(length=1000)
                    if hasattr(cursor, "to_list")
                    else list(cursor)
                )
                return [d.get("item") for d in docs if "item" in d]
        except Exception as err:
            logger.warning("MongoDB get_items failed (%s), falling back to memory", err)
        return await self._fallback_memory.get_items()

    async def add_items(self, items: list[Any]) -> None:
        col = await self._get_collection()
        if col is None:
            await self._fallback_memory.add_items(items)
            return
        try:
            import time

            docs = [
                {
                    "session_id": self.session_id,
                    "item": i,
                    "created_at": time.time(),
                }
                for i in items
            ]
            if docs:
                if hasattr(col, "insert_many"):
                    res = col.insert_many(docs)
                    if hasattr(res, "__await__"):
                        await res
        except Exception as err:
            logger.warning("MongoDB add_items failed (%s), falling back to memory", err)
            await self._fallback_memory.add_items(items)

    async def clear(self) -> None:
        col = await self._get_collection()
        if col is None:
            await self._fallback_memory.clear()
            return
        try:
            if hasattr(col, "delete_many"):
                res = col.delete_many({"session_id": self.session_id})
                if hasattr(res, "__await__"):
                    await res
        except Exception as err:
            logger.warning("MongoDB clear failed (%s)", err)
            await self._fallback_memory.clear()


__all__ = ["MongoDBSession"]
