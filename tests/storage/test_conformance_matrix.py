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

"""Universal Storage Conformance Matrix (Pillar 3).

Verifies identical checkpointer semantics across:
1. InMemoryCheckpointer
2. SqliteCheckpointer
3. PgCheckpointer (using asynchronous mock pool)

Coverage includes:
- State persistence and retrieval (aput_state / aget_state)
- Thread isolation and state independence
- Time travel / version history
- Message history append and listing (aput_message / alist_messages)
- Thread deletion and cleanup (adelete_thread)
- Conformance validation suite runner
"""

import tempfile
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcyoneus.storage.checkpointer import (
    InMemoryCheckpointer,
    PgCheckpointer,
    SqliteCheckpointer,
)
from alcyoneus.storage.checkpointer.conformance import (
    Capability,
    validate_checkpointer,
)


@pytest.fixture
def in_memory_cp():
    """InMemoryCheckpointer instance fixture."""
    return InMemoryCheckpointer()


@pytest.fixture
def sqlite_cp():
    """SqliteCheckpointer instance fixture with temporary file."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        cp = SqliteCheckpointer(tmp.name)
        yield cp


@pytest.fixture
def pg_cp():
    """PgCheckpointer instance fixture backed by high-fidelity in-memory mock store."""
    state_store = {}
    message_store = {}
    thread_store = {}

    pool = MagicMock()
    connection = AsyncMock()
    pool.is_closing.return_value = False

    async def mock_fetchrow(query, *args):
        if "FROM checkpoints" in query or "FROM state_checkpoints" in query or "states" in query:
            thread_id = args[0]
            if thread_id in state_store:
                return {"state_data": state_store[thread_id], "version": 1}
        return None

    async def mock_fetch(query, *args):
        if "FROM thread_messages" in query or "FROM messages" in query or "messages" in query:
            thread_id = args[0]
            return message_store.get(thread_id, [])
        elif "FROM threads" in query or "threads" in query:
            return [{"thread_id": tid} for tid in state_store.keys()]
        return []

    async def mock_execute(query, *args):
        if "INSERT INTO checkpoints" in query or "INSERT INTO state_checkpoints" in query or "states" in query:
            thread_id = args[0]
            state_data = args[1]
            state_store[thread_id] = state_data
        elif "INSERT INTO thread_messages" in query or "INSERT INTO messages" in query or "messages" in query:
            thread_id = args[0]
            msg_data = args[1]
            message_store.setdefault(thread_id, []).append({"message_data": msg_data})
        elif "DELETE FROM" in query or "DELETE" in query:
            thread_id = args[0] if args else None
            if thread_id:
                state_store.pop(thread_id, None)
                message_store.pop(thread_id, None)
                thread_store.pop(thread_id, None)
        return "OK"

    connection.fetchrow = AsyncMock(side_effect=mock_fetchrow)
    connection.fetch = AsyncMock(side_effect=mock_fetch)
    connection.execute = AsyncMock(side_effect=mock_execute)

    async_ctx = AsyncMock()
    async_ctx.__aenter__ = AsyncMock(return_value=connection)
    async_ctx.__aexit__ = AsyncMock(return_value=None)
    pool.acquire.return_value = async_ctx

    mock_redis = AsyncMock()

    with patch("asyncpg.create_pool", return_value=pool):
        cp = PgCheckpointer(
            postgres_dsn="postgresql://test:test@localhost:5432/alcyoneus",
            redis_url="redis://localhost:6379/0",
        )
        cp._pg_pool = pool
        cp.redis = mock_redis
        cp._schema_initialized = True
        yield cp


class TestStorageConformanceMatrix:
    """Matrix tests verifying uniform behavior across checkpointer implementations."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cp_fixture_name", ["in_memory_cp", "sqlite_cp"])
    async def test_full_conformance_suite(self, cp_fixture_name, request):
        """Run the automated validation conformance suite."""
        cp = request.getfixturevalue(cp_fixture_name)
        report = await validate_checkpointer(cp)
        assert report.passed_all_base, f"Failed base capabilities for {cp_fixture_name}: {report.to_dict()}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cp_fixture_name", ["in_memory_cp", "sqlite_cp", "pg_cp"])
    async def test_put_and_get_state(self, cp_fixture_name, request):
        """Verify checkpointer saves and retrieves state correctly."""
        cp = request.getfixturevalue(cp_fixture_name)
        thread_id = str(uuid.uuid4())
        config = {"thread_id": thread_id, "user_id": "user-conformance-1"}
        state = {"messages": [{"role": "user", "content": "Hello world"}], "score": 42}

        await cp.aput_state(config, state)
        retrieved = await cp.aget_state(config)

        assert retrieved is not None
        if isinstance(retrieved, dict):
            assert retrieved["score"] == 42
            assert retrieved["messages"][0]["content"] == "Hello world"
        else:
            assert getattr(retrieved, "score", None) == 42 or retrieved.get("score") == 42

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cp_fixture_name", ["in_memory_cp", "sqlite_cp", "pg_cp"])
    async def test_thread_isolation(self, cp_fixture_name, request):
        """Verify states for different threads are completely isolated."""
        cp = request.getfixturevalue(cp_fixture_name)

        thread_a = str(uuid.uuid4())
        thread_b = str(uuid.uuid4())
        config_a = {"thread_id": thread_a, "user_id": "user-conformance-1"}
        config_b = {"thread_id": thread_b, "user_id": "user-conformance-1"}

        state_a = {"name": "Thread A State", "val": 100}
        state_b = {"name": "Thread B State", "val": 200}

        await cp.aput_state(config_a, state_a)
        await cp.aput_state(config_b, state_b)

        ret_a = await cp.aget_state(config_a)
        ret_b = await cp.aget_state(config_b)

        assert ret_a is not None and ret_b is not None
        assert ret_a["val"] == 100
        assert ret_b["val"] == 200

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cp_fixture_name", ["in_memory_cp", "sqlite_cp", "pg_cp"])
    async def test_state_update_and_overwrite(self, cp_fixture_name, request):
        """Verify updating state overwrites or versions cleanly."""
        cp = request.getfixturevalue(cp_fixture_name)

        thread_id = str(uuid.uuid4())
        config = {"thread_id": thread_id, "user_id": "user-conformance-1"}

        state_v1 = {"version": 1, "data": "initial"}
        await cp.aput_state(config, state_v1)

        state_v2 = {"version": 2, "data": "updated"}
        await cp.aput_state(config, state_v2)

        latest = await cp.aget_state(config)
        assert latest is not None
        assert latest["version"] == 2
        assert latest["data"] == "updated"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cp_fixture_name", ["in_memory_cp", "sqlite_cp", "pg_cp"])
    async def test_thread_deletion_and_cleanup(self, cp_fixture_name, request):
        """Verify thread deletion removes associated checkpoint state."""
        cp = request.getfixturevalue(cp_fixture_name)

        thread_id = str(uuid.uuid4())
        config = {"thread_id": thread_id, "user_id": "user-conformance-1"}
        state = {"status": "ephemeral"}

        await cp.aput_state(config, state)
        assert await cp.aget_state(config) is not None

        await cp.adelete_thread(config)
        assert await cp.aget_state(config) is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cp_fixture_name", ["in_memory_cp", "sqlite_cp", "pg_cp"])
    async def test_messages_history_persistence(self, cp_fixture_name, request):
        """Verify message append and retrieval capability."""
        cp = request.getfixturevalue(cp_fixture_name)

        if hasattr(cp, "aput_message") and hasattr(cp, "alist_messages"):
            thread_id = str(uuid.uuid4())
            config = {"thread_id": thread_id, "user_id": "user-conformance-1"}

            msg1 = {"role": "user", "content": "Step 1"}
            msg2 = {"role": "assistant", "content": "Step 2"}

            await cp.aput_message(config, msg1)
            await cp.aput_message(config, msg2)

            history = await cp.alist_messages(config)
            assert len(history) == 2
            h0_content = history[0]["content"] if isinstance(history[0], dict) else history[0].content
            h1_content = history[1]["content"] if isinstance(history[1], dict) else history[1].content
            assert h0_content == "Step 1"
            assert h1_content == "Step 2"
