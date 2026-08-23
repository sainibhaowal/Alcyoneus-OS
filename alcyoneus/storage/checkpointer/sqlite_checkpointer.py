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
"""SQLite checkpointer for alcyoneus OS.

Provides a SQLite-backed checkpointer for agent state persistence.
Supports both sync and async operation modes.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from alcyoneus.storage.checkpointer.base_checkpointer import BaseCheckpointer, StateT


class SqliteCheckpointer(BaseCheckpointer[StateT]):
    """SQLite-backed checkpointer for agent state persistence.

    Uses a local SQLite database for checkpoint storage.
    Suitable for single-threaded or lightly concurrent environments.

    Example:
        ```python
        from alcyoneus.storage.checkpointer import SqliteCheckpointer

        checkpointer = SqliteCheckpointer(":memory:")
        await checkpointer.asetup()
        await checkpointer.aput_state(config, state)
        state = await checkpointer.aget_state(config)
        ```
    """

    def __init__(self, database: str | os.PathLike[str] = ":memory:"):
        """Initialize the SQLite checkpointer.

        Args:
            database: Path to SQLite database file. Use ":memory:" for in-memory.
        """
        self._db_path = os.path.expanduser(str(database))
        self._lock = asyncio.Lock()
        self._conn: sqlite3.Connection | None = None
        self._state: StateT | None = None
        self._initialized = False

    async def asetup(self) -> None:
        """Asynchronous setup: initialize the SQLite database."""
        async with self._lock:
            if self._initialized:
                return
            await self._setup()

    async def _setup(self) -> None:
        """Create tables on the persistent connection.

        Must be called with ``self._lock`` already held.
        """
        # Create tables on the persistent connection
        await self._ensure_connection()
        conn = self._conn  # type: ignore[assignment]
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                parent_checkpoint_id TEXT,
                checkpoint_values TEXT NOT NULL,
                checkpoint_metadata TEXT NOT NULL,
                created_at TEXT NOT NULL,
                run_id TEXT
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoint_writes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint_id TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                channel_version INTEGER NOT NULL,
                write_index INTEGER NOT NULL,
                value TEXT NOT NULL,
                thread_id TEXT,
                FOREIGN KEY (checkpoint_id) REFERENCES checkpoints(checkpoint_id)
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_writes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint_id TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                value TEXT NOT NULL,
                FOREIGN KEY (checkpoint_id) REFERENCES checkpoints(checkpoint_id)
            )
        """
        )
        columns = [row[1] for row in conn.execute("PRAGMA table_info(checkpoints)")]
        if "run_id" not in columns:
            conn.execute("ALTER TABLE checkpoints ADD COLUMN run_id TEXT")
        write_columns = [row[1] for row in conn.execute("PRAGMA table_info(checkpoint_writes)")]
        if "thread_id" not in write_columns:
            conn.execute("ALTER TABLE checkpoint_writes ADD COLUMN thread_id TEXT")
        conn.commit()
        self._initialized = True

    async def _ensure_connection(self) -> None:
        """Ensure a database connection exists, creating tables if needed."""
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            # Create tables if they don't exist
            conn = self._conn  # type: ignore[assignment]
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    parent_checkpoint_id TEXT,
                    checkpoint_values TEXT NOT NULL,
                    checkpoint_metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    run_id TEXT
                )
            """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoint_writes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    checkpoint_id TEXT NOT NULL,
                    channel_name TEXT NOT NULL,
                    channel_version INTEGER NOT NULL,
                    write_index INTEGER NOT NULL,
                    value TEXT NOT NULL,
                    thread_id TEXT,
                    FOREIGN KEY (checkpoint_id) REFERENCES checkpoints(checkpoint_id)
                )
            """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_writes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    checkpoint_id TEXT NOT NULL,
                    channel_name TEXT NOT NULL,
                    value TEXT NOT NULL,
                    FOREIGN KEY (checkpoint_id) REFERENCES checkpoints(checkpoint_id)
                )
            """
            )
            columns = [row[1] for row in conn.execute("PRAGMA table_info(checkpoints)")]
            if "run_id" not in columns:
                conn.execute("ALTER TABLE checkpoints ADD COLUMN run_id TEXT")
            write_columns = [row[1] for row in conn.execute("PRAGMA table_info(checkpoint_writes)")]
            if "thread_id" not in write_columns:
                conn.execute("ALTER TABLE checkpoint_writes ADD COLUMN thread_id TEXT")
            conn.commit()

    async def _ensure_setup(self) -> None:
        """Ensure the checkpointer is set up.

        Assumes the caller already holds ``self._lock``, so it runs setup
        inline instead of re-entering ``asetup`` (which would deadlock on the
        non-reentrant asyncio.Lock).
        """
        if not self._initialized:
            await self._setup()

    async def _get_conn(self) -> sqlite3.Connection:
        """Get or create a database connection.

        Returns:
            SQLite connection.
        """
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    async def aput_state(self, config: dict[str, Any], state: StateT) -> StateT:
        """Store agent state asynchronously.

        Args:
            config: Configuration dictionary.
            state: State object to store.

        Returns:
            The stored state object.
        """
        async with self._lock:
            await self._ensure_setup()
            conn = await self._get_conn()
            checkpoint_id = str(uuid.uuid4())
            now = datetime.now(UTC).isoformat()
            state_json = (
                json.dumps(state.model_dump() if hasattr(state, "model_dump") else state)
                if not isinstance(state, str)
                else state
            )
            metadata_json = json.dumps({"source": "sqlite", "checkpoint_id": checkpoint_id})
            conn.execute(
                """
                INSERT OR REPLACE INTO checkpoints
                (checkpoint_id, thread_id, parent_checkpoint_id, checkpoint_values,
checkpoint_metadata, created_at, run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    checkpoint_id,
                    config.get("thread_id", ""),
                    None,
                    state_json,
                    metadata_json,
                    now,
                    config.get("run_id"),
                ),
            )
            conn.commit()
            self._state = state
            return state

    async def aget_state(self, config: dict[str, Any]) -> StateT | None:
        """Retrieve agent state asynchronously.

        Args:
            config: Configuration dictionary.

        Returns:
            Retrieved state or None.
        """
        async with self._lock:
            await self._ensure_setup()
            conn = await self._get_conn()
            thread_id = config.get("thread_id", "")
            row = conn.execute(
                "SELECT checkpoint_values FROM checkpoints WHERE thread_id = ? ORDER BY created_at DESC LIMIT 1",  # noqa: E501
                (thread_id,),
            ).fetchone()
            if row is None:
                return None
            state = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            self._state = state
            return state

    async def aclear_state(self, config: dict[str, Any]) -> Any:
        """Clear agent state asynchronously.

        Args:
            config: Configuration dictionary.

        Returns:
            Implementation-defined result.
        """
        async with self._lock:
            await self._ensure_setup()
            conn = await self._get_conn()
            thread_id = config.get("thread_id", "")
            conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
            conn.execute(
                "DELETE FROM checkpoint_writes WHERE checkpoint_id IN (SELECT checkpoint_id FROM checkpoints WHERE thread_id = ?)",  # noqa: E501
                (thread_id,),
            )
            conn.execute(
                "DELETE FROM pending_writes WHERE checkpoint_id IN (SELECT checkpoint_id FROM checkpoints WHERE thread_id = ?)",  # noqa: E501
                (thread_id,),
            )
            conn.commit()
            self._state = None
            return None

    async def aput_state_cache(self, config: dict[str, Any], state: StateT) -> Any | None:
        """Store agent state in cache asynchronously.

        Args:
            config: Configuration dictionary.
            state: State object to cache.

        Returns:
            Implementation-defined result.
        """
        async with self._lock:
            self._state = state
            return state

    async def aget_state_cache(self, config: dict[str, Any]) -> StateT | None:
        """Retrieve agent state from cache asynchronously.

        Args:
            config: Configuration dictionary.

        Returns:
            Cached state or None.
        """
        async with self._lock:
            return self._state

    async def aput(self, config: dict[str, Any], state: Any) -> None:
        """Store checkpoint state (alias for aput_state).

        Args:
            config: Configuration dictionary.
            state: State to persist.
        """
        await self.aput_state(config, state)

    async def aget(self, config: dict[str, Any]) -> Any:
        """Retrieve checkpoint state (alias for aget_state).

        Args:
            config: Configuration dictionary.

        Returns:
            Retrieved state or None.
        """
        return await self.aget_state(config)

    async def adelete_thread(self, config: dict[str, Any]) -> None:
        """Delete all checkpoints for a thread.

        Args:
            config: Configuration dictionary.
        """
        async with self._lock:
            await self._ensure_setup()
            conn = await self._get_conn()
            thread_id = config.get("thread_id", "")
            conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
            conn.execute(
                "DELETE FROM checkpoint_writes WHERE checkpoint_id IN (SELECT checkpoint_id FROM checkpoints WHERE thread_id = ?)",  # noqa: E501
                (thread_id,),
            )
            conn.execute(
                "DELETE FROM pending_writes WHERE checkpoint_id IN (SELECT checkpoint_id FROM checkpoints WHERE thread_id = ?)",  # noqa: E501
                (thread_id,),
            )
            conn.commit()
            self._state = None

    async def aprune(self, strategy: str = "keep_latest") -> None:
        """Prune checkpoints based on strategy.

        Args:
            strategy: Prune strategy ("keep_latest", "delete_all").
        """
        async with self._lock:
            await self._ensure_setup()
            conn = await self._get_conn()
            if strategy == "keep_latest":
                conn.execute(
                    """
                    DELETE FROM checkpoints
                    WHERE rowid NOT IN (
                        SELECT MAX(rowid) FROM checkpoints GROUP BY thread_id
                    )
                """
                )
            elif strategy == "delete_all":
                conn.execute("DELETE FROM checkpoints")
            conn.commit()

    async def adelete_for_runs(
        self,
        config: dict[str, Any],
        run_ids: list[str] | str,
    ) -> Any | None:
        """Delete checkpoint history entries associated with specific run ids.

        Args:
            config: Configuration dictionary (must include thread_id).
            run_ids: A single run id or list of run ids to delete.

        Returns:
            Any | None: Implementation-defined result.
        """
        if isinstance(run_ids, str):
            run_ids = [run_ids]
        if not run_ids:
            return None

        async with self._lock:
            await self._ensure_setup()
            conn = await self._get_conn()
            placeholders = ",".join("?" for _ in run_ids)
            query = (
                "DELETE FROM checkpoint_writes "
                "WHERE checkpoint_id IN ("
                "    SELECT checkpoint_id FROM checkpoints "
                f"    WHERE thread_id = ? AND run_id IN ({placeholders})"
                ")"
            )
            conn.execute(query, (config.get("thread_id", ""), *run_ids))
            query = f"DELETE FROM checkpoints WHERE thread_id = ? AND run_id IN ({placeholders})"
            conn.execute(query, (config.get("thread_id", ""), *run_ids))
            conn.commit()
        return len(run_ids)

    async def acopy_thread(
        self,
        config: dict[str, Any],
        source_thread_id: str,
        new_thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Copy a thread's state/checkpoints into a new thread.

        Args:
            config: Configuration dictionary.
            source_thread_id: Thread to copy from.
            new_thread_id: Destination thread id (auto-generated when None).

        Returns:
            dict: Config with the new thread_id.
        """
        from uuid import uuid4

        target_thread_id = new_thread_id or str(uuid4())
        source_cfg = dict(config)
        source_cfg["thread_id"] = source_thread_id
        target_cfg = dict(config)
        target_cfg["thread_id"] = target_thread_id

        async with self._lock:
            await self._ensure_setup()
            conn = await self._get_conn()
            rows = conn.execute(
                "SELECT checkpoint_id, checkpoint_values, checkpoint_metadata, created_at, run_id FROM checkpoints WHERE thread_id = ?",  # noqa: E501
                (source_thread_id,),
            ).fetchall()
            id_map: dict[str, str] = {}
            for row in rows:
                checkpoint_id, values, metadata, created_at, run_id = row
                new_checkpoint_id = str(uuid4())
                id_map[checkpoint_id] = new_checkpoint_id
                conn.execute(
                    """
                    INSERT INTO checkpoints
                        (checkpoint_id, thread_id, checkpoint_values, checkpoint_metadata,
created_at, run_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_checkpoint_id,
                        target_thread_id,
                        values,
                        metadata,
                        created_at,
                        run_id,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO checkpoint_writes
                        (checkpoint_id, thread_id, channel_name, channel_version,
write_index, value)
                    SELECT ?, ?, channel_name, channel_version, write_index, value
                    FROM checkpoint_writes WHERE checkpoint_id = ?
                    """,
                    (new_checkpoint_id, target_thread_id, checkpoint_id),
                )
            conn.commit()

        return {"configurable": {"thread_id": target_thread_id}}

    async def aget_delta_channel_history(self, config: dict[str, Any], **kwargs: Any) -> list[Any]:
        """Get delta channel history.

        Args:
            config: Configuration dictionary.
            **kwargs: Additional keyword arguments.

        Returns:
            List of delta channel history entries.
        """
        async with self._lock:
            await self._ensure_setup()
            conn = await self._get_conn()
            thread_id = config.get("thread_id", "")
            rows = conn.execute(
                """
                SELECT channel_name, channel_version, write_index, value
                FROM checkpoint_writes
                WHERE checkpoint_id IN (
                    SELECT checkpoint_id FROM checkpoints WHERE thread_id = ?
                )
                ORDER BY write_index ASC
                """,
                (thread_id,),
            ).fetchall()
            import json

            return [
                {
                    "channel_name": row[0],
                    "channel_version": row[1],
                    "write_index": row[2],
                    "value": json.loads(row[3]) if isinstance(row[3], str) else row[3],
                }
                for row in rows
            ]

    async def aget_thread(self) -> list[Any]:
        """List all thread IDs.

        Returns:
            List of thread IDs.
        """
        async with self._lock:
            await self._ensure_setup()
            conn = await self._get_conn()
            rows = conn.execute("SELECT DISTINCT thread_id FROM checkpoints").fetchall()
            return [row[0] for row in rows]

    async def alist_threads(self) -> list[Any]:
        """List all thread IDs (alias for aget_thread).

        Returns:
            List of thread IDs.
        """
        return await self.aget_thread()

    async def alist(self, filter: dict[str, Any] | None = None, **kwargs: Any) -> list[Any]:  # noqa: A002
        """List checkpoints.

        Args:
            filter: Optional filter dict (e.g., before, limit).
            **kwargs: Additional keyword arguments.

        Returns:
            List of checkpoint data.
        """
        async with self._lock:
            await self._ensure_setup()
            conn = await self._get_conn()
            query = "SELECT checkpoint_values, checkpoint_metadata, created_at, thread_id FROM checkpoints ORDER BY created_at DESC"  # noqa: E501
            rows = conn.execute(query).fetchall()
            import json

            return [
                {
                    "values": json.loads(row[0]) if isinstance(row[0], str) else row[0],
                    "metadata": json.loads(row[1]) if isinstance(row[1], str) else row[1],
                    "created_at": row[2],
                    "thread_id": row[3],
                }
                for row in rows
            ]

    async def arelease(self) -> Any | None:
        """Release resources asynchronously.

        Returns:
            Implementation-defined result.
        """
        # Don't use lock here - aclose() uses its own lock
        await self.aclose()
        return None

    async def aclose(self) -> None:
        """Close the database connection asynchronously.

        Ensures proper cleanup of the database connection and releases
        all held resources.
        """
        async with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            self._initialized = False

    async def aclean_thread(self, config: dict[str, Any]) -> None:
        """Clean (delete) a thread's checkpoints.

        Args:
            config: Configuration dictionary containing thread_id.
        """
        async with self._lock:
            await self._ensure_setup()
            conn = await self._get_conn()
            thread_id = config.get("thread_id", "")
            conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
            conn.execute(
                "DELETE FROM checkpoint_writes WHERE checkpoint_id IN (SELECT checkpoint_id FROM checkpoints WHERE thread_id = ?)",  # noqa: E501
                (thread_id,),
            )
            conn.execute(
                "DELETE FROM pending_writes WHERE checkpoint_id IN (SELECT checkpoint_id FROM checkpoints WHERE thread_id = ?)",  # noqa: E501
                (thread_id,),
            )
            conn.commit()

    async def adelete_message(self, config: dict[str, Any], message_id: str | int) -> Any | None:
        """Delete a specific message checkpoint.

        Args:
            config: Configuration dictionary.
            message_id: Identifier of the message to delete.

        Returns:
            Implementation-defined result.
        """
        async with self._lock:
            await self._ensure_setup()
            conn = await self._get_conn()
            conn.execute(
                "DELETE FROM pending_writes WHERE value LIKE ?",
                (f"%{message_id!s}%",),
            )
            conn.commit()
            return None

    async def aget_message(self, config: dict[str, Any], message_id: str | int) -> Any:
        """Retrieve a specific message checkpoint.

        Args:
            config: Configuration dictionary.
            message_id: Identifier of the message to retrieve.

        Returns:
            Message object or None.
        """
        async with self._lock:
            await self._ensure_setup()
            conn = await self._get_conn()
            row = conn.execute(
                "SELECT value FROM pending_writes WHERE value LIKE ?",
                (f"%{message_id!s}%",),
            ).fetchone()
            if row is None:
                return None
            import types

            return types.SimpleNamespace(**json.loads(row[0]))

    async def alist_messages(self, config: dict[str, Any], **kwargs: Any) -> list[Any]:
        """List all message checkpoints.

        Args:
            config: Configuration dictionary.
            **kwargs: Additional keyword arguments.

        Returns:
            List of message checkpoints.
        """
        async with self._lock:
            await self._ensure_setup()
            conn = await self._get_conn()
            rows = conn.execute("SELECT value FROM pending_writes").fetchall()
            import json

            return [json.loads(row[0]) if isinstance(row[0], str) else row[0] for row in rows]

    async def aput_message(self, config: dict[str, Any], message: Any) -> Any:
        """Persist a single message checkpoint.

        Args:
            config: Configuration dictionary.
            message: Message object to persist.

        Returns:
            The persisted message.
        """
        async with self._lock:
            await self._ensure_setup()
            conn = await self._get_conn()
            message_json = json.dumps(message) if not isinstance(message, str) else message
            conn.execute(
                """
                INSERT INTO pending_writes (checkpoint_id, channel_name, value)
                VALUES (?, ?, ?)
                """,
                (
                    config.get("thread_id", ""),
                    "messages",
                    message_json,
                ),
            )
            conn.commit()
            return message

    async def aput_messages(
        self, config: dict[str, Any], messages: list[Any], metadata: dict[str, Any] | None = None
    ) -> Any:
        """Persist multiple messages checkpoints.

        Args:
            config: Configuration dictionary.
            messages: List of message objects to persist.
            metadata: Optional metadata dict.

        Returns:
            Implementation-defined result.
        """
        async with self._lock:
            await self._ensure_setup()
            conn = await self._get_conn()
            for msg in messages:
                message_json = json.dumps(msg.model_dump()) if not isinstance(msg, str) else msg
                conn.execute(
                    """
                    INSERT INTO pending_writes (checkpoint_id, channel_name, value)
                    VALUES (?, ?, ?)
                    """,
                    (
                        config.get("thread_id", ""),
                        "messages",
                        message_json,
                    ),
                )
            conn.commit()
            return None

    async def aput_thread(self, config: dict[str, Any], state: StateT) -> StateT:
        """Persist thread state.

        Args:
            config: Configuration dictionary.
            state: State object to persist.

        Returns:
            The stored state object.
        """
        return await self.aput_state(config, state)
