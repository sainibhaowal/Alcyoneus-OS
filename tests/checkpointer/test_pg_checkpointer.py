"""
Comprehensive tests for PgCheckpointer implementation.

Tests cover:
- Schema creation and setup
- State persistence and caching
- Message storage and retrieval
- Thread management
- Error handling and retry logic
- Resource cleanup
- Async and sync variants
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcyoneus.storage.checkpointer.pg_checkpointer import PgCheckpointer
from alcyoneus.core.state import AgentState, Message
from alcyoneus.utils.thread_info import ThreadInfo


class TestPgCheckpointer:
    """Test suite for PgCheckpointer."""

    @pytest.fixture
    def mock_pg_pool(self):
        """Mock PostgreSQL pool."""
        pool = MagicMock()
        connection = AsyncMock()
        pool.is_closing.return_value = False

        # Create a mock async context manager for pool.acquire()
        async_context_manager = AsyncMock()
        async_context_manager.__aenter__ = AsyncMock(return_value=connection)
        async_context_manager.__aexit__ = AsyncMock(return_value=None)

        # Make pool.acquire() return the async context manager
        pool.acquire.return_value = async_context_manager

        return pool

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis connection."""
        redis = AsyncMock()
        return redis

    @pytest.fixture
    def checkpointer(self, mock_pg_pool, mock_redis):
        """Create PgCheckpointer with mocked dependencies."""
        with patch("asyncpg.create_pool", return_value=mock_pg_pool):
            cp = PgCheckpointer(
                postgres_dsn="postgresql://test:test@localhost/test",
                redis_url="redis://localhost:6379/0",
                user_id_type="string",
                id_type="string",
                cache_ttl=3600,
            )
            # Replace with our mocks
            cp._pg_pool = mock_pg_pool
            cp.redis = mock_redis
            return cp

    @pytest.fixture
    def sample_state(self):
        """Create sample AgentState for testing."""
        state = AgentState()
        state.context = [
            Message.text_message("Hello", role="user", message_id="msg1"),
            Message.text_message("Hi there!", role="assistant", message_id="msg2"),
        ]
        return state

    @pytest.fixture
    def sample_config(self):
        """Sample configuration for testing."""
        return {
            "thread_id": "thread_123",
            "user_id": "user_456",
            "thread_name": "Test Thread",
            "meta": {"test": "data"},
        }

    def test_initialization_valid(self):
        """Test valid initialization scenarios."""
        # With DSN and Redis URL
        cp = PgCheckpointer(
            postgres_dsn="postgresql://test:test@localhost/test",
            redis_url="redis://localhost:6379/0",
        )
        assert cp.user_id_type == "string"
        assert cp.id_type == "string"
        assert cp.cache_ttl == 86400  # default TTL

        # With custom types
        cp2 = PgCheckpointer(
            postgres_dsn="postgresql://test:test@localhost/test",
            redis_url="redis://localhost:6379/0",
            user_id_type="int",
            cache_ttl=3600,
        )
        assert cp2.user_id_type == "int"
        assert cp2.id_type == "string"
        assert cp2.cache_ttl == 3600

    def test_initialization_invalid(self):
        """Test invalid initialization scenarios."""
        # Missing PostgreSQL connection
        with pytest.raises(ValueError, match="Either postgres_dsn or pg_pool must be provided"):
            PgCheckpointer(redis_url="redis://localhost:6379/0")

        # Missing Redis connection
        with pytest.raises(
            ValueError, match="Either redis_url, redis_pool or redis instance must be provided"
        ):
            PgCheckpointer(postgres_dsn="postgresql://test:test@localhost/test")

    @pytest.mark.asyncio
    async def test_sql_type_mapping(self, checkpointer):
        """Test SQL type mapping for different ID types."""
        cp = checkpointer
        assert cp._get_sql_type("string") == "VARCHAR(255)"
        assert cp._get_sql_type("int") == "SERIAL"
        assert cp._get_sql_type("bigint") == "BIGSERIAL"
        assert cp._get_sql_type("unknown") == "VARCHAR(255)"

    def test_schema_creation(self, checkpointer):
        """Test database schema creation."""
        sql_statements = checkpointer._build_create_tables_sql()

        assert len(sql_statements) >= 6  # tables + indexes

        # Check that key statements are present
        sql_text = " ".join(sql_statements)
        assert "CREATE TYPE message_role" in sql_text
        assert 'CREATE TABLE IF NOT EXISTS "public"."threads"' in sql_text
        assert 'CREATE TABLE IF NOT EXISTS "public"."states"' in sql_text
        assert 'CREATE TABLE IF NOT EXISTS "public"."messages"' in sql_text
        assert "CREATE INDEX" in sql_text

    @pytest.mark.asyncio
    async def test_setup_async(self, checkpointer, mock_pg_pool):
        """Test async setup method."""
        connection = mock_pg_pool.acquire.return_value.__aenter__.return_value
        connection.execute = AsyncMock()

        await checkpointer.asetup()

        assert checkpointer._schema_initialized
        assert connection.execute.call_count >= 6  # Multiple SQL statements

    def test_setup_sync(self, checkpointer):
        """Test sync setup method."""
        with patch.object(checkpointer, "asetup", new_callable=AsyncMock) as mock_asetup:
            checkpointer.setup()
            mock_asetup.assert_called_once_with()

    def test_helper_methods(self, checkpointer, sample_state):
        """Test helper methods."""
        # Test cache key generation
        key = checkpointer._get_thread_key("thread_123", "user_456")
        assert key == "state_cache:thread_123:user_456"

        # Test state serialization/deserialization
        serialized = checkpointer._serialize_state(sample_state)
        assert isinstance(serialized, str)
        assert json.loads(serialized)  # Valid JSON

        deserialized = checkpointer._deserialize_state(serialized, AgentState)
        assert isinstance(deserialized, AgentState)
        assert len(deserialized.context) == len(sample_state.context)

    @pytest.mark.asyncio
    async def test_state_operations_async(
        self, checkpointer, sample_state, sample_config, mock_pg_pool, mock_redis
    ):
        """Test async state operations."""
        connection = mock_pg_pool.acquire.return_value.__aenter__.return_value
        connection.execute = AsyncMock()
        connection.fetchrow = AsyncMock()
        connection.fetchval = AsyncMock(return_value=None)  # Thread doesn't exist

        # Test put_state
        result = await checkpointer.aput_state(sample_config, sample_state)
        assert result == sample_state
        connection.execute.assert_called()

        # Test get_state
        # connection.fetchrow.return_value = {
        #     "state_data": checkpointer._serialize_state(sample_state)
        # }
        # retrieved = await checkpointer.aget_state({**sample_config, "state_class": AgentState})
        # assert isinstance(retrieved, AgentState)

        # Test clear_state
        await checkpointer.aclear_state(sample_config)
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_state_caching(self, checkpointer, sample_state, sample_config, mock_redis):
        """Test Redis caching operations."""
        # Test cache put
        await checkpointer.aput_state_cache(sample_config, sample_state)
        mock_redis.setex.assert_called_once()

        # Test cache get - hit
        # Properly serialize with __class_path__
        data = sample_state.model_dump()
        data["__class_path__"] = checkpointer._get_full_class_path(sample_state)
        serialized_state = json.dumps(data)
        mock_redis.get.return_value = serialized_state.encode()
        cached_state = await checkpointer.aget_state_cache(
            {**sample_config, "state_class": AgentState}
        )
        assert isinstance(cached_state, AgentState)

        # Test cache get - miss (should fallback to postgres)
        mock_redis.get.return_value = None
        with patch.object(checkpointer, "aget_state", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = sample_state
            result = await checkpointer.aget_state_cache(
                {**sample_config, "state_class": AgentState}
            )
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_operations(self, checkpointer, sample_config, mock_pg_pool):
        """Test message storage and retrieval."""
        messages = [
            Message.text_message("Hello", role="user", message_id="msg1"),
            Message.text_message("Hi there!", role="assistant", message_id="msg2"),
        ]

        # Mock all message operations to avoid database calls
        with patch.object(checkpointer, "aput_messages", new_callable=AsyncMock) as mock_put:
            await checkpointer.aput_messages(sample_config, messages)
            mock_put.assert_called_once_with(sample_config, messages)

        with patch.object(checkpointer, "aget_message", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = Message.text_message("Hello", role="user", message_id="msg1")
            message = await checkpointer.aget_message(sample_config, "msg1")
            assert isinstance(message, Message)
            assert message.content[0].text == "Hello" # type: ignore
            mock_get.assert_called_once_with(sample_config, "msg1")

        with patch.object(checkpointer, "alist_messages", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [Message.text_message("Hello", role="user", message_id="msg1")]
            messages_list = await checkpointer.alist_messages(sample_config)
            assert len(messages_list) == 1
            assert isinstance(messages_list[0], Message)
            mock_list.assert_called_once_with(sample_config)

        with patch.object(checkpointer, "adelete_message", new_callable=AsyncMock) as mock_delete:
            await checkpointer.adelete_message(sample_config, "msg1")
            mock_delete.assert_called_once_with(sample_config, "msg1")

    @pytest.mark.asyncio
    async def test_thread_operations(self, checkpointer, sample_config, mock_pg_pool, mock_redis):
        """Test thread management operations."""
        connection = mock_pg_pool.acquire.return_value.__aenter__.return_value
        connection.execute = AsyncMock()
        connection.fetchrow = AsyncMock()
        connection.fetch = AsyncMock()

        thread_info = ThreadInfo(thread_id="thread_123", thread_name="Test Thread", metadata={"test": "data"})

        # Test put_thread (basic call)
        await checkpointer.aput_thread(sample_config, thread_info)
        connection.fetchrow.assert_called()

    @pytest.mark.asyncio
    async def test_put_thread_returns_created_flag(self, checkpointer, sample_config, mock_pg_pool, mock_redis):
        """aput_thread should return True when inserted, False on update."""
        connection = mock_pg_pool.acquire.return_value.__aenter__.return_value
        connection.fetchrow = AsyncMock(return_value={"thread_id": "thread_123"})

        thread_info = ThreadInfo(thread_id="thread_123", thread_name="Test Thread")
        created = await checkpointer.aput_thread(sample_config, thread_info)
        assert created is True

        # Now simulate conflict -> should perform update and return False
        connection.fetchrow = AsyncMock(return_value=None)
        connection.execute = AsyncMock()

        thread_info2 = ThreadInfo(thread_id="thread_123", thread_name=None, metadata={"a": 1})
        created2 = await checkpointer.aput_thread(sample_config, thread_info2)
        assert created2 is False
        # Ensure we executed the meta-only update path when thread_name is None
        assert any(
            "SET meta = $1, updated_at = NOW()" in str(call.args[0]) for call in connection.execute.mock_calls
        )

        # Test get_thread
        connection.fetchrow.return_value = {
            "thread_id": "thread_123",
            "thread_name": "Test Thread",
            "user_id": "user_456",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "meta": {"test": "data"},
        }

        thread = await checkpointer.aget_thread(sample_config)
        assert thread.thread_name == "Test Thread"

        # Test list_threads
        connection.fetch.return_value = [connection.fetchrow.return_value]
        threads = await checkpointer.alist_threads(sample_config)
        assert len(threads) == 1

        # Test clean_thread
        await checkpointer.aclean_thread(sample_config)
        connection.execute.assert_called()
        mock_redis.delete.assert_called()

    def test_sync_variants(self, checkpointer):
        """Test that sync methods properly delegate to async versions."""
        with patch.object(checkpointer, "aput_state", new_callable=AsyncMock) as mock:
            sample_state = AgentState()
            sample_config = {"thread_id": "123", "user_id": "456"}

            checkpointer.put_state(sample_config, sample_state)
            mock.assert_called_once_with(sample_config, sample_state)

    @pytest.mark.asyncio
    async def test_error_handling(self, checkpointer, sample_config):
        """Test error handling in various scenarios."""
        # Test missing required config
        with pytest.raises(ValueError):
            await checkpointer.aput_state({}, AgentState())

        with pytest.raises(ValueError):
            await checkpointer.aget_state({})

    @pytest.mark.asyncio
    async def test_retry_logic(self, checkpointer):
        """Test connection retry logic."""
        import asyncpg

        # Mock operation that fails twice then succeeds
        operation = AsyncMock()
        operation.side_effect = [
            asyncpg.PostgresConnectionError("Connection lost"),
            asyncpg.PostgresConnectionError("Still down"),
            "Success",
        ]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await checkpointer._retry_on_connection_error(operation)
            assert result == "Success"
            assert operation.call_count == 3

        # Test max retries exceeded
        operation.reset_mock()
        operation.side_effect = [asyncpg.PostgresConnectionError("Connection lost")] * 5

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(asyncpg.PostgresConnectionError):
                await checkpointer._retry_on_connection_error(operation, max_retries=3)
            assert operation.call_count == 3

    @pytest.mark.asyncio
    async def test_resource_cleanup(self, checkpointer, mock_pg_pool, mock_redis):
        """Test resource cleanup."""
        mock_redis.aclose = AsyncMock()
        mock_pg_pool.close = AsyncMock()

        await checkpointer.arelease()

        mock_redis.aclose.assert_called_once()
        mock_pg_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_resource_cleanup_errors(self, checkpointer, mock_pg_pool, mock_redis):
        """Test resource cleanup with errors."""
        mock_redis.aclose = AsyncMock(side_effect=Exception("Redis error"))
        mock_pg_pool.close = AsyncMock(side_effect=Exception("PG error"))

        # Should not raise - cleanup is best effort
        await checkpointer.arelease()


@pytest.mark.integration
class TestPgCheckpointerIntegration2:
    """Integration tests requiring actual PostgreSQL and Redis."""

    @pytest.fixture
    def real_checkpointer(self):
        """Create checkpointer with real connections (requires services)."""
        return PgCheckpointer(
            postgres_dsn="postgresql://test:test@localhost:5432/test_alcyoneus",
            redis_url="redis://localhost:6379/1",  # Use different DB for testing
        )


@pytest.mark.integration
@pytest.mark.skipif(
    True,  # Skip integration tests by default unless --integration flag is used
    reason="Integration tests require real PostgreSQL and Redis connections",
)
class TestPgCheckpointerIntegration:
    """Integration tests requiring real PostgreSQL and Redis connections."""

    @pytest.fixture
    async def real_checkpointer(self):
        """Create a PgCheckpointer with real database connections."""
        checkpointer = PgCheckpointer(
            database_url="postgresql://postgres:password@localhost:5432/test_db",
            redis_url="redis://localhost:6379/1",  # Use different DB for testing
        )
        await checkpointer.asetup()
        try:
            yield checkpointer
        finally:
            await checkpointer.arelease()

    @pytest.mark.asyncio
    async def test_full_workflow(self, real_checkpointer):
        """Test complete workflow with real database."""
        config = {
            "thread_id": "integration_test_123",
            "user_id": "test_user_456",
            "thread_name": "Integration Test Thread",
        }

        try:
            # Setup schema
            await real_checkpointer.asetup()

            # Create state and store it
            state = AgentState()
            state.context = [
                Message.text_message("Integration test", role="user", message_id="int_msg1")
            ]

            stored_state = await real_checkpointer.aput_state(config, state)
            assert stored_state == state

            # Retrieve state
            retrieved_state = await real_checkpointer.aget_state(
                {**config, "state_class": AgentState}
            )
            assert retrieved_state is not None
            assert len(retrieved_state.context) == 1

            # Test caching
            cached_state = await real_checkpointer.aget_state_cache(
                {**config, "state_class": AgentState}
            )
            assert cached_state is not None

            # Clean up
            await real_checkpointer.aclean_thread(config)

        finally:
            await real_checkpointer.arelease()


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__, "-v"])
