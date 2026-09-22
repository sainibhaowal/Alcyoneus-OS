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

"""Graph State Transitions & Human-in-the-Loop Test Suite (Pillar 3).

Comprehensive verification for:
1. Complex cyclic graphs with condition edges & loop termination.
2. Dynamic prompt updates and state variable interpolation.
3. Human-in-the-loop: interrupt_before / interrupt_after and state resumption from checkpoint.
4. Stream Transformers: ToolCallTransformer pipeline events.
"""

from __future__ import annotations

import pytest

from alcyoneus.core.graph import (
    CompiledGraph,
    Edge,
    Node,
    StateGraph,
)
from alcyoneus.core.graph.stream_transformers import ToolCallTransformer
from alcyoneus.core.state import AgentState, Message
from alcyoneus.core.state.stream_chunks import StreamChunk, StreamEvent
from alcyoneus.storage.checkpointer import InMemoryCheckpointer
from alcyoneus.utils import END, ResponseGranularity, convert_messages


# Custom state for dynamic interpolation and cyclic counters
class WorkflowState(AgentState):
    counter: int = 0
    max_loops: int = 3
    user_name: str = "Anonymous"
    role: str = "Engineer"
    approved: bool = False
    audit_trail: list[str] = []


class TestGraphLifecycle:
    """Test suite covering advanced state transitions and HITL in compiled graphs."""

    @pytest.mark.asyncio
    async def test_complex_cyclic_graph_with_conditional_loop(self):
        """Verify cyclic graph iterates until condition is met and safely terminates."""
        graph = StateGraph[WorkflowState](WorkflowState())

        def increment_node(state: WorkflowState) -> WorkflowState:
            state.counter += 1
            state.audit_trail.append(f"cycle_{state.counter}")
            return state

        def finalize_node(state: WorkflowState) -> WorkflowState:
            state.audit_trail.append("finalized")
            return state

        def should_continue(state: WorkflowState) -> str:
            if state.counter < state.max_loops:
                return "increment"
            return "finalize"

        graph.add_node("increment", increment_node)
        graph.add_node("finalize", finalize_node)
        graph.set_entry_point("increment")

        graph.add_conditional_edges(
            "increment",
            should_continue,
            {"increment": "increment", "finalize": "finalize"},
        )
        graph.add_edge("finalize", END)

        compiled = graph.compile()
        messages = [Message.text_message("Start cyclic workflow", "user")]

        result = await compiled.ainvoke(
            {"messages": messages},
            response_granularity=ResponseGranularity.FULL,
        )
        assert isinstance(result, dict)
        final_state = result["state"]
        assert final_state.counter == 3
        assert "finalized" in final_state.audit_trail
        assert final_state.audit_trail == ["cycle_1", "cycle_2", "cycle_3", "finalized"]

    @pytest.mark.asyncio
    async def test_dynamic_prompt_interpolation(self):
        """Verify state variables are dynamically interpolated into system prompts."""
        state = WorkflowState(user_name="Alice", role="Security Architect")
        system_prompts = [
            {
                "role": "system",
                "content": "Welcome {user_name}! You are configured as {role}.",
            }
        ]

        converted = convert_messages(system_prompts=system_prompts, state=state)
        assert len(converted) >= 1
        assert converted[0]["content"] == "Welcome Alice! You are configured as Security Architect."

    @pytest.mark.asyncio
    async def test_interrupt_before_and_checkpoint_resumption(self):
        """Verify human-in-the-loop: graph pauses before specified node and can be resumed with updated state."""
        checkpointer = InMemoryCheckpointer()
        graph = StateGraph[WorkflowState](WorkflowState())

        def step_1(state: WorkflowState) -> WorkflowState:
            state.audit_trail.append("step_1_completed")
            return state

        def sensitive_step_2(state: WorkflowState) -> WorkflowState:
            state.audit_trail.append("sensitive_step_2_executed")
            state.approved = True
            return state

        graph.add_node("step_1", step_1)
        graph.add_node("sensitive_step_2", sensitive_step_2)
        graph.set_entry_point("step_1")
        graph.add_edge("step_1", "sensitive_step_2")
        graph.add_edge("sensitive_step_2", END)

        # Interrupt BEFORE sensitive_step_2
        compiled = graph.compile(
            checkpointer=checkpointer,
            interrupt_before=["sensitive_step_2"],
        )

        thread_id = "hitl-thread-test-1"
        config = {"thread_id": thread_id, "user_id": "auditor"}
        messages = [Message.text_message("Run workflow", "user")]

        # Run first phase - should stop before sensitive_step_2
        await compiled.ainvoke({"messages": messages}, config=config)

        # Check saved state in checkpointer
        saved_state = await checkpointer.aget_state(config)
        assert saved_state is not None
        assert "step_1_completed" in saved_state.audit_trail
        assert "sensitive_step_2_executed" not in saved_state.audit_trail

        # Human review: update state before resuming
        await compiled.aupdate_state(config, {"user_name": "SupervisorApproved"})

        # Resume execution
        await compiled.ainvoke({"messages": []}, config=config)

        # Verify resumption completed the sensitive step
        resumed_state = await checkpointer.aget_state(config)
        assert resumed_state is not None
        assert "sensitive_step_2_executed" in resumed_state.audit_trail
        assert resumed_state.approved is True
        assert resumed_state.user_name == "SupervisorApproved"

    @pytest.mark.asyncio
    async def test_stream_transformer_pipeline(self):
        """Verify ToolCallTransformer receives and transforms streaming chunks."""
        transformer = ToolCallTransformer()
        await transformer.init({})

        # Simulate raw TOOL_EXECUTION start event
        start_chunk = StreamChunk(
            event=StreamEvent.TOOL_EXECUTION,
            data={
                "tool_name": "code_search",
                "tool_call_id": "call_123",
                "status": "start",
                "arguments": {"query": "def ainvoke"},
            },
        )
        transformed_start = await transformer.process(start_chunk)
        assert len(transformed_start) == 1
        assert transformed_start[0].event == StreamEvent.TOOL_CALL
        assert transformed_start[0].data["name"] == "code_search"
        assert transformed_start[0].data["args"] == {"query": "def ainvoke"}

        # Simulate progress event
        prog_chunk = StreamChunk(
            event=StreamEvent.TOOL_EXECUTION,
            data={
                "tool_name": "code_search",
                "tool_call_id": "call_123",
                "status": "progress",
                "progress": 50,
            },
        )
        transformed_prog = await transformer.process(prog_chunk)
        assert len(transformed_prog) == 1
        assert transformed_prog[0].event == StreamEvent.TOOL_PROGRESS
        assert transformed_prog[0].data["progress"] == 50

        # Simulate complete event
        comp_chunk = StreamChunk(
            event=StreamEvent.TOOL_EXECUTION,
            data={
                "tool_name": "code_search",
                "tool_call_id": "call_123",
                "status": "complete",
                "result": "Found 4 matches",
            },
        )
        transformed_comp = await transformer.process(comp_chunk)
        assert len(transformed_comp) == 1
        assert transformed_comp[0].event == StreamEvent.TOOL_RESULT
        assert transformed_comp[0].data["output"] == "Found 4 matches"
