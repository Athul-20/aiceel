# aiccel/agent/__init__.py
"""
Agent Package
=============

Clean, modular agent implementation with:
- Separated concerns (config, prompts, execution, orchestration)
- Type-safe interfaces
- Production-ready patterns
"""

from typing import Any

from .config import AgentConfig, AgentResponse, ExecutionContext, ExecutionMode, ToolCallResult
from .core import Agent
from .orchestrator import ExecutionOrchestrator
from .prompt_builder import PromptBuilder
from .tool_executor import AgentToolExecutor


def create_agent(provider: Any, **kwargs) -> Agent:
    """Factory to create an Agent with a provider and options."""
    return Agent(provider=provider, **kwargs)


__all__ = [
    # Core
    'Agent',
    'create_agent',
    # Configuration
    'AgentConfig',
    'AgentResponse',
    'AgentToolExecutor',
    'ExecutionContext',
    'ExecutionMode',
    'ExecutionOrchestrator',
    # Components
    'PromptBuilder',
    'ToolCallResult',
]
