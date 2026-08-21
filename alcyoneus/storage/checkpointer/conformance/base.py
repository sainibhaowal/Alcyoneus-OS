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
"""Base conformance test functions for checkpointers."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from alcyoneus.storage.checkpointer.conformance.capabilities import (
    Capability,
    CapabilityReport,
    CapabilityResult,
    DetectedCapabilities,
)


def checkpointer_test(
    name: str,
    *,
    skip_capabilities: list[Capability] | None = None,
    lifespan: Callable | None = None,
) -> Callable:
    """Decorator to register a checkpointer conformance test.

    Args:
        name: Name of the checkpointer.
        skip_capabilities: Capabilities to skip testing.
        lifespan: Optional async context manager for setup/teardown.

    Returns:
        Decorator function that registers the test.
    """

    def decorator(func: Callable) -> Callable:
        func._checkpointer_test_name = name
        func._checkpointer_test_skip = skip_capabilities or []
        func._checkpointer_test_lifespan = lifespan
        return func

    return decorator


async def validate_checkpointer(
    checkpointer: Any,
    name: str | None = None,
    skip_capabilities: list[Capability] | None = None,
    lifespan: Callable | None = None,
) -> CapabilityReport:
    """Validate a checkpointer against the conformance suite.

    Args:
        checkpointer: Checkpointer instance to validate.
        name: Optional name for the checkpointer.
        skip_capabilities: Capabilities to skip.
        lifespan: Optional async context manager for setup/teardown.

    Returns:
        CapabilityReport with test results.
    """
    checkpointer_name = name or type(checkpointer).__name__
    skip = skip_capabilities or []

    # Detect capabilities
    detected = DetectedCapabilities.from_instance(checkpointer)

    # Run setup
    if hasattr(checkpointer, "asetup"):
        await checkpointer.asetup()

    results = []

    # Test each detected capability
    for capability in detected.capabilities:
        if capability in skip:
            results.append(CapabilityResult(capability=capability, passed=True, error="skipped"))
            continue

        try:
            await _test_capability(checkpointer, capability)
            results.append(CapabilityResult(capability=capability, passed=True))
        except Exception as e:
            results.append(CapabilityResult(capability=capability, passed=False, error=str(e)))

    # Run lifespan if provided
    if lifespan:
        try:
            async with lifespan(checkpointer):
                pass
        except Exception as e:
            results.append(
                CapabilityResult(
                    capability=Capability.PUT, passed=False, error=f"Lifespan error: {e}"
                )
            )

    return CapabilityReport(
        checkpointer_name=checkpointer_name,
        results=results,
        detected_capabilities=detected,
    )


async def _test_capability(checkpointer: Any, capability: Capability) -> None:
    """Test a specific capability."""
    thread_id = str(uuid.uuid4())
    config = {"thread_id": thread_id}
    test_state = {"messages": [], "test": "data", "count": 1}

    if capability == Capability.PUT or capability == Capability.GET_TUPLE:
        await checkpointer.aput_state(config, test_state)
        result = await checkpointer.aget_state(config)
        assert result is not None, "State should exist after put"

    elif capability == Capability.LIST:
        await checkpointer.aput_state(config, test_state)
        results = await checkpointer.alist()
        assert isinstance(results, list), "List should return list"

    elif capability == Capability.DELETE_THREAD:
        await checkpointer.aput_state(config, test_state)
        await checkpointer.adelete_thread(config)
        result = await checkpointer.aget_state(config)
        assert result is None, "State should be deleted"

    elif capability == Capability.PRUNE:
        await checkpointer.aput_state(config, test_state)
        await checkpointer.aprune("keep_latest")
        # Prune should not raise

    elif capability == Capability.DELTA_CHANNEL_HISTORY:
        await checkpointer.aput_state(config, test_state)
        history = await checkpointer.aget_delta_channel_history(config)
        assert isinstance(history, list), "Delta history should return list"

    elif capability == Capability.MESSAGES:
        await checkpointer.aput_message(config, {"role": "user", "content": "test"})
        messages = await checkpointer.alist_messages(config)
        assert isinstance(messages, list), "Messages should return list"

    elif capability == Capability.THREADS:
        await checkpointer.aput_state(config, test_state)
        threads = await checkpointer.alist_threads()
        assert isinstance(threads, list), "Threads should return list"
        ids = [getattr(t, "thread_id", None) if not isinstance(t, str) else t for t in threads]
        assert thread_id in ids, "Thread should be listed"

    elif capability == Capability.DELETE_FOR_RUNS:
        await checkpointer.aput_state(config, test_state)
        run_id = str(uuid.uuid4())
        result = await checkpointer.adelete_for_runs(config, [run_id])
        # Should not raise; some implementations return a count.
        if result is not None:
            assert result >= 0, "Delete count should be non-negative"

    elif capability == Capability.COPY_THREAD:
        await checkpointer.aput_state(config, test_state)
        new_cfg = await checkpointer.acopy_thread(config, thread_id)
        assert "thread_id" in new_cfg.get("configurable", {}), (
            "Copy should return new thread config"
        )
        copied = await checkpointer.aget_state({"thread_id": new_cfg["configurable"]["thread_id"]})
        assert copied is not None, "Copied thread should have state"

    else:
        raise NotImplementedError(f"Capability {capability} not implemented")


async def run_conformance_suite(
    checkpointer_factory: Callable[[], Any],
    name: str,
    *,
    skip_capabilities: list[Capability] | None = None,
) -> CapabilityReport:
    """Run the full conformance suite on a checkpointer factory.

    Args:
        checkpointer_factory: Callable that returns a new checkpointer instance.
        name: Name of the checkpointer.
        skip_capabilities: Capabilities to skip.

    Returns:
        CapabilityReport with all results.
    """
    checkpointer = checkpointer_factory()
    try:
        return await validate_checkpointer(checkpointer, name, skip_capabilities)
    finally:
        if hasattr(checkpointer, "aclose"):
            await checkpointer.aclose()
