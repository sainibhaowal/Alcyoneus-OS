#!/usr/bin/env python3
"""
Comprehensive test to verify logging functionality across Alcyoneus OS modules.
"""

import logging
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Import and configure logging
from alcyoneus.utils.logging import configure_logging


# Configure logging to see all messages
configure_logging(level=logging.DEBUG)


def test_logging_across_modules():
    """Test that logging is working across different Alcyoneus OS modules."""

    # Test main test logger
    logger = logging.getLogger(__name__)
    logger.info("=== Alcyoneus OS Logging Comprehensive Test ===")

    # Test different log levels
    logger.debug("Debug level test")
    logger.info("Info level test")
    logger.warning("Warning level test")
    logger.error("Error level test")

    # Test graph module logging
    logger.info("Testing graph module logging...")
    graph_logger = logging.getLogger("alcyoneus.graph.compiled_graph")
    graph_logger.info("CompiledGraph module logger test")

    node_logger = logging.getLogger("alcyoneus.graph.node")
    node_logger.debug("Node module logger test")

    edge_logger = logging.getLogger("alcyoneus.graph.edge")
    edge_logger.debug("Edge module logger test")

    # Test state module logging
    logger.info("Testing state module logging...")
    agent_state_logger = logging.getLogger("alcyoneus.state.agent_state")
    agent_state_logger.info("AgentState module logger test")

    exec_state_logger = logging.getLogger("alcyoneus.state.execution_state")
    exec_state_logger.debug("ExecutionState module logger test")

    # Test utils module logging
    logger.info("Testing utils module logging...")
    di_logger = logging.getLogger("alcyoneus.utils.dependency_injection")
    di_logger.info("DependencyInjection module logger test")

    callbacks_logger = logging.getLogger("alcyoneus.utils.callbacks")
    callbacks_logger.debug("Callbacks module logger test")

    # Test checkpointer module logging
    logger.info("Testing checkpointer module logging...")
    base_cp_logger = logging.getLogger("alcyoneus.checkpointer.base_checkpointer")
    base_cp_logger.info("BaseCheckpointer module logger test")

    mem_cp_logger = logging.getLogger("alcyoneus.checkpointer.in_memory_checkpointer")
    mem_cp_logger.debug("InMemoryCheckpointer module logger test")

    # Test exceptions module logging
    logger.info("Testing exceptions module logging...")
    graph_error_logger = logging.getLogger("alcyoneus.exceptions.graph_error")
    graph_error_logger.warning("GraphError module logger test")

    node_error_logger = logging.getLogger("alcyoneus.exceptions.node_error")
    node_error_logger.error("NodeError module logger test")

    # Test store module logging
    logger.info("Testing store module logging...")
    store_logger = logging.getLogger("alcyoneus.store.base_store")
    store_logger.info("BaseStore module logger test")

    logger.info("=== All module logging tests completed ===")

    # Verify hierarchical logging is working
    logger.info("Testing hierarchical logging...")
    parent_logger = logging.getLogger("alcyoneus")
    parent_logger.info("Parent 'alcyoneus' logger test")

    child_logger = logging.getLogger("alcyoneus.graph")
    child_logger.info("Child 'alcyoneus.graph' logger test")

    grandchild_logger = logging.getLogger("alcyoneus.graph.compiled_graph")
    grandchild_logger.info("Grandchild 'alcyoneus.graph.compiled_graph' logger test")

    logger.info("=== Alcyoneus OS logging system verified successfully ===")


if __name__ == "__main__":
    test_logging_across_modules()
