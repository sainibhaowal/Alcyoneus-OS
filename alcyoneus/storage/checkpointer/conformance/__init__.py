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
"""Checkpointer conformance test suite for alcyoneus OS.

This module provides a standardized test suite for validating checkpointer
implementations against the BaseCheckpointer interface.
"""

from .base import checkpointer_test, validate_checkpointer
from .capabilities import BASE_CAPABILITIES, EXTENDED_CAPABILITIES, Capability


__all__ = [
    "BASE_CAPABILITIES",
    "EXTENDED_CAPABILITIES",
    "Capability",
    "checkpointer_test",
    "validate_checkpointer",
]
