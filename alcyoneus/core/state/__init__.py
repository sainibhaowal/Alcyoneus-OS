"""
State management for TAF agent graphs.

This package provides schemas and context managers for agent state, execution
tracking, and message context management. All core state classes are exported
for use in agent workflows and custom state extensions.
"""

from .agent_state import AgentState
from .base_context import BaseContextManager
from .channels import (
    OVERWRITE_SENTINEL,
    BinaryOperatorAggregate,
    ChannelPersistence,
    Context,
    CRDTChannelSync,
    DeltaChannel,
    LastValueAfterFinish,
    Overwrite,
    Topic,
    get_value,
    is_overwrite,
)
from .execution_state import ExecutionState, ExecutionStatus
from .managed_values import (
    IS_LAST_STEP,
    REMAINING_STEPS,
    IsLastStep,
    ManagedValue,
    RemainingSteps,
    WritableManagedValue,
    get_managed_value,
    is_managed_value,
)
from .message import (
    Message,
    TokenUsages,
)
from .message_block import (
    AnnotationBlock,
    AnnotationRef,
    AudioBlock,
    ContentBlock,
    DataBlock,
    DocumentBlock,
    ErrorBlock,
    ImageBlock,
    MediaRef,
    ReasoningBlock,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
    VideoBlock,
)
from .message_context_manager import MessageContextManager
from .reducers import (
    add_messages,
    append_items,
    remove_tool_messages,
    replace_messages,
    replace_value,
)
from .remove_message import (
    REMOVE_ALL_MESSAGES,
    RemoveMessage,
    is_remove_all_messages,
    is_remove_message,
    message_to_remove_id,
)
from .run_state import RunState
from .serde import JsonSerde, PickleSerde, SerializerProtocol
from .stream_chunks import StreamChunk, StreamEvent
from .stream_emitter import StreamEmitter
from .summary_context_manager import SummaryContextManager
from .tool_result import ToolResult


__all__ = [
    "IS_LAST_STEP",
    "OVERWRITE_SENTINEL",
    "REMAINING_STEPS",
    "REMOVE_ALL_MESSAGES",
    "AgentState",
    "AnnotationBlock",
    "AnnotationRef",
    "AudioBlock",
    "BaseContextManager",
    "BinaryOperatorAggregate",
    "CRDTChannelSync",
    "ChannelPersistence",
    "ContentBlock",
    "Context",
    "DataBlock",
    "DeltaChannel",
    "DocumentBlock",
    "ErrorBlock",
    "ExecutionState",
    "ExecutionStatus",
    "ImageBlock",
    "IsLastStep",
    "JsonSerde",
    "LastValueAfterFinish",
    "ManagedValue",
    "MediaRef",
    "Message",
    "MessageContextManager",
    "Overwrite",
    "PickleSerde",
    "ReasoningBlock",
    "RemainingSteps",
    "RemoveMessage",
    "RunState",
    "SerializerProtocol",
    "StreamChunk",
    "StreamEmitter",
    "StreamEvent",
    "SummaryContextManager",
    "TextBlock",
    "TokenUsages",
    "ToolCallBlock",
    "ToolResult",
    "ToolResultBlock",
    "Topic",
    "VideoBlock",
    "WritableManagedValue",
    "add_messages",
    "append_items",
    "get_managed_value",
    "get_value",
    "is_managed_value",
    "is_overwrite",
    "is_remove_all_messages",
    "is_remove_message",
    "message_to_remove_id",
    "remove_tool_messages",
    "replace_messages",
    "replace_value",
]
