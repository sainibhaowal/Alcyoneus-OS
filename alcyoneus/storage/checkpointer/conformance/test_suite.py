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
"""Conformance test suite for checkpointer implementations."""

from __future__ import annotations

import pytest

from alcyoneus.storage.checkpointer import InMemoryCheckpointer, SqliteCheckpointer
from alcyoneus.storage.checkpointer.conformance import Capability, validate_checkpointer


@pytest.mark.asyncio
async def test_in_memory_checkpointer_conformance():
    """Test InMemoryCheckpointer conformance."""
    checkpointer = InMemoryCheckpointer()
    report = await validate_checkpointer(checkpointer, "InMemoryCheckpointer")
    assert report.passed_all_base, f"Base capabilities failed: {report.to_dict()}"


@pytest.mark.asyncio
async def test_sqlite_checkpointer_conformance():
    """Test SqliteCheckpointer conformance."""
    checkpointer = SqliteCheckpointer(":memory:")
    report = await validate_checkpointer(checkpointer, "SqliteCheckpointer")
    assert report.passed_all_base, f"Base capabilities failed: {report.to_dict()}"


@pytest.mark.asyncio
async def test_checkpointer_capabilities():
    """Test individual capability detection."""
    from alcyoneus.storage.checkpointer.conformance.capabilities import DetectedCapabilities

    mem_cp = InMemoryCheckpointer()
    detected = DetectedCapabilities.from_instance(mem_cp)
    assert Capability.PUT in detected.capabilities
    assert Capability.GET_TUPLE in detected.capabilities
    assert Capability.LIST in detected.capabilities
    assert Capability.DELETE_THREAD in detected.capabilities

    sqlite_cp = SqliteCheckpointer(":memory:")
    detected = DetectedCapabilities.from_instance(sqlite_cp)
    assert Capability.PUT in detected.capabilities
    assert Capability.GET_TUPLE in detected.capabilities
    assert Capability.MESSAGES in detected.capabilities
    assert Capability.THREADS in detected.capabilities


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
