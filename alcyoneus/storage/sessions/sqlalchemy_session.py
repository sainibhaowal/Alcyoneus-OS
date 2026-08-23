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

"""SQLAlchemy ORM session storage backend for enterprise SQL databases."""

from __future__ import annotations

import json
import logging
from typing import Any

from .base import Session, SessionABC, SessionSettings


logger = logging.getLogger("alcyoneus.storage.sessions.sqlalchemy")


class SQLAlchemySession(SessionABC):
    """Production-grade SQLAlchemy ORM session storage backend."""

    def __init__(
        self,
        session_id: str,
        engine_url: str = "sqlite:///alcyoneus_sql.db",
        settings: SessionSettings | None = None,
        session_factory: Any | None = None,
    ) -> None:
        super().__init__(session_id, settings)
        self.engine_url = engine_url
        self._session_factory = session_factory
        self._fallback_memory = Session(session_id, settings)

    async def _get_session(self) -> Any:
        if self._session_factory is not None:
            return self._session_factory()
        try:
            from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
            from sqlalchemy.orm import sessionmaker

            engine = create_async_engine(self.engine_url)
            factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            self._session_factory = factory
            return factory()
        except ImportError:
            logger.debug("SQLAlchemy async extension not installed, using in-memory store")
            return None

    async def get_items(self) -> list[Any]:
        session = await self._get_session()
        if session is None:
            return await self._fallback_memory.get_items()
        try:
            from sqlalchemy import text

            async with session:
                result = await session.execute(
                    text(
                        "SELECT item_json FROM alcyoneus_session_items WHERE session_id = :sid ORDER BY id ASC"
                    ),
                    {"sid": self.session_id},
                )
                rows = result.fetchall()
                return [json.loads(r[0]) for r in rows]
        except Exception as err:
            logger.warning("SQLAlchemy get_items failed (%s), falling back to memory", err)
            return await self._fallback_memory.get_items()

    async def add_items(self, items: list[Any]) -> None:
        session = await self._get_session()
        if session is None:
            await self._fallback_memory.add_items(items)
            return
        try:
            from sqlalchemy import text

            async with session:
                for item in items:
                    dumped = json.dumps(item) if not isinstance(item, str) else item
                    await session.execute(
                        text(
                            "INSERT INTO alcyoneus_session_items (session_id, item_json) VALUES (:sid, :ij)"
                        ),
                        {"sid": self.session_id, "ij": dumped},
                    )
                await session.commit()
        except Exception as err:
            logger.warning("SQLAlchemy add_items failed (%s), falling back to memory", err)
            await self._fallback_memory.add_items(items)

    async def clear(self) -> None:
        session = await self._get_session()
        if session is None:
            await self._fallback_memory.clear()
            return
        try:
            from sqlalchemy import text

            async with session:
                await session.execute(
                    text("DELETE FROM alcyoneus_session_items WHERE session_id = :sid"),
                    {"sid": self.session_id},
                )
                await session.commit()
        except Exception as err:
            logger.warning("SQLAlchemy clear failed (%s)", err)
            await self._fallback_memory.clear()


__all__ = ["SQLAlchemySession"]
