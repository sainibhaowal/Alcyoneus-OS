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

"""SQLite persistent disk cache implementation."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from .base import BaseCache


class SQLiteCache(BaseCache):
    """Production-grade SQLite-backed persistent disk cache store."""

    def __init__(self, db_path: str = "alcyoneus_cache.db", default_ttl: int | None = None) -> None:
        self.db_path = db_path
        self.default_ttl = default_ttl
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    val TEXT NOT NULL,
                    expiry REAL
                )
                """
            )
            conn.commit()

    def get(self, key: str) -> Any | None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT val, expiry FROM cache WHERE key = ?", (key,))
            row = cursor.fetchone()
            if not row:
                return None
            val_str, expiry = row
            if expiry is not None and time.time() > expiry:
                cursor.execute("DELETE FROM cache WHERE key = ?", (key,))
                conn.commit()
                return None
            try:
                return json.loads(val_str)
            except Exception:
                return val_str

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        eff_ttl = ttl if ttl is not None else self.default_ttl
        expiry = (time.time() + eff_ttl) if eff_ttl is not None else None
        val_str = json.dumps(value) if not isinstance(value, str) else value

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, val, expiry) VALUES (?, ?, ?)",
                (key, val_str, expiry),
            )
            conn.commit()

    def clear(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM cache")
            conn.commit()


__all__ = ["SQLiteCache"]
