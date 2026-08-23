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

"""SQLite-backed session storage backend for persistent thread history."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .base import SessionABC, SessionSettings


class SQLiteSession(SessionABC):
    """SQLite database session backend."""

    def __init__(
        self,
        session_id: str,
        db_path: str = "alcyoneus_sessions.db",
        settings: SessionSettings | None = None,
    ) -> None:
        super().__init__(session_id, settings)
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    item_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()

    async def get_items(self) -> list[Any]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT item_json FROM session_items WHERE session_id = ? ORDER BY id ASC",
                (self.session_id,),
            )
            rows = cursor.fetchall()
            return [json.loads(r[0]) for r in rows]

    async def add_items(self, items: list[Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            for item in items:
                dumped = json.dumps(item) if not isinstance(item, str) else item
                conn.execute(
                    "INSERT INTO session_items (session_id, item_json) VALUES (?, ?)",
                    (self.session_id, dumped),
                )
            conn.commit()

    async def clear(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM session_items WHERE session_id = ?", (self.session_id,))
            conn.commit()


__all__ = ["SQLiteSession"]
