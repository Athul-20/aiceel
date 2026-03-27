# aiccel/agent_slim.py
"""
Compatibility layer - SlimAgent is now the main Agent.
This module re-exports from agent.py for backwards compatibility.
"""

from .agent import Agent as SlimAgent
from .agent import AgentConfig, create_agent


# Re-export with both names
Agent = SlimAgent

__all__ = ['Agent', 'AgentConfig', 'SlimAgent', 'create_agent']
