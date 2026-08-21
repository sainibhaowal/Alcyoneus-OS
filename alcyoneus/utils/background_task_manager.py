"""
Background task manager for async operations in Alcyoneus OS.

This module provides BackgroundTaskManager, which tracks and manages
asyncio background tasks, ensuring proper cleanup and error logging.
"""

import asyncio
import logging
import time
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any

from alcyoneus.utils import metrics


logger = logging.getLogger("alcyoneus.utils")


@dataclass
class TaskMetadata:
    """Metadata for tracking background tasks."""

    name: str
    created_at: float
    timeout: float | None = None
    context: dict[str, Any] | None = None


class BackgroundTaskManager:
    """
    Manages asyncio background tasks for agent operations.

    Tracks created tasks, ensures proper cleanup, and logs errors from background execution.
    Enhanced with cancellation, timeouts, metadata tracking, and graceful shutdown.

    Supports async context manager for automatic cleanup:
        async with BackgroundTaskManager() as manager:
            manager.create_task(some_coroutine())
        # All tasks automatically cleaned up on exit
    """

    def __init__(self, default_shutdown_timeout: float = 30.0):
        """
        Initialize the BackgroundTaskManager.

        Args:
            default_shutdown_timeout: Default timeout for graceful shutdown in seconds.
        """
        self._tasks: set[asyncio.Task] = set()
        self._task_metadata: dict[asyncio.Task, TaskMetadata] = {}
        self._shutdown_timeout = default_shutdown_timeout
        self._is_shutdown = False
        self._shutdown_lock = asyncio.Lock()

    def create_task(
        self,
        coro: Coroutine,
        *,
        name: str = "background_task",
        timeout: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> asyncio.Task:
        """
        Create and track a background asyncio task.

        Args:
            coro (Coroutine): The coroutine to run in the background.
            name (str): Human-readable name for the task.
            timeout (Optional[float]): Timeout in seconds for the task.
            context (Optional[dict]): Additional context for logging.

        Returns:
            asyncio.Task: The created task.
        """
        metrics.counter("background_task_manager.tasks_created").inc()

        task = asyncio.create_task(coro, name=name)
        metadata = TaskMetadata(
            name=name, created_at=time.time(), timeout=timeout, context=context or {}
        )

        self._tasks.add(task)
        self._task_metadata[task] = metadata
        task.add_done_callback(self._task_done_callback)

        # Set up timeout if specified
        if timeout:
            self._setup_timeout(task, timeout)

        logger.debug(
            "Created background task: %s (timeout=%s)",
            name,
            timeout,
            extra={"task_context": context},
        )

        return task

    def _setup_timeout(self, task: asyncio.Task, timeout: float) -> None:
        """Set up timeout cancellation for a task."""

        async def timeout_canceller():
            try:
                await asyncio.sleep(timeout)
                if not task.done():
                    metadata = self._task_metadata.get(task)
                    task_name = metadata.name if metadata else "unknown"
                    logger.warning(
                        "Background task '%s' timed out after %s seconds", task_name, timeout
                    )
                    task.cancel()
                    metrics.counter("background_task_manager.tasks_timed_out").inc()
            except asyncio.CancelledError:
                pass  # Parent task was cancelled, this is expected

        # Create the timeout task but don't track it (avoid recursive tracking)
        timeout_task = asyncio.create_task(timeout_canceller())
        # Add a callback to clean up the timeout task reference
        timeout_task.add_done_callback(lambda t: None)

    def _task_done_callback(self, task: asyncio.Task) -> None:
        """
        Remove completed task and log exceptions if any.

        Args:
            task (asyncio.Task): The completed asyncio task.
        """
        metadata = self._task_metadata.pop(task, None)
        self._tasks.discard(task)

        task_name = metadata.name if metadata else "unknown"
        duration = time.time() - metadata.created_at if metadata else 0.0

        try:
            task.result()  # raises if task failed
            metrics.counter("background_task_manager.tasks_completed").inc()
            logger.debug(
                "Background task '%s' completed successfully (duration=%.2fs)",
                task_name,
                duration,
                extra={"task_context": metadata.context if metadata else {}},
            )
        except asyncio.CancelledError:
            metrics.counter("background_task_manager.tasks_cancelled").inc()
            logger.debug("Background task '%s' was cancelled", task_name)
        except Exception as e:
            metrics.counter("background_task_manager.tasks_failed").inc()
            error_msg = (
                f"Background task raised an exception - {task_name}: {e} (duration={duration:.2f}s)"
            )
            logger.error(
                error_msg,
                exc_info=e,
                extra={"task_context": metadata.context if metadata else {}},
            )

    async def cancel_all(self) -> None:
        """
        Cancel all tracked background tasks.

        Returns:
            None
        """
        if not self._tasks:
            return

        logger.info("Cancelling %d background tasks...", len(self._tasks))

        for task in self._tasks.copy():
            if not task.done():
                task.cancel()

        # Wait a short time for cancellations to process
        await asyncio.sleep(0.1)

    async def wait_for_all(
        self, timeout: float | None = None, return_exceptions: bool = False
    ) -> None:
        """
        Wait for all tracked background tasks to complete.

        Args:
            timeout (float | None): Maximum time to wait in seconds.
            return_exceptions (bool): If True, exceptions are returned as results instead of raised.

        Returns:
            None
        """
        if not self._tasks:
            return

        logger.info("Waiting for %d background tasks to finish...", len(self._tasks))

        try:
            if timeout:
                await asyncio.wait_for(
                    asyncio.gather(*self._tasks, return_exceptions=return_exceptions),
                    timeout=timeout,
                )
            else:
                await asyncio.gather(*self._tasks, return_exceptions=return_exceptions)
            logger.info("All background tasks finished.")
        except TimeoutError:
            logger.warning("Timeout waiting for background tasks, some may still be running")
            metrics.counter("background_task_manager.wait_timeout").inc()

    def get_task_count(self) -> int:
        """Get the number of active background tasks."""
        return len(self._tasks)

    def get_task_info(self) -> list[dict[str, Any]]:
        """Get information about all active tasks."""
        current_time = time.time()
        return [
            {
                "name": metadata.name,
                "age_seconds": current_time - metadata.created_at,
                "timeout": metadata.timeout,
                "context": metadata.context,
                "done": task.done(),
                "cancelled": task.cancelled() if task.done() else False,
            }
            for task, metadata in self._task_metadata.items()
        ]

    async def shutdown(self, timeout: float | None = None) -> dict[str, Any]:
        """
        Gracefully shutdown the task manager.

        This method cancels all tasks and waits for them to complete with a timeout.
        It ensures proper cleanup and prevents memory leaks.

        Args:
            timeout: Maximum time to wait for tasks to complete.
                     Uses default_shutdown_timeout if None.

        Returns:
            Dictionary with shutdown statistics.
        """
        async with self._shutdown_lock:
            if self._is_shutdown:
                logger.debug("BackgroundTaskManager already shut down")
                return {"status": "already_shutdown", "tasks_remaining": 0}

            self._is_shutdown = True
            shutdown_timeout = timeout if timeout is not None else self._shutdown_timeout
            start_time = time.time()

            initial_count = len(self._tasks)
            logger.info(
                "Initiating graceful shutdown of BackgroundTaskManager (%d tasks, timeout=%ss)",
                initial_count,
                shutdown_timeout,
            )

            # Cancel all tasks
            await self.cancel_all()

            # Wait for tasks to complete with timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(*list(self._tasks), return_exceptions=True),
                    timeout=shutdown_timeout,
                )
                completed_count = initial_count - len(self._tasks)
                duration = time.time() - start_time

                logger.info(
                    "BackgroundTaskManager shutdown completed: %d/%d tasks finished (%.2fs)",
                    completed_count,
                    initial_count,
                    duration,
                )
                metrics.counter("background_task_manager.shutdown_completed").inc()

                return {
                    "status": "completed",
                    "initial_tasks": initial_count,
                    "completed_tasks": completed_count,
                    "remaining_tasks": len(self._tasks),
                    "duration_seconds": duration,
                }
            except TimeoutError:
                remaining_count = len(self._tasks)
                duration = time.time() - start_time

                logger.warning(
                    "BackgroundTaskManager shutdown timed out: %d tasks still running after %.2fs",
                    remaining_count,
                    duration,
                )
                metrics.counter("background_task_manager.shutdown_timeout").inc()

                # Force cancel remaining tasks
                for task in list(self._tasks):
                    if not task.done():
                        task.cancel()

                return {
                    "status": "timeout",
                    "initial_tasks": initial_count,
                    "completed_tasks": initial_count - remaining_count,
                    "remaining_tasks": remaining_count,
                    "duration_seconds": duration,
                }

    async def __aenter__(self):
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager, ensuring cleanup."""
        await self.shutdown()
        return False  # Don't suppress exceptions
