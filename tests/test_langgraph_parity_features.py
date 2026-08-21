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

"""Unit tests for the 4 LangGraph parity features in Alcyoneus OS."""

import os
import unittest
from dataclasses import dataclass

from alcyoneus import (
    Command,
    InMemoryCache,
    JsonSerde,
    PickleSerde,
    RedisCache,
    SQLiteCache,
    StateGraph,
    cache,
    entrypoint,
    set_global_cache,
    task,
)
from alcyoneus.core.state.message import Message


@dataclass
class SampleObj:
    x: int


class TestLangGraphParityFeatures(unittest.TestCase):
    """Test suite covering Command, @task/@entrypoint, @cache, and Serde protocols."""

    def test_command_dataclass(self):
        cmd = Command(goto="node_b", update={"user_id": "123"})
        self.assertEqual(cmd.goto, "node_b")
        self.assertEqual(cmd.update, {"user_id": "123"})

    def test_command_compiled_graph_routing(self):
        def node_a(state, config):
            return Command(goto="node_c", update={"messages": [Message.text_message("Jumped to C")]})

        def node_b(state, config):
            return [Message.text_message("In Node B")]

        def node_c(state, config):
            return [Message.text_message("In Node C")]

        builder = StateGraph()
        builder.add_node("node_a", node_a)
        builder.add_node("node_b", node_b)
        builder.add_node("node_c", node_c)
        builder.set_entry_point("node_a")

        builder.add_edge("node_a", "node_b")
        builder.add_edge("node_b", "node_c")
        compiled = builder.compile()
        res = compiled.invoke({"messages": [Message.text_message("Start")]})
        self.assertTrue(any("Jumped to C" in str(m) for m in res["messages"]))

    def test_functional_decorators(self):
        @task
        def add(a: int, b: int) -> int:
            return a + b

        @entrypoint
        def workflow(x: int, y: int) -> int:
            res_call = add(x, y)
            return res_call.result()

        output = workflow(10, 20)
        self.assertEqual(output, 30)

    def test_caching_subsystem(self):
        call_count = 0
        mem_cache = InMemoryCache()

        @cache(store=mem_cache)
        def expensive_fn(val: int) -> int:
            nonlocal call_count
            call_count += 1
            return val * 2

        self.assertEqual(expensive_fn(5), 10)
        self.assertEqual(call_count, 1)

        # Second call should be served from cache
        self.assertEqual(expensive_fn(5), 10)
        self.assertEqual(call_count, 1)

    def test_sqlite_and_redis_cache(self):
        db_path = "test_alcyoneus_cache.db"
        sqlite_c = SQLiteCache(db_path=db_path)
        sqlite_c.set("k1", {"data": 42})
        self.assertEqual(sqlite_c.get("k1"), {"data": 42})
        sqlite_c.clear()
        self.assertIsNone(sqlite_c.get("k1"))
        if os.path.exists(db_path):
            os.remove(db_path)

        redis_c = RedisCache()
        redis_c.set("rk1", "test_value")
        self.assertEqual(redis_c.get("rk1"), "test_value")
        redis_c.clear()

    def test_serde_json_and_pickle(self):
        json_serde = JsonSerde()
        data = {"name": "Alcyoneus OS", "version": 1}
        dumped = json_serde.dumps(data)
        loaded = json_serde.loads(dumped)
        self.assertEqual(loaded, data)

        secret = b"my_secure_secret_key_1234567890"
        pickle_serde = PickleSerde(secret_key=secret)

        obj = SampleObj(x=100)
        p_dumped = pickle_serde.dumps(obj)
        p_loaded = pickle_serde.loads(p_dumped)
        self.assertEqual(p_loaded.x, 100)

        # Invalid HMAC signature test
        tampered = bytearray(p_dumped)
        tampered[0] ^= 0xFF
        with self.assertRaises(ValueError):
            pickle_serde.loads(bytes(tampered))


if __name__ == "__main__":
    unittest.main()
