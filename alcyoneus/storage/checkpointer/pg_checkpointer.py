import asyncio
import importlib
import json
import logging
import os
import re
from contextlib import suppress
from enum import Enum
from typing import Any, TypeVar


try:
    from injectq import InjectQ
except ImportError:
    InjectQ = Any


from alcyoneus.core.exceptions.storage_exceptions import (
    StorageError,
    TransientStorageError,
)
from alcyoneus.utils import ThreadInfo, metrics


try:
    import asyncpg
    from asyncpg import Pool

    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False
    asyncpg = None  # type: ignore
    Pool = None  # type: ignore

try:
    from redis.asyncio import ConnectionPool, Redis

    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    ConnectionPool = None  # type: ignore
    Redis = None  # type: ignore

from alcyoneus.core.state import AgentState, Message

from .base_checkpointer import BaseCheckpointer


logger = logging.getLogger("alcyoneus.checkpointer.pg")

StateT = TypeVar("StateT", bound="AgentState")

# Default TTL for Redis cache (24 hours)
DEFAULT_CACHE_TTL = 86400

# SQL type mapping for ID types
ID_TYPE_MAP = {
    "string": "VARCHAR(255)",
    "int": "SERIAL",
    "bigint": "BIGSERIAL",
}


class PgCheckpointer(BaseCheckpointer[StateT]):
    """
    Implements a checkpointer using PostgreSQL and Redis for persistent and cached state management.

    This class provides asynchronous and synchronous methods for storing, retrieving, and managing
    agent states, messages, and threads. PostgreSQL is used for durable storage, while Redis
    provides fast caching with TTL.

    Features:
        - Async-first design with sync fallbacks
        - Configurable ID types (string, int, bigint)
        - Connection pooling for both PostgreSQL and Redis
        - Proper error handling and resource management
        - Schema migration support

    Args:
        postgres_dsn (str, optional): PostgreSQL connection string.
        pg_pool (Any, optional): Existing asyncpg Pool instance.
        pool_config (dict, optional): Configuration for new pg pool creation.
        redis_url (str, optional): Redis connection URL.
        redis (Any, optional): Existing Redis instance.
        redis_pool (Any, optional): Existing Redis ConnectionPool.
        redis_pool_config (dict, optional): Configuration for new redis pool creation.
        **kwargs: Additional configuration options:
            - user_id_type: Type for user_id fields ('string', 'int', 'bigint')
            - cache_ttl: Redis cache TTL in seconds
            - release_resources: Whether to release resources on cleanup

    Raises:
        ImportError: If required dependencies are missing.
        ValueError: If required connection details are missing.
    """

    def __init__(
        self,
        # postgress connection details
        postgres_dsn: str | None = None,
        pg_pool: Any | None = None,
        pool_config: dict | None = None,
        # redis connection details
        redis_url: str | None = None,
        redis: Any | None = None,
        redis_pool: Any | None = None,
        redis_pool_config: dict | None = None,
        # database schema
        schema: str = "public",
        # other configurations - combine to reduce args
        **kwargs,
    ):
        """
        Initializes PgCheckpointer with PostgreSQL and Redis connections.

        Args:
            postgres_dsn (str, optional): PostgreSQL connection string.
            pg_pool (Any, optional): Existing asyncpg Pool instance.
            pool_config (dict, optional): Configuration for new pg pool creation.
            redis_url (str, optional): Redis connection URL.
            redis (Any, optional): Existing Redis instance.
            redis_pool (Any, optional): Existing Redis ConnectionPool.
            redis_pool_config (dict, optional): Configuration for new redis pool creation.
            schema (str, optional): PostgreSQL schema name. Defaults to "public".
            **kwargs: Additional configuration options.

        Raises:
            ImportError: If required dependencies are missing.
            ValueError: If required connection details are missing.
        """
        # Check for required dependencies
        if not HAS_ASYNCPG:
            raise ImportError(
                "PgCheckpointer requires 'asyncpg' package. "
                "Install with: pip install alcyoneus[pg_checkpoint]"
            )

        if not HAS_REDIS:
            raise ImportError(
                "PgCheckpointer requires 'redis' package. "
                "Install with: pip install alcyoneus[pg_checkpoint]"
            )

        self.user_id_type = kwargs.get("user_id_type", "string")
        # allow explicit override via kwargs, fallback to InjectQ, then default
        self.id_type = kwargs.get(
            "id_type", InjectQ.get_instance().try_get("generated_id_type", "string")
        )
        self.cache_ttl = kwargs.get("cache_ttl", DEFAULT_CACHE_TTL)
        self.release_resources = kwargs.get("release_resources", False)

        # Validate schema name to prevent SQL injection
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", schema):
            raise ValueError(
                f"Invalid schema name: {schema}. Schema must match pattern ^[a-zA-Z_][a-zA-Z0-9_]*$"
            )
        self.schema = schema

        self._schema_initialized = False
        self._loop: asyncio.AbstractEventLoop | None = None

        # Store pool configuration for lazy initialization
        self._pg_pool_config = {
            "pg_pool": pg_pool,
            "postgres_dsn": postgres_dsn,
            "pool_config": pool_config or {},
        }

        # Initialize pool immediately if provided, otherwise defer
        if pg_pool is not None:
            self._pg_pool = pg_pool
        else:
            self._pg_pool = None

        # Now check and initialize connections
        if not pg_pool and not postgres_dsn:
            raise ValueError("Either postgres_dsn or pg_pool must be provided.")

        if not redis and not redis_url and not redis_pool:
            raise ValueError("Either redis_url, redis_pool or redis instance must be provided.")

        # Initialize Redis connection (synchronous)
        self.redis = self._create_redis_pool(redis, redis_pool, redis_url, redis_pool_config or {})

    def _create_redis_pool(
        self,
        redis: Any | None,
        redis_pool: Any | None,
        redis_url: str | None,
        redis_pool_config: dict,
    ) -> Any:
        """
        Create or use an existing Redis connection.

        Args:
            redis (Any, optional): Existing Redis instance.
            redis_pool (Any, optional): Existing Redis ConnectionPool.
            redis_url (str, optional): Redis connection URL.
            redis_pool_config (dict): Configuration for new redis pool creation.

        Returns:
            Redis: Redis connection instance.

        Raises:
            ValueError: If redis_url is not provided when creating a new connection.
        """
        if redis:
            return redis

        if redis_pool:
            return Redis(connection_pool=redis_pool)  # type: ignore

        # as we are creating new pool, redis_url must be provided
        # and we will release the resources if needed
        if not redis_url:
            raise ValueError("redis_url must be provided when creating new Redis connection")

        self.release_resources = True
        return Redis(
            connection_pool=ConnectionPool.from_url(  # type: ignore
                redis_url,
                **redis_pool_config,
            )
        )

    def _get_table_name(self, table: str) -> str:
        """
        Get the schema-qualified table name.

        Args:
            table (str): The base table name (e.g., 'threads', 'states', 'messages')

        Returns:
            str: The schema-qualified table name (e.g., '"public"."threads"')
        """
        # Validate table name to prevent SQL injection
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table):
            raise ValueError(
                f"Invalid table name: {table}. Table must match pattern ^[a-zA-Z_][a-zA-Z0-9_]*$"
            )
        return f'"{self.schema}"."{table}"'

    def _create_pg_pool(self, pg_pool: Any, postgres_dsn: str | None, pool_config: dict) -> Any:
        """
        Create or use an existing PostgreSQL connection pool.

        Args:
            pg_pool (Any, optional): Existing asyncpg Pool instance.
            postgres_dsn (str, optional): PostgreSQL connection string.
            pool_config (dict): Configuration for new pg pool creation.

        Returns:
            Pool: PostgreSQL connection pool.
        """
        if pg_pool:
            return pg_pool
        # as we are creating new pool, postgres_dsn must be provided
        # and we will release the resources if needed
        self.release_resources = True
        return asyncpg.create_pool(dsn=postgres_dsn, **pool_config)  # type: ignore

    async def _get_pg_pool(self) -> Any:
        """
        Get PostgreSQL pool, creating it if necessary.

        Returns:
            Pool: PostgreSQL connection pool.
        """
        if self._pg_pool is None:
            config = self._pg_pool_config
            self._pg_pool = await self._create_pg_pool(
                config["pg_pool"], config["postgres_dsn"], config["pool_config"]
            )
        return self._pg_pool

    def _get_sql_type(self, type_name: str) -> str:
        """
        Get SQL type for given configuration type.

        Args:
            type_name (str): Type name ('string', 'int', 'bigint').

        Returns:
            str: Corresponding SQL type.
        """
        return ID_TYPE_MAP.get(type_name, "VARCHAR(255)")

    def _get_json_serializer(self):
        """Get optimal JSON serializer based on FAST_JSON env var."""
        if os.environ.get("FAST_JSON", "0") == "1":
            try:
                import orjson

                return orjson.dumps
            except ImportError:
                try:
                    import msgspec  # type: ignore

                    return msgspec.json.encode
                except ImportError:
                    pass
        return json.dumps

    def _get_current_schema_version(self) -> int:
        """Return current expected schema version."""
        return 1  # increment when schema changes

    def _build_create_tables_sql(self) -> list[str]:
        """
        Build SQL statements for table creation with dynamic ID types.

        Returns:
            list[str]: List of SQL statements for table creation.
        """
        thread_id_type = self._get_sql_type(self.id_type)
        user_id_type = self._get_sql_type(self.user_id_type)
        message_id_type = self._get_sql_type(self.id_type)

        # For AUTO INCREMENT types, we need to handle primary key differently
        thread_pk = (
            "thread_id SERIAL PRIMARY KEY"
            if self.id_type == "int"
            else f"thread_id {thread_id_type} PRIMARY KEY"
        )
        message_pk = (
            "message_id SERIAL PRIMARY KEY"
            if self.id_type == "int"
            else f"message_id {message_id_type} PRIMARY KEY"
        )

        return [
            # Schema version tracking table
            f"""
            CREATE TABLE IF NOT EXISTS {self._get_table_name("schema_version")} (
                version INT PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT NOW()
            )
            """,
            # Create message role enum (safe for older Postgres versions)
            (
                "DO $$\n"
                "BEGIN\n"
                "    CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system', 'tool');\n"
                "EXCEPTION\n"
                "    WHEN duplicate_object THEN NULL;\n"
                "END$$;"
            ),
            # Create threads table
            f"""
            CREATE TABLE IF NOT EXISTS {self._get_table_name("threads")} (
                {thread_pk},
                thread_name VARCHAR(255),
                user_id {user_id_type} NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                meta JSONB DEFAULT '{{}}'::jsonb
            )
            """,
            # Create states table
            f"""
            CREATE TABLE IF NOT EXISTS {self._get_table_name("states")} (
                state_id SERIAL PRIMARY KEY,
                thread_id {thread_id_type} NOT NULL
                    REFERENCES {self._get_table_name("threads")}(thread_id)
                    ON DELETE CASCADE,
                state_data JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                meta JSONB DEFAULT '{{}}'::jsonb
            )
            """,
            # Create messages table
            f"""
            CREATE TABLE IF NOT EXISTS {self._get_table_name("messages")} (
                {message_pk},
                thread_id {thread_id_type} NOT NULL
                    REFERENCES {self._get_table_name("threads")}(thread_id)
                    ON DELETE CASCADE,
                role message_role NOT NULL,
                content TEXT NOT NULL,
                tool_calls JSONB,
                tool_call_id VARCHAR(255),
                reasoning TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                total_tokens INT DEFAULT 0,
                usages JSONB DEFAULT '{{}}'::jsonb,
                meta JSONB DEFAULT '{{}}'::jsonb
            )
            """,
            # Create indexes
            f"CREATE INDEX IF NOT EXISTS idx_threads_user_id ON "
            f"{self._get_table_name('threads')}(user_id)",
            f"CREATE INDEX IF NOT EXISTS idx_states_thread_id ON "
            f"{self._get_table_name('states')}(thread_id)",
            f"CREATE INDEX IF NOT EXISTS idx_messages_thread_id ON "
            f"{self._get_table_name('messages')}(thread_id)",
        ]

    async def _check_and_apply_schema_version(self, conn) -> None:
        """Check current version and update if needed."""
        try:
            # Check if schema version exists
            row = await conn.fetchrow(
                f"SELECT version FROM {self._get_table_name('schema_version')} "  # noqa: S608
                f"ORDER BY version DESC LIMIT 1"
            )
            current_version = row["version"] if row else 0
            target_version = self._get_current_schema_version()

            if current_version < target_version:
                logger.info(
                    "Upgrading schema from version %d to %d", current_version, target_version
                )
                # Insert new version
                await conn.execute(
                    f"INSERT INTO {self._get_table_name('schema_version')} (version) VALUES ($1)",  # noqa: S608
                    target_version,
                )
        except Exception as e:
            logger.debug("Schema version check failed (expected on first run): %s", e)
            # Insert initial version
            with suppress(Exception):
                await conn.execute(
                    f"INSERT INTO {self._get_table_name('schema_version')} (version) VALUES ($1)",  # noqa: S608
                    self._get_current_schema_version(),
                )

    async def _initialize_schema(self) -> None:
        """
        Initialize database schema if not already done.

        Returns:
            None
        """
        if self._schema_initialized:
            return

        logger.debug(
            "Initializing database schema with types: id_type=%s, user_id_type=%s",
            self.id_type,
            self.user_id_type,
        )

        async with (await self._get_pg_pool()).acquire() as conn:
            try:
                sql_statements = self._build_create_tables_sql()
                for sql in sql_statements:
                    logger.debug("Executing SQL: %s", sql.strip())
                    await conn.execute(sql)

                # Check and apply schema version tracking
                await self._check_and_apply_schema_version(conn)

                self._schema_initialized = True
                logger.debug("Database schema initialized successfully")
            except Exception as e:
                logger.error("Failed to initialize database schema: %s", e)
                raise

    ###########################
    #### SETUP METHODS ########
    ###########################

    async def asetup(self) -> Any:
        """
        Asynchronous setup method. Initializes database schema.

        Returns:
            Any: True if setup completed.
        """
        logger.info(
            "Setting up PgCheckpointer (async)",
            extra={
                "id_type": self.id_type,
                "user_id_type": self.user_id_type,
                "schema": self.schema,
            },
        )
        await self._initialize_schema()
        logger.info("PgCheckpointer setup completed")
        return True

    ###########################
    #### HELPER METHODS #######
    ###########################

    def _validate_config(self, config: dict[str, Any]) -> tuple[str | int, str | int]:
        """
        Extract and validate thread_id and user_id from config.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            tuple: (thread_id, user_id)

        Raises:
            ValueError: If required fields are missing.
        """
        thread_id = config.get("thread_id")
        user_id = config.get("user_id")
        if not user_id:
            raise ValueError("user_id must be provided in config")

        if not thread_id:
            raise ValueError("Both thread_id must be provided in config")

        return thread_id, user_id

    def _get_thread_key(
        self,
        thread_id: str | int,
        user_id: str | int,
    ) -> str:
        """
        Get Redis cache key for thread state.

        Args:
            thread_id (str|int): Thread identifier.
            user_id (str|int): User identifier.

        Returns:
            str: Redis cache key.
        """
        return f"state_cache:{thread_id}:{user_id}"

    def _get_generic_cache_key(self, namespace: str, key: str) -> str:
        """Build a Redis key for shared non-state cache entries."""
        return f"generic_cache:{namespace}:{key}"

    def _serialize_state(self, state: StateT) -> str:
        """
        Serialize state to JSON string for storage.

        Args:
            state (StateT): State object.

        Returns:
            str: JSON string.
        """

        def enum_handler(obj):
            if isinstance(obj, Enum):
                return obj.value
            return str(obj)

        return json.dumps(state.model_dump(), default=enum_handler)

    def _deserialize_state(
        self,
        data: Any,
        state_class: type[StateT],
    ) -> StateT:
        """
        Deserialize JSON/JSONB back to state object.

        Args:
            data (Any): JSON string or dict/list.
            state_class (type): State class type.

        Returns:
            StateT: Deserialized state object.

        Raises:
            Exception: If deserialization fails.
        """
        try:
            if isinstance(data, bytes | bytearray):
                data = data.decode()
            if isinstance(data, str):
                return state_class.model_validate(json.loads(data))
            # Assume it's already a dict/list
            return state_class.model_validate(data)
        except Exception:
            # Last-resort: coerce to string and attempt parse, else raise
            if isinstance(data, str):
                return state_class.model_validate(json.loads(data))
            raise

    async def _retry_on_connection_error(
        self,
        operation,
        *args,
        max_retries=3,
        **kwargs,
    ):
        """
        Retry database operations on connection errors.

        Args:
            operation: Callable operation.
            *args: Arguments.
            max_retries (int): Maximum retries.
            **kwargs: Keyword arguments.

        Returns:
            Any: Result of operation or None.

        Raises:
            Exception: If all retries fail.
        """
        last_exception = None

        # Define exception types to catch (only if asyncpg is available)
        exceptions_to_catch: list[type[Exception]] = [ConnectionError]
        if HAS_ASYNCPG and asyncpg:
            exceptions_to_catch.extend([asyncpg.PostgresConnectionError, asyncpg.InterfaceError])

        exception_tuple = tuple(exceptions_to_catch)

        for attempt in range(max_retries):
            try:
                return await operation(*args, **kwargs)
            except exception_tuple as e:
                last_exception = e
                if attempt < max_retries - 1:
                    wait_time = 2**attempt  # exponential backoff
                    logger.warning(
                        "Database connection error on attempt %d/%d, retrying in %ds: %s",
                        attempt + 1,
                        max_retries,
                        wait_time,
                        e,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                logger.error("Failed after %d attempts: %s", max_retries, e)
                break
            except Exception as e:
                # Don't retry on non-connection errors
                logger.error("Non-retryable error: %s", e)
                raise

        if last_exception:
            raise last_exception
        return None

    async def _ensure_thread_exists(
        self,
        thread_id: str | int,
        user_id: str | int,
        config: dict[str, Any],
    ) -> None:
        """
        Ensure thread exists in database, create if not.

        Args:
            thread_id (str|int): Thread identifier.
            user_id (str|int): User identifier.
            config (dict): Configuration dictionary.

        Returns:
            None

        Raises:
            Exception: If creation fails.
        """
        # Ensure schema is initialized before accessing tables
        try:

            async def _check_and_create_thread():
                async with (await self._get_pg_pool()).acquire() as conn:
                    exists = await conn.fetchval(
                        f"SELECT 1 FROM {self._get_table_name('threads')} "  # noqa: S608
                        f"WHERE thread_id = $1 AND user_id = $2",
                        thread_id,
                        user_id,
                    )

                    if not exists:
                        thread_name = config.get("thread_name", f"Thread {thread_id}")
                        meta = json.dumps(config.get("thread_meta", {}))
                        await conn.execute(
                            f"""
                            INSERT INTO {self._get_table_name("threads")}
                                (thread_id, thread_name, user_id, meta)
                            VALUES ($1, $2, $3, $4)
                            ON CONFLICT DO NOTHING
                            """,  # noqa: S608
                            thread_id,
                            thread_name,
                            user_id,
                            meta,
                        )
                        logger.debug("Created thread: thread_id=%s, user_id=%s", thread_id, user_id)

            await self._retry_on_connection_error(_check_and_create_thread, max_retries=3)

        except Exception as e:
            logger.error("Failed to ensure thread exists: %s", e)
            raise

    def _get_full_class_path(self, obj: object) -> str:
        cls = obj.__class__
        return f"{cls.__module__}.{cls.__name__}"

    def _import_class_from_path(self, path: str) -> type[AgentState]:
        module_name, class_name = path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, class_name)

    ###########################
    #### STATE METHODS ########
    ###########################

    async def aput_state(
        self,
        config: dict[str, Any],
        state: StateT,
    ) -> StateT:
        """
        Store state in PostgreSQL and optionally cache in Redis.

        Args:
            config (dict): Configuration dictionary.
            state (StateT): State object to store.

        Returns:
            StateT: The stored state object.

        Raises:
            StorageError: If storing fails.
        """
        # Ensure schema is initialized before accessing tables
        thread_id, user_id = self._validate_config(config)

        logger.debug("Storing state for thread_id=%s, user_id=%s", thread_id, user_id)
        metrics.counter("pg_checkpointer.save_state.attempts").inc()

        with metrics.timer("pg_checkpointer.save_state.duration"):
            try:
                # Ensure thread exists first
                await self._ensure_thread_exists(thread_id, user_id, config)

                # Store in PostgreSQL with retry logic
                data = state.model_dump()
                data["__class_path__"] = self._get_full_class_path(state)
                state_json = json.dumps(data)

                async def _store_state():
                    async with (await self._get_pg_pool()).acquire() as conn:
                        await conn.execute(
                            f"""
                            INSERT INTO {self._get_table_name("states")}
                                (thread_id, state_data, meta)
                            VALUES ($1, $2, $3)
                            ON CONFLICT DO NOTHING
                            """,  # noqa: S608
                            thread_id,
                            state_json,
                            json.dumps(config.get("meta", {})),
                        )

                await self._retry_on_connection_error(_store_state, max_retries=3)
                logger.debug("State stored successfully for thread_id=%s", thread_id)
                metrics.counter("pg_checkpointer.save_state.success").inc()
                return state

            except Exception as e:
                metrics.counter("pg_checkpointer.save_state.error").inc()
                logger.error("Failed to store state for thread_id=%s: %s", thread_id, e)
                if asyncpg and hasattr(asyncpg, "ConnectionDoesNotExistError"):
                    connection_errors = (
                        asyncpg.ConnectionDoesNotExistError,
                        asyncpg.InterfaceError,
                    )
                    if isinstance(e, connection_errors):
                        raise TransientStorageError(
                            message=f"Connection issue storing state: {e}",
                            error_code="STORAGE_TRANSIENT_001",
                            context={
                                "thread_id": thread_id,
                                "error_type": type(e).__name__,
                            },
                        ) from e
                raise StorageError(
                    message=f"Failed to store state: {e}",
                    error_code="STORAGE_001",
                    context={
                        "thread_id": thread_id,
                        "error_type": type(e).__name__,
                    },
                ) from e

    async def aget_state(self, config: dict[str, Any]) -> StateT | None:
        """
        Retrieve state from PostgreSQL.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            StateT | None: Retrieved state or None.

        Raises:
            Exception: If retrieval fails.
        """
        # Ensure schema is initialized before accessing tables
        thread_id, user_id = self._validate_config(config)

        logger.debug("Retrieving state for thread_id=%s, user_id=%s", thread_id, user_id)

        try:

            async def _get_state():
                async with (await self._get_pg_pool()).acquire() as conn:
                    return await conn.fetchrow(
                        f"""
                        SELECT state_data FROM {self._get_table_name("states")}
                        WHERE thread_id = $1
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,  # noqa: S608
                        thread_id,
                    )

            row = await self._retry_on_connection_error(_get_state, max_retries=3)

            if row:
                data = json.loads(row["state_data"])
                logger.debug("State found for thread_id=%s", thread_id)
                class_path = data.pop("__class_path__", None)
                if not class_path:
                    raise ValueError("Missing '__class_path__' in JSON data")

                cls = self._import_class_from_path(class_path)
                return cls.model_validate(data)  # type: ignore

            logger.debug("No state found for thread_id=%s", thread_id)
            return None

        except Exception as e:
            logger.error("Failed to retrieve state for thread_id=%s: %s", thread_id, e)
            raise

    async def aclear_state(self, config: dict[str, Any]) -> Any:
        """
        Clear state from PostgreSQL and Redis cache.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            Any: None

        Raises:
            Exception: If clearing fails.
        """
        # Ensure schema is initialized before accessing tables
        thread_id, user_id = self._validate_config(config)

        logger.debug("Clearing state for thread_id=%s, user_id=%s", thread_id, user_id)

        try:
            # Clear from PostgreSQL with retry logic
            async def _clear_state():
                async with (await self._get_pg_pool()).acquire() as conn:
                    await conn.execute(
                        f"DELETE FROM {self._get_table_name('states')} WHERE thread_id = $1",  # noqa: S608
                        thread_id,
                    )

            await self._retry_on_connection_error(_clear_state, max_retries=3)

            # Clear from Redis cache
            cache_key = self._get_thread_key(thread_id, user_id)
            await self.redis.delete(cache_key)

            logger.debug("State cleared for thread_id=%s", thread_id)

        except Exception as e:
            logger.error("Failed to clear state for thread_id=%s: %s", thread_id, e)
            raise

    async def aput_state_cache(self, config: dict[str, Any], state: StateT) -> Any | None:
        """
        Cache state in Redis with TTL.

        Args:
            config (dict): Configuration dictionary.
            state (StateT): State object to cache.

        Returns:
            Any | None: True if cached, None if failed.
        """
        # No DB access, but keep consistent
        thread_id, user_id = self._validate_config(config)

        logger.debug("Caching state for thread_id=%s, user_id=%s", thread_id, user_id)

        try:
            cache_key = self._get_thread_key(thread_id, user_id)
            data = state.model_dump()
            data["__class_path__"] = self._get_full_class_path(state)
            state_json = json.dumps(data)
            await self.redis.setex(cache_key, self.cache_ttl, state_json)
            logger.debug("State cached with key=%s, ttl=%d", cache_key, self.cache_ttl)
            return True

        except Exception as e:
            logger.error("Failed to cache state for thread_id=%s: %s", thread_id, e)
            # Don't raise - caching is optional
            return None

    async def aget_state_cache(self, config: dict[str, Any]) -> StateT | None:
        """
        Get state from Redis cache, fallback to PostgreSQL if miss.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            StateT | None: State object or None.
        """
        # Schema might be needed if we fall back to DB
        thread_id, user_id = self._validate_config(config)

        logger.debug("Getting cached state for thread_id=%s, user_id=%s", thread_id, user_id)

        try:
            # Try Redis first
            cache_key = self._get_thread_key(thread_id, user_id)
            cached_data = await self.redis.get(cache_key)

            if cached_data:
                data = json.loads(cached_data)
                logger.debug("Cache hit for thread_id=%s", thread_id)
                class_path = data.pop("__class_path__", None)
                if not class_path:
                    raise ValueError("Missing '__class_path__' in JSON data")

                cls = self._import_class_from_path(class_path)
                return cls.model_validate(data)  # type: ignore

            # Cache miss - fallback to PostgreSQL
            logger.debug("Cache miss for thread_id=%s, falling back to PostgreSQL", thread_id)
            state = await self.aget_state(config)

            # Cache the result for next time
            if state:
                await self.aput_state_cache(config, state)

            return state

        except Exception as e:
            logger.error("Failed to get cached state for thread_id=%s: %s", thread_id, e)
            # Fallback to PostgreSQL on error
            return await self.aget_state(config)

    async def aput_cache_value(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> Any | None:
        """Cache a generic JSON-serializable value in Redis."""
        try:
            cache_key = self._get_generic_cache_key(namespace, key)
            ttl = ttl_seconds or self.cache_ttl
            await self.redis.setex(cache_key, ttl, json.dumps(value))
            return True
        except Exception as e:
            logger.error("Failed to cache value for namespace=%s key=%s: %s", namespace, key, e)
            return None

    async def aget_cache_value(self, namespace: str, key: str) -> Any | None:
        """Retrieve a generic cache value from Redis."""
        try:
            cache_key = self._get_generic_cache_key(namespace, key)
            cached_data = await self.redis.get(cache_key)
            if not cached_data:
                return None
            return json.loads(cached_data)
        except Exception as e:
            logger.error(
                "Failed to get cached value for namespace=%s key=%s: %s", namespace, key, e
            )
            return None

    async def aclear_cache_value(self, namespace: str, key: str) -> Any | None:
        """Delete a generic cache value from Redis."""
        try:
            cache_key = self._get_generic_cache_key(namespace, key)
            return await self.redis.delete(cache_key)
        except Exception as e:
            logger.error(
                "Failed to clear cached value for namespace=%s key=%s: %s",
                namespace,
                key,
                e,
            )
            return None

    async def alist_cache_keys(
        self,
        namespace: str,
        prefix: str | None = None,
    ) -> list[str]:
        """List all cache keys for a namespace using Redis SCAN."""
        try:
            pattern = self._get_generic_cache_key(namespace, prefix or "*")
            keys: list[str] = []
            cursor = 0
            while True:
                cursor, found = await self.redis.scan(
                    cursor=cursor,
                    match=pattern,
                    count=100,
                )
                for raw_key in found:
                    key_str = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
                    # Strip the namespace prefix to return just the key part
                    ns_prefix = f"generic_cache:{namespace}:"
                    if key_str.startswith(ns_prefix):
                        keys.append(key_str[len(ns_prefix) :])
                if cursor == 0:
                    break
            return keys
        except Exception as e:
            logger.error(
                "Failed to list cache keys for namespace=%s: %s",
                namespace,
                e,
            )
            return []

    ###########################
    #### MESSAGE METHODS ######
    ###########################

    async def aput_messages(
        self,
        config: dict[str, Any],
        messages: list[Message],
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """
        Store messages in PostgreSQL.

        Args:
            config (dict): Configuration dictionary.
            messages (list[Message]): List of messages to store.
            metadata (dict, optional): Additional metadata.

        Returns:
            Any: None

        Raises:
            Exception: If storing fails.
        """
        # Ensure schema is initialized before accessing tables
        thread_id, user_id = self._validate_config(config)

        if not messages:
            logger.debug("No messages to store for thread_id=%s", thread_id)
            return

        logger.debug("Storing %d messages for thread_id=%s", len(messages), thread_id)

        try:
            # Ensure thread exists
            await self._ensure_thread_exists(thread_id, user_id, config)

            # Store messages in batch with retry logic
            async def _store_messages():
                async with (await self._get_pg_pool()).acquire() as conn, conn.transaction():
                    for message in messages:
                        # content_value = message.content
                        # if not isinstance(content_value, str):
                        #     try:
                        #         content_value = json.dumps(content_value)
                        #     except Exception:
                        #         content_value = str(content_value)
                        await conn.execute(
                            f"""
                                INSERT INTO {self._get_table_name("messages")} (
                                    message_id, thread_id, role, content, tool_calls,
                                    tool_call_id, reasoning, total_tokens, usages, meta
                                )
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                                ON CONFLICT (message_id) DO UPDATE SET
                                    content = EXCLUDED.content,
                                    reasoning = EXCLUDED.reasoning,
                                    usages = EXCLUDED.usages,
                                    updated_at = NOW()
                                """,  # noqa: S608
                            message.message_id,
                            thread_id,
                            message.role,
                            json.dumps(
                                [block.model_dump(mode="json") for block in message.content]
                            ),
                            json.dumps(message.tools_calls) if message.tools_calls else None,
                            getattr(message, "tool_call_id", None),
                            message.reasoning,
                            message.usages.total_tokens if message.usages else 0,
                            json.dumps(message.usages.model_dump()) if message.usages else None,
                            json.dumps({**(metadata or {}), **(message.metadata or {})}),
                        )

            await self._retry_on_connection_error(_store_messages, max_retries=3)
            logger.debug("Stored %d messages for thread_id=%s", len(messages), thread_id)

        except Exception as e:
            logger.error("Failed to store messages for thread_id=%s: %s", thread_id, e)
            raise

    async def aget_message(self, config: dict[str, Any], message_id: str | int) -> Message:
        """
        Retrieve a single message by ID.

        Args:
            config (dict): Configuration dictionary.
            message_id (str|int): Message identifier.

        Returns:
            Message: Retrieved message object.

        Raises:
            Exception: If retrieval fails.
        """
        # Ensure schema is initialized before accessing tables
        thread_id = config.get("thread_id")

        logger.debug("Retrieving message_id=%s for thread_id=%s", message_id, thread_id)

        try:

            async def _get_message():
                async with (await self._get_pg_pool()).acquire() as conn:
                    query = f"""
                        SELECT message_id, thread_id, role, content, tool_calls,
                               tool_call_id, reasoning, created_at, total_tokens,
                               usages, meta
                        FROM {self._get_table_name("messages")}
                        WHERE message_id = $1
                    """  # noqa: S608
                    if thread_id:
                        query += " AND thread_id = $2"
                        return await conn.fetchrow(query, message_id, thread_id)
                    return await conn.fetchrow(query, message_id)

            row = await self._retry_on_connection_error(_get_message, max_retries=3)

            if not row:
                raise ValueError(f"Message not found: {message_id}")

            return self._row_to_message(row)

        except Exception as e:
            logger.error("Failed to retrieve message_id=%s: %s", message_id, e)
            raise

    async def alist_messages(
        self,
        config: dict[str, Any],
        search: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[Message]:
        """
        List messages for a thread with optional search and pagination.

        Args:
            config (dict): Configuration dictionary.
            search (str, optional): Search string.
            offset (int, optional): Offset for pagination.
            limit (int, optional): Limit for pagination.

        Returns:
            list[Message]: List of message objects.

        Raises:
            Exception: If listing fails.
        """
        # Ensure schema is initialized before accessing tables
        thread_id = config.get("thread_id")

        if not thread_id:
            raise ValueError("thread_id must be provided in config")

        logger.debug("Listing messages for thread_id=%s", thread_id)

        try:

            async def _list_messages():
                async with (await self._get_pg_pool()).acquire() as conn:
                    # Build query with optional search
                    query = f"""
                        SELECT message_id, thread_id, role, content, tool_calls,
                               tool_call_id, reasoning, created_at, total_tokens,
                               usages, meta
                        FROM {self._get_table_name("messages")}
                        WHERE thread_id = $1
                    """  # noqa: S608
                    params = [thread_id]
                    param_count = 1

                    if search:
                        param_count += 1
                        query += f" AND content ILIKE ${param_count}"
                        params.append(f"%{search}%")

                    query += " ORDER BY created_at ASC"

                    if limit:
                        param_count += 1
                        query += f" LIMIT ${param_count}"
                        params.append(limit)

                    if offset:
                        param_count += 1
                        query += f" OFFSET ${param_count}"
                        params.append(offset)

                    return await conn.fetch(query, *params)

            rows = await self._retry_on_connection_error(_list_messages, max_retries=3)
            if not rows:
                rows = []
            messages = [self._row_to_message(row) for row in rows]

            logger.debug("Found %d messages for thread_id=%s", len(messages), thread_id)
            return messages

        except Exception as e:
            logger.error("Failed to list messages for thread_id=%s: %s", thread_id, e)
            raise

    async def adelete_message(
        self,
        config: dict[str, Any],
        message_id: str | int,
    ) -> Any | None:
        """
        Delete a message by ID.

        Args:
            config (dict): Configuration dictionary.
            message_id (str|int): Message identifier.

        Returns:
            Any | None: None

        Raises:
            Exception: If deletion fails.
        """
        # Ensure schema is initialized before accessing tables
        thread_id = config.get("thread_id")

        logger.debug("Deleting message_id=%s for thread_id=%s", message_id, thread_id)

        try:

            async def _delete_message():
                async with (await self._get_pg_pool()).acquire() as conn:
                    if thread_id:
                        await conn.execute(
                            f"DELETE FROM {self._get_table_name('messages')} "  # noqa: S608
                            f"WHERE message_id = $1 AND thread_id = $2",
                            message_id,
                            thread_id,
                        )
                    else:
                        await conn.execute(
                            f"DELETE FROM {self._get_table_name('messages')} WHERE message_id = $1",  # noqa: S608
                            message_id,
                        )

            await self._retry_on_connection_error(_delete_message, max_retries=3)
            logger.debug("Deleted message_id=%s", message_id)
            return None

        except Exception as e:
            logger.error("Failed to delete message_id=%s: %s", message_id, e)
            raise

    def _row_to_message(self, row) -> Message:  # noqa: PLR0912, PLR0915
        """
        Convert database row to Message object with robust JSON handling.

        Args:
            row: Database row.

        Returns:
            Message: Message object.
        """
        from alcyoneus.core.state.message import TokenUsages

        # Handle usages JSONB
        usages = None
        usages_raw = row["usages"]
        if usages_raw:
            try:
                usages_dict = (
                    json.loads(usages_raw)
                    if isinstance(usages_raw, str | bytes | bytearray)
                    else usages_raw
                )
                usages = TokenUsages(**usages_dict)
            except Exception:
                usages = None

        # Handle tool_calls JSONB
        tool_calls_raw = row["tool_calls"]
        if tool_calls_raw:
            try:
                tool_calls = (
                    json.loads(tool_calls_raw)
                    if isinstance(tool_calls_raw, str | bytes | bytearray)
                    else tool_calls_raw
                )
            except Exception:
                tool_calls = None
        else:
            tool_calls = None

        # Handle meta JSONB
        meta_raw = row["meta"]
        if meta_raw:
            try:
                metadata = (
                    json.loads(meta_raw)
                    if isinstance(meta_raw, str | bytes | bytearray)
                    else meta_raw
                )
            except Exception:
                metadata = {}
        else:
            metadata = {}

        # Handle content TEXT/JSONB -> list of blocks
        content_raw = row["content"]
        content_value: list[Any] = []
        if content_raw is None:
            content_value = []
        elif isinstance(content_raw, bytes | bytearray):
            try:
                parsed = json.loads(content_raw.decode())
                if isinstance(parsed, list):
                    content_value = parsed
                elif isinstance(parsed, dict):
                    content_value = [parsed]
                else:
                    content_value = [{"type": "text", "text": str(parsed), "annotations": []}]
            except Exception:
                content_value = [
                    {"type": "text", "text": content_raw.decode(errors="ignore"), "annotations": []}
                ]
        elif isinstance(content_raw, str):
            # Try JSON parse first
            try:
                parsed = json.loads(content_raw)
                if isinstance(parsed, list):
                    content_value = parsed
                elif isinstance(parsed, dict):
                    content_value = [parsed]
                else:
                    content_value = [{"type": "text", "text": content_raw, "annotations": []}]
            except Exception:
                content_value = [{"type": "text", "text": content_raw, "annotations": []}]
        elif isinstance(content_raw, list):
            content_value = content_raw
        elif isinstance(content_raw, dict):
            content_value = [content_raw]
        else:
            content_value = [{"type": "text", "text": str(content_raw), "annotations": []}]

        return Message(
            message_id=row["message_id"],
            role=row["role"],
            content=content_value,
            tools_calls=tool_calls,
            reasoning=row["reasoning"],
            timestamp=row["created_at"].timestamp() if row["created_at"] else 0,
            metadata=metadata,
            usages=usages,
        )

    ###########################
    #### THREAD METHODS #######
    ###########################

    async def aput_thread(
        self,
        config: dict[str, Any],
        thread_info: ThreadInfo,
    ) -> Any | None:
        """
        Create or update thread information.

        Args:
            config (dict): Configuration dictionary.
            thread_info (ThreadInfo): Thread information object.

        Returns:
            bool: True if thread was created (inserted).
                  False if thread already existed and was updated.

        Raises:
            Exception: If storing fails.
        """
        # Ensure schema is initialized before accessing tables
        thread_id, user_id = self._validate_config(config)

        logger.debug("Storing thread info for thread_id=%s, user_id=%s", thread_id, user_id)

        try:
            thread_name = thread_info.thread_name
            meta = thread_info.metadata or {}
            user_id = thread_info.user_id or user_id
            meta.update(
                {
                    "run_id": thread_info.run_id,
                }
            )

            async def _put_thread():
                async with (await self._get_pg_pool()).acquire() as conn:
                    # Try to insert; if inserted, RETURNING will return the row
                    row = await conn.fetchrow(
                        f"""
                        INSERT INTO {self._get_table_name("threads")}
                            (thread_id, thread_name, user_id, meta)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (thread_id) DO NOTHING
                        RETURNING thread_id
                        """,  # noqa: S608
                        thread_id,
                        thread_name,
                        user_id,
                        json.dumps(meta),
                    )

                    if row:
                        # Insert succeeded
                        return True

                    # Insert did nothing (conflict) -> update existing row
                    # Only set thread_name when a non-None value is provided
                    if thread_name is None:
                        await conn.execute(
                            f"""
                            UPDATE {self._get_table_name("threads")}
                            SET meta = $1, updated_at = NOW()
                            WHERE thread_id = $2
                            """,  # noqa: S608
                            json.dumps(meta),
                            thread_id,
                        )
                    else:
                        await conn.execute(
                            f"""
                            UPDATE {self._get_table_name("threads")}
                            SET thread_name = $1, meta = $2, updated_at = NOW()
                            WHERE thread_id = $3
                            """,  # noqa: S608
                            thread_name,
                            json.dumps(meta),
                            thread_id,
                        )

                    return False

            created = await self._retry_on_connection_error(_put_thread, max_retries=3)
            logger.debug("Thread info stored for thread_id=%s (created=%s)", thread_id, created)
            return bool(created)

        except Exception as e:
            logger.error("Failed to store thread info for thread_id=%s: %s", thread_id, e)
            raise e

    async def aget_thread(
        self,
        config: dict[str, Any],
    ) -> ThreadInfo | None:
        """
        Get thread information.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            ThreadInfo | None: Thread information object or None.

        Raises:
            Exception: If retrieval fails.
        """
        # Ensure schema is initialized before accessing tables
        thread_id, user_id = self._validate_config(config)

        logger.debug("Retrieving thread info for thread_id=%s, user_id=%s", thread_id, user_id)

        try:

            async def _get_thread():
                async with (await self._get_pg_pool()).acquire() as conn:
                    return await conn.fetchrow(
                        f"""
                        SELECT thread_id, thread_name, user_id, created_at, updated_at, meta
                        FROM {self._get_table_name("threads")}
                        WHERE thread_id = $1 AND user_id = $2
                        """,  # noqa: S608
                        thread_id,
                        user_id,
                    )

            row = await self._retry_on_connection_error(_get_thread, max_retries=3)

            if row:
                meta_dict = {}
                if row["meta"]:
                    meta_dict = (
                        json.loads(row["meta"]) if isinstance(row["meta"], str) else row["meta"]
                    )
                return ThreadInfo(
                    thread_id=thread_id,
                    thread_name=row["thread_name"] if row else None,
                    user_id=user_id,
                    metadata=meta_dict,
                    run_id=meta_dict.get("run_id"),
                    updated_at=row["updated_at"] if row else None,
                )

            logger.debug("Thread not found for thread_id=%s, user_id=%s", thread_id, user_id)
            return None

        except Exception as e:
            logger.error("Failed to retrieve thread info for thread_id=%s: %s", thread_id, e)
            raise e

    async def alist_threads(
        self,
        config: dict[str, Any],
        search: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[ThreadInfo]:
        """
        List threads for a user with optional search and pagination.

        Args:
            config (dict): Configuration dictionary.
            search (str, optional): Search string.
            offset (int, optional): Offset for pagination.
            limit (int, optional): Limit for pagination.

        Returns:
            list[ThreadInfo]: List of thread information objects.

        Raises:
            Exception: If listing fails.
        """
        # Ensure schema is initialized before accessing tables
        user_id = config.get("user_id")
        user_id = user_id or "test-user"

        if not user_id:
            raise ValueError("user_id must be provided in config")

        logger.debug("Listing threads for user_id=%s", user_id)

        try:

            async def _list_threads():
                async with (await self._get_pg_pool()).acquire() as conn:
                    # Build query with optional search
                    query = f"""
                        SELECT thread_id, thread_name, user_id, created_at, updated_at, meta
                        FROM {self._get_table_name("threads")}
                        WHERE user_id = $1
                    """  # noqa: S608
                    params = [user_id]
                    param_count = 1

                    if search:
                        param_count += 1
                        query += f" AND thread_name ILIKE ${param_count}"
                        params.append(f"%{search}%")

                    query += " ORDER BY updated_at DESC"

                    if limit:
                        param_count += 1
                        query += f" LIMIT ${param_count}"
                        params.append(limit)

                    if offset:
                        param_count += 1
                        query += f" OFFSET ${param_count}"
                        params.append(offset)

                    return await conn.fetch(query, *params)

            rows = await self._retry_on_connection_error(_list_threads, max_retries=3)
            if not rows:
                rows = []

            threads = []
            for row in rows:
                meta_dict = {}
                if row["meta"]:
                    meta_dict = (
                        json.loads(row["meta"]) if isinstance(row["meta"], str) else row["meta"]
                    )
                threads.append(
                    ThreadInfo(
                        thread_id=row["thread_id"],
                        thread_name=row["thread_name"],
                        user_id=row["user_id"],
                        metadata=meta_dict,
                        run_id=meta_dict.get("run_id"),
                        updated_at=row["updated_at"],
                    )
                )
            logger.debug("Found %d threads for user_id=%s", len(threads), user_id)
            return threads

        except Exception as e:
            logger.error("Failed to list threads for user_id=%s: %s", user_id, e)
            raise

    async def aclean_thread(self, config: dict[str, Any]) -> Any | None:
        """
        Clean/delete a thread and all associated data.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            Any | None: None

        Raises:
            Exception: If cleaning fails.
        """
        # Ensure schema is initialized before accessing tables
        thread_id, user_id = self._validate_config(config)

        logger.debug("Cleaning thread thread_id=%s, user_id=%s", thread_id, user_id)

        try:
            # Delete thread (cascade will handle messages and states) with retry logic
            async def _clean_thread():
                async with (await self._get_pg_pool()).acquire() as conn:
                    await conn.execute(
                        f"DELETE FROM {self._get_table_name('threads')} "  # noqa: S608
                        f"WHERE thread_id = $1 AND user_id = $2",
                        thread_id,
                        user_id,
                    )

            await self._retry_on_connection_error(_clean_thread, max_retries=3)

            # Clean from Redis cache
            cache_key = self._get_thread_key(thread_id, user_id)
            await self.redis.delete(cache_key)

            logger.debug("Thread cleaned: thread_id=%s, user_id=%s", thread_id, user_id)

        except Exception as e:
            logger.error("Failed to clean thread thread_id=%s: %s", thread_id, e)
            raise

    ###########################
    #### RESOURCE CLEANUP #####
    ###########################

    async def arelease(self) -> Any | None:
        """
        Clean up connections and resources.

        Returns:
            Any | None: None
        """
        logger.info("Releasing PgCheckpointer resources")

        if not self.release_resources:
            logger.info("No resources to release")
            return

        errors = []

        # Close Redis connection
        try:
            if hasattr(self.redis, "aclose"):
                await self.redis.aclose()
            elif hasattr(self.redis, "close"):
                await self.redis.close()
            logger.debug("Redis connection closed")
        except Exception as e:
            logger.error("Error closing Redis connection: %s", e)
            errors.append(f"Redis: {e}")

        # Close PostgreSQL pool
        try:
            if self._pg_pool and not self._pg_pool.is_closing():
                await self._pg_pool.close()
            logger.debug("PostgreSQL pool closed")
        except Exception as e:
            logger.error("Error closing PostgreSQL pool: %s", e)
            errors.append(f"PostgreSQL: {e}")

        if errors:
            error_msg = f"Errors during resource cleanup: {'; '.join(errors)}"
            logger.warning(error_msg)
            # Don't raise - cleanup should be best effort
        else:
            logger.info("All resources released successfully")
