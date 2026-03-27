# aiccel/core/config.py
"""
Compatibility shim for core config types.

Canonical definitions live in aiccel.agent.config.
"""

from ..agent.config import AgentConfig, ExecutionContext, ExecutionMode

__all__ = [
    "AgentConfig",
    "ExecutionContext",
    "ExecutionMode",
]
