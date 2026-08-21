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

"""Functional decorators (@task and @entrypoint) for direct function-based workflows."""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
from collections.abc import Callable
from typing import Any, Generic, TypeVar


logger = logging.getLogger("alcyoneus.func")

T = TypeVar("T")


class TaskCall(Generic[T]):
    """Wrapper representing a task execution result."""

    def __init__(
        self, func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> None:
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self._result: Any = None
        self._executed: bool = False

    def result(self) -> T:
        """Synchronously execute the task function and return the result."""
        if not self._executed:
            if inspect.iscoroutinefunction(self.func):
                try:
                    loop = asyncio.get_running_loop()
                    self._result = loop.run_until_complete(self.func(*self.args, **self.kwargs))
                except RuntimeError:
                    self._result = asyncio.run(self.func(*self.args, **self.kwargs))
            else:
                self._result = self.func(*self.args, **self.kwargs)
            self._executed = True
        return self._result

    def __await__(self):
        """Allow awaiting the task directly in async contexts."""

        async def _async_exec():
            if not self._executed:
                if inspect.iscoroutinefunction(self.func):
                    self._result = await self.func(*self.args, **self.kwargs)
                else:
                    self._result = self.func(*self.args, **self.kwargs)
                self._executed = True
            return self._result

        return _async_exec().__await__()


def task(fn: Callable[..., T] | None = None) -> Any:
    """Decorator to mark a function as a Task within a functional workflow.

    Example:
        ```python
        @task
        def compute_sum(a: int, b: int) -> int:
            return a + b


        res = compute_sum(5, 10).result()
        ```
    """

    def decorator(func: Callable[..., T]) -> Callable[..., TaskCall[T]]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> TaskCall[T]:
            return TaskCall(func, args, kwargs)

        return wrapper

    if fn is not None:
        return decorator(fn)
    return decorator


class TaskWorkflow(Generic[T]):
    """Wrapper representing an entrypoint functional workflow."""

    def __init__(self, func: Callable[..., T]) -> None:
        self.func = func

    def invoke(self, *args: Any, **kwargs: Any) -> T:
        """Invoke the functional workflow synchronously."""
        if inspect.iscoroutinefunction(self.func):
            try:
                loop = asyncio.get_running_loop()
                return loop.run_until_complete(self.func(*args, **kwargs))
            except RuntimeError:
                return asyncio.run(self.func(*args, **kwargs))
        return self.func(*args, **kwargs)

    async def ainvoke(self, *args: Any, **kwargs: Any) -> T:
        """Invoke the functional workflow asynchronously."""
        if inspect.iscoroutinefunction(self.func):
            return await self.func(*args, **kwargs)
        return self.func(*args, **kwargs)

    def __call__(self, *args: Any, **kwargs: Any) -> T:
        return self.invoke(*args, **kwargs)


def entrypoint(fn: Callable[..., T] | None = None) -> Any:
    """Decorator to mark a main entrypoint function for a functional workflow.

    Example:
        ```python
        @entrypoint
        def main_workflow(query: str) -> str:
            t1 = research_task(query)
            return t1.result()


        result = main_workflow("AI Agents")
        ```
    """

    def decorator(func: Callable[..., T]) -> TaskWorkflow[T]:
        return TaskWorkflow(func)

    if fn is not None:
        return decorator(fn)
    return decorator


__all__ = [
    "TaskCall",
    "TaskWorkflow",
    "entrypoint",
    "task",
]
