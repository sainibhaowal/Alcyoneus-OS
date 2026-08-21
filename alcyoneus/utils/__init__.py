"""
Unified utility exports for Alcyoneus OS agent graphs.

This module re-exports core utility symbols for agent graph construction, message handling,
callback management, reducers, and constants. Import from this module for a stable, unified
surface of agent utilities.

Main Exports:
    - Message and content blocks (Message, TextBlock, ToolCallBlock, etc.)
    - Callback management (CallbackManager, register_before_invoke, etc.)
    - Validators (PromptInjectionValidator, MessageContentValidator, etc.)
    - Command and callable utilities (Command, call_sync_or_async)
    - Reducers (add_messages, replace_messages, append_items, replace_value)
    - Constants (START, END, ExecutionState, etc.)
    - Converter (convert_messages)
"""

from alcyoneus.core.state.reducers import (
    add_messages,
    append_items,
    replace_messages,
    replace_value,
)

from .background_task_manager import BackgroundTaskManager, TaskMetadata
from .callable_utils import call_sync_or_async, run_coroutine

# Export from callbacks.py
from .callbacks import (
    AfterInvokeCallback,
    BaseValidator,
    BeforeInvokeCallback,
    CallbackContext,
    CallbackManager,
    GraphLifecycleContext,
    GraphLifecycleHook,
    InvocationType,
    OnErrorCallback,
)
from .command import Command

# Export from constants.py
from .constants import END, START, ExecutionState, ResponseGranularity
from .converter import convert_messages
from .decorators import get_tool_metadata, has_tool_decorator, tool
from .id_generator import (
    AsyncIDGenerator,
    BaseIDGenerator,
    BigIntIDGenerator,
    DefaultIDGenerator,
    HexIDGenerator,
    IDType,
    IntIDGenerator,
    ShortIDGenerator,
    TimestampIDGenerator,
    UUIDGenerator,
)
from .interactive import (
    AskQuestionHook,
    Spinner,
    ToolConfirmationHook,
    async_input,
    run_interactive_loop,
)
from .logging import (
    SecretRedactionFilter,
    install_secret_redaction,
    logger,
    mask_secrets,
)
from .schema import ensure_strict_json_schema, function_schema
from .shutdown import (
    DelayedKeyboardInterrupt,
    GracefulShutdownManager,
    delayed_keyboard_interrupt,
    setup_exception_handler,
    shutdown_with_timeout,
)
from .thread_info import ThreadInfo

# Export validators
from .validators import (
    MessageContentValidator,
    PromptInjectionValidator,
    ValidationError,
    register_default_validators,
)


__all__ = [
    "END",
    "START",
    "AfterInvokeCallback",
    "AskQuestionHook",
    "AsyncIDGenerator",
    "BackgroundTaskManager",
    "BaseIDGenerator",
    "BaseValidator",
    "BeforeInvokeCallback",
    "BigIntIDGenerator",
    "CallbackContext",
    "CallbackManager",
    "Command",
    "DefaultIDGenerator",
    "DelayedKeyboardInterrupt",
    "ExecutionState",
    "GracefulShutdownManager",
    "GraphLifecycleContext",
    "GraphLifecycleHook",
    "HexIDGenerator",
    "IDType",
    "IntIDGenerator",
    "InvocationType",
    "MessageContentValidator",
    "OnErrorCallback",
    "PromptInjectionValidator",
    "ResponseGranularity",
    "SecretRedactionFilter",
    "ShortIDGenerator",
    "Spinner",
    "TaskMetadata",
    "ThreadInfo",
    "TimestampIDGenerator",
    "ToolConfirmationHook",
    "UUIDGenerator",
    "ValidationError",
    "add_messages",
    "append_items",
    "async_input",
    "call_sync_or_async",
    "convert_messages",
    "delayed_keyboard_interrupt",
    "ensure_strict_json_schema",
    "function_schema",
    "get_tool_metadata",
    "has_tool_decorator",
    "install_secret_redaction",
    "logger",
    "mask_secrets",
    "register_default_validators",
    "replace_messages",
    "replace_value",
    "run_coroutine",
    "run_interactive_loop",
    "setup_exception_handler",
    "shutdown_with_timeout",
    "tool",
]
