from __future__ import annotations


# """Optional A2A protocol bridge for Alcyoneus OS.

# This package exposes any alcyoneus ``CompiledGraph`` as a standard A2A
# agent using the official ``a2a-sdk`` package, and also provides client
# helpers to call remote A2A agents from within a graph.

# Install the extra:

#     pip install alcyoneus[a2a_sdk]

# Quick start - server:

#     from alcyoneus.runtime.protocols.a2a import (
#         AlcyoneusExecutor,
#         create_a2a_server,
#         make_agent_card,
#     )

# Quick start - client:

#     from alcyoneus.runtime.protocols.a2a import delegate_to_a2a_agent
# """

# from .client import create_a2a_client_node, delegate_to_a2a_agent
# from .executor import AlcyoneusExecutor
# from .server import build_a2a_app, create_a2a_server, make_agent_card


# __all__ = [
#     "AlcyoneusExecutor",
#     "build_a2a_app",
#     "create_a2a_client_node",
#     "create_a2a_server",
#     "delegate_to_a2a_agent",
#     "make_agent_card",
# ]
"""Optional A2A protocol bridge for Alcyoneus OS.

This package exposes any alcyoneus ``CompiledGraph`` as a standard A2A
agent using the official ``a2a-sdk`` package, and also provides client
helpers to call remote A2A agents from within a graph.

Install the extra:

    pip install alcyoneus[a2a_sdk]

Quick start - server:

    from alcyoneus.runtime.protocols.a2a import (
        AlcyoneusExecutor,
        create_a2a_server,
        make_agent_card,
    )

Quick start - client:

    from alcyoneus.runtime.protocols.a2a import delegate_to_a2a_agent
"""

from .client import create_a2a_client_node, delegate_to_a2a_agent
from .executor import AlcyoneusExecutor
from .server import build_a2a_app, create_a2a_server, make_agent_card


__all__ = [
    "AlcyoneusExecutor",
    "build_a2a_app",
    "create_a2a_client_node",
    "create_a2a_server",
    "delegate_to_a2a_agent",
    "make_agent_card",
]
