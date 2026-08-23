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

"""Unit test suite for the 4 Ergonomic Enhancements added to Alcyoneus OS."""

import asyncio
import unittest

from alcyoneus import (
    InjectedState,
    InjectedStore,
    StateGraph,
)
from alcyoneus.core.state.message import Message
from alcyoneus.utils.schema import function_schema


class TestErgonomicEnhancements(unittest.TestCase):
    """Test suite covering InjectedState schema stripping, get_state_history, stream_mode, and heartbeat."""

    def test_injected_state_schema_stripping(self):
        def sample_tool(query: str, state: InjectedState, store: InjectedStore) -> str:
            """Sample search tool."""
            return f"Results for {query}"

        schema = function_schema(sample_tool)
        properties = schema["parameters"]["properties"]
        required = schema["parameters"]["required"]

        # 'query' should be in the schema
        self.assertIn("query", properties)
        self.assertIn("query", required)

        # 'state' and 'store' MUST be stripped from the LLM JSON schema
        self.assertNotIn("state", properties)
        self.assertNotIn("store", properties)
        self.assertNotIn("state", required)
        self.assertNotIn("store", required)

    def test_get_state_history_api(self):
        def node_a(state, config):
            return {"messages": [Message.text_message("Step 1")]}

        builder = StateGraph()
        builder.add_node("node_a", node_a)
        builder.set_entry_point("node_a")
        compiled = builder.compile()

        # Run invocation
        compiled.invoke({"messages": [Message.text_message("Start")]}, config={"thread_id": "test_thread_1"})

        # Get state history via time-travel API
        history = compiled.get_state_history("test_thread_1")
        self.assertIsInstance(history, list)
        self.assertGreaterEqual(len(history), 1)

    def test_stream_mode_filtering_and_heartbeat(self):
        async def _test():
            async def node_a(state, config):
                await asyncio.sleep(0.06)
                return {"messages": [Message.text_message("Streaming Output")]}

            builder = StateGraph()
            builder.add_node("node_a", node_a)
            builder.set_entry_point("node_a")
            compiled = builder.compile()

            chunks = []
            async for chunk in compiled.astream(
                {"messages": [Message.text_message("Hello")]},
                config={"thread_id": "test_stream_thread"},
                stream_mode=["messages", "updates"],
                heartbeat_interval=0.03,
            ):
                chunks.append(chunk)

            self.assertGreaterEqual(len(chunks), 1)

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
