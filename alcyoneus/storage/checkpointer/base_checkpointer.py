import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, TypeVar

from alcyoneus.core.state import AgentState, Message
from alcyoneus.utils import run_coroutine
from alcyoneus.utils.thread_info import ThreadInfo


logger = logging.getLogger("alcyoneus.checkpointer")

if TYPE_CHECKING:
    from alcyoneus.core.state import AgentState, Message


StateT = TypeVar("StateT", bound="AgentState")


class BaseCheckpointer[StateT: AgentState](ABC):
    """
    Abstract base class for checkpointing agent state, messages, and threads.

    This class defines the contract for all checkpointer implementations, supporting both
    async and sync methods.
    Subclasses should implement async methods for optimal performance.
    Sync methods are provided for compatibility.

    Usage:
        - Async-first design: subclasses should implement `async def` methods.
        - If a subclass provides only a sync `def`, it will be executed in a worker thread
            automatically using `asyncio.run`.
        - Callers always use the async APIs (`await cp.put_state(...)`, etc.).

    Type Args:
        StateT: Type of agent state (must inherit from AgentState).
    """

    ###########################
    #### SETUP ################
    ###########################
    def setup(self) -> Any:
        """
        Synchronous setup method for checkpointer.

        Returns:
            Any: Implementation-defined setup result.
        """
        return run_coroutine(self.asetup())

    @abstractmethod
    async def asetup(self) -> Any:
        """
        Asynchronous setup method for checkpointer.

        Returns:
            Any: Implementation-defined setup result.
        """
        raise NotImplementedError

    # -------------------------
    # State methods Async
    # -------------------------
    @abstractmethod
    async def aput_state(self, config: dict[str, Any], state: StateT) -> StateT:
        """
        Store agent state asynchronously.

        Args:
            config (dict): Configuration dictionary.
            state (StateT): State object to store.

        Returns:
            StateT: The stored state object.
        """
        raise NotImplementedError

    @abstractmethod
    async def aget_state(self, config: dict[str, Any]) -> StateT | None:
        """
        Retrieve agent state asynchronously.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            StateT | None: Retrieved state or None.
        """
        raise NotImplementedError

    @abstractmethod
    async def aclear_state(self, config: dict[str, Any]) -> Any:
        """
        Clear agent state asynchronously.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            Any: Implementation-defined result.
        """
        raise NotImplementedError

    @abstractmethod
    async def aput_state_cache(self, config: dict[str, Any], state: StateT) -> Any | None:
        """
        Store agent state in cache asynchronously.

        Args:
            config (dict): Configuration dictionary.
            state (StateT): State object to cache.

        Returns:
            Any | None: Implementation-defined result.
        """
        raise NotImplementedError

    @abstractmethod
    async def aget_state_cache(self, config: dict[str, Any]) -> StateT | None:
        """
        Retrieve agent state from cache asynchronously.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            StateT | None: Cached state or None.
        """
        raise NotImplementedError

    # -------------------------
    # State methods Sync
    # -------------------------
    def put_state(self, config: dict[str, Any], state: StateT) -> StateT:
        """
        Store agent state synchronously.

        Args:
            config (dict): Configuration dictionary.
            state (StateT): State object to store.

        Returns:
            StateT: The stored state object.
        """
        return run_coroutine(self.aput_state(config, state))

    def get_state(self, config: dict[str, Any]) -> StateT | None:
        """
        Retrieve agent state synchronously.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            StateT | None: Retrieved state or None.
        """
        return run_coroutine(self.aget_state(config))

    def clear_state(self, config: dict[str, Any]) -> Any:
        """
        Clear agent state synchronously.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            Any: Implementation-defined result.
        """
        return run_coroutine(self.aclear_state(config))

    def put_state_cache(self, config: dict[str, Any], state: StateT) -> Any | None:
        """
        Store agent state in cache synchronously.

        Args:
            config (dict): Configuration dictionary.
            state (StateT): State object to cache.

        Returns:
            Any | None: Implementation-defined result.
        """
        return run_coroutine(self.aput_state_cache(config, state))

    def get_state_cache(self, config: dict[str, Any]) -> StateT | None:
        """
        Retrieve agent state from cache synchronously.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            StateT | None: Cached state or None.
        """
        return run_coroutine(self.aget_state_cache(config))

    # -------------------------
    # Generic cache methods
    # -------------------------
    async def aput_cache_value(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> Any | None:
        """Store a small JSON-serializable cache value.

        This is intentionally optional so existing checkpointers keep working
        even if they do not offer a shared cache backend.
        """
        return None

    async def aget_cache_value(self, namespace: str, key: str) -> Any | None:
        """Retrieve a cached value previously stored via ``aput_cache_value``."""
        return None

    async def aclear_cache_value(self, namespace: str, key: str) -> Any | None:
        """Delete a previously cached value."""
        return None

    async def alist_cache_keys(
        self,
        namespace: str,
        prefix: str | None = None,
    ) -> list[str]:
        """List all cache keys for a namespace.

        This is intentionally optional — default returns an empty list.
        Subclasses should override if they support key enumeration.

        Args:
            namespace: Cache namespace (e.g. "media:signed-url").
            prefix: Optional prefix to filter keys.

        Returns:
            List of cache key strings.
        """
        return []

    def put_cache_value(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> Any | None:
        """Synchronously store a small cache value."""
        return run_coroutine(self.aput_cache_value(namespace, key, value, ttl_seconds))

    def get_cache_value(self, namespace: str, key: str) -> Any | None:
        """Synchronously retrieve a small cache value."""
        return run_coroutine(self.aget_cache_value(namespace, key))

    def clear_cache_value(self, namespace: str, key: str) -> Any | None:
        """Synchronously delete a small cache value."""
        return run_coroutine(self.aclear_cache_value(namespace, key))

    # -------------------------
    # Message methods async
    # -------------------------
    @abstractmethod
    async def aput_messages(
        self,
        config: dict[str, Any],
        messages: list[Message],
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """
        Store messages asynchronously.

        Args:
            config (dict): Configuration dictionary.
            messages (list[Message]): List of messages to store.
            metadata (dict, optional): Additional metadata.

        Returns:
            Any: Implementation-defined result.
        """
        raise NotImplementedError

    @abstractmethod
    async def aget_message(self, config: dict[str, Any], message_id: str | int) -> Message:
        """
        Retrieve a specific message asynchronously.

        Args:
            config (dict): Configuration dictionary.
            message_id (str|int): Message identifier.

        Returns:
            Message: Retrieved message object.
        """
        raise NotImplementedError

    @abstractmethod
    async def alist_messages(
        self,
        config: dict[str, Any],
        search: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[Message]:
        """
        List messages asynchronously with optional filtering.

        Args:
            config (dict): Configuration dictionary.
            search (str, optional): Search string.
            offset (int, optional): Offset for pagination.
            limit (int, optional): Limit for pagination.

        Returns:
            list[Message]: List of message objects.
        """
        raise NotImplementedError

    @abstractmethod
    async def adelete_message(self, config: dict[str, Any], message_id: str | int) -> Any | None:
        """
        Delete a specific message asynchronously.

        Args:
            config (dict): Configuration dictionary.
            message_id (str|int): Message identifier.

        Returns:
            Any | None: Implementation-defined result.
        """
        raise NotImplementedError

    # -------------------------
    # Message methods sync
    # -------------------------
    def put_messages(
        self,
        config: dict[str, Any],
        messages: list[Message],
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """
        Store messages synchronously.

        Args:
            config (dict): Configuration dictionary.
            messages (list[Message]): List of messages to store.
            metadata (dict, optional): Additional metadata.

        Returns:
            Any: Implementation-defined result.
        """
        return run_coroutine(self.aput_messages(config, messages, metadata))

    def get_message(self, config: dict[str, Any], message_id: str | int) -> Message:
        """
        Retrieve a specific message synchronously.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            Message: Retrieved message object.
        """
        return run_coroutine(self.aget_message(config, message_id))

    def list_messages(
        self,
        config: dict[str, Any],
        search: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[Message]:
        """
        List messages synchronously with optional filtering.

        Args:
            config (dict): Configuration dictionary.
            search (str, optional): Search string.
            offset (int, optional): Offset for pagination.
            limit (int, optional): Limit for pagination.

        Returns:
            list[Message]: List of message objects.
        """
        return run_coroutine(self.alist_messages(config, search, offset, limit))

    def delete_message(self, config: dict[str, Any], message_id: str | int) -> Any | None:
        """
        Delete a specific message synchronously.

        Args:
            config (dict): Configuration dictionary.
            message_id (str|int): Message identifier.

        Returns:
            Any | None: Implementation-defined result.
        """
        return run_coroutine(self.adelete_message(config, message_id))

    # -------------------------
    # Thread methods async
    # -------------------------
    @abstractmethod
    async def aput_thread(
        self,
        config: dict[str, Any],
        thread_info: ThreadInfo,
    ) -> Any | None:
        """
        Store thread info asynchronously.

        Args:
            config (dict): Configuration dictionary.
            thread_info (ThreadInfo): Thread information object.

        Returns:
            Any | None: Implementation-defined result.
        """
        raise NotImplementedError

    @abstractmethod
    async def aget_thread(
        self,
        config: dict[str, Any],
    ) -> ThreadInfo | None:
        """
        Retrieve thread info asynchronously.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            ThreadInfo | None: Thread information object or None.
        """
        raise NotImplementedError

    @abstractmethod
    async def alist_threads(
        self,
        config: dict[str, Any],
        search: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[ThreadInfo]:
        """
        List threads asynchronously with optional filtering.

        Args:
            config (dict): Configuration dictionary.
            search (str, optional): Search string.
            offset (int, optional): Offset for pagination.
            limit (int, optional): Limit for pagination.

        Returns:
            list[ThreadInfo]: List of thread information objects.
        """
        raise NotImplementedError

    @abstractmethod
    async def aclean_thread(self, config: dict[str, Any]) -> Any | None:
        """
        Clean/delete thread asynchronously.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            Any | None: Implementation-defined result.
        """
        raise NotImplementedError

    # -------------------------
    # Thread methods sync
    # -------------------------
    def put_thread(self, config: dict[str, Any], thread_info: ThreadInfo) -> Any | None:
        """
        Store thread info synchronously.

        Args:
            config (dict): Configuration dictionary.
            thread_info (ThreadInfo): Thread information object.

        Returns:
            Any | None: Implementation-defined result.
        """
        return run_coroutine(self.aput_thread(config, thread_info))

    def get_thread(self, config: dict[str, Any]) -> ThreadInfo | None:
        """
        Retrieve thread info synchronously.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            ThreadInfo | None: Thread information object or None.
        """
        return run_coroutine(self.aget_thread(config))

    def list_threads(
        self,
        config: dict[str, Any],
        search: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[ThreadInfo]:
        """
        List threads synchronously with optional filtering.

        Args:
            config (dict): Configuration dictionary.
            search (str, optional): Search string.
            offset (int, optional): Offset for pagination.
            limit (int, optional): Limit for pagination.

        Returns:
            list[ThreadInfo]: List of thread information objects.
        """
        return run_coroutine(self.alist_threads(config, search, offset, limit))

    def clean_thread(self, config: dict[str, Any]) -> Any | None:
        """
        Clean/delete thread synchronously.

        Args:
            config (dict): Configuration dictionary.

        Returns:
            Any | None: Implementation-defined result.
        """
        return run_coroutine(self.aclean_thread(config))

    # -------------------------
    # Lifecycle helpers: prune / delete_for_runs / copy_thread (async-first)
    # -------------------------
    async def aprune(self, strategy: str = "keep_latest", **kwargs: Any) -> Any | None:
        """Prune stale checkpoints.

        Default is a no-op; subclasses may override to implement strategies
        such as ``"keep_latest"`` or ``"delete_all"``.

        Args:
            strategy: Pruning strategy name.
            **kwargs: Strategy-specific options.

        Returns:
            Any | None: Implementation-defined result.
        """
        return None

    async def adelete_for_runs(
        self,
        config: dict[str, Any],
        run_ids: list[str] | str,
    ) -> Any | None:
        """Delete checkpoint history entries associated with specific run ids.

        Default is a no-op; subclasses that store per-run history should
        override to remove the given runs from the thread.

        Args:
            config: Configuration dictionary (must include thread_id).
            run_ids: A single run id or list of run ids to delete.

        Returns:
            Any | None: Implementation-defined result.
        """
        return None

    async def acopy_thread(
        self,
        config: dict[str, Any],
        source_thread_id: str,
        new_thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Copy all state/checkpoints from one thread into another.

        Default implementation copies the latest state via ``aput_state``.
        Subclasses may override for a full checkpoint-history copy.

        Args:
            config: Configuration dictionary.
            source_thread_id: Thread to copy from.
            new_thread_id: Destination thread id (auto-generated when None).

        Returns:
            dict: Config with the new thread_id.
        """
        from uuid import uuid4

        source_cfg = dict(config)
        source_cfg["thread_id"] = source_thread_id
        target_thread_id = new_thread_id or str(uuid4())
        target_cfg = dict(config)
        target_cfg["thread_id"] = target_thread_id

        state = await self.aget_state(source_cfg)
        if state is not None:
            await self.aput_state(target_cfg, state)
        return {"configurable": {"thread_id": target_thread_id}}

    # -------------------------
    # Sync wrappers for lifecycle helpers
    # -------------------------
    def prune(self, strategy: str = "keep_latest", **kwargs: Any) -> Any | None:
        """Synchronously prune stale checkpoints."""
        return run_coroutine(self.aprune(strategy, **kwargs))

    def delete_for_runs(self, config: dict[str, Any], run_ids: list[str] | str) -> Any | None:
        """Synchronously delete history entries for the given run ids."""
        return run_coroutine(self.adelete_for_runs(config, run_ids))

    def copy_thread(
        self,
        config: dict[str, Any],
        source_thread_id: str,
        new_thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Synchronously copy a thread's state into a new thread."""
        return run_coroutine(self.acopy_thread(config, source_thread_id, new_thread_id))

    # -------------------------
    # Clean Resources
    # -------------------------
    def release(self) -> Any | None:
        """
        Release resources synchronously.

        Returns:
            Any | None: Implementation-defined result.
        """
        return run_coroutine(self.arelease())

    @abstractmethod
    async def arelease(self) -> Any | None:
        """
        Release resources asynchronously.

        Returns:
            Any | None: Implementation-defined result.
        """
        raise NotImplementedError
