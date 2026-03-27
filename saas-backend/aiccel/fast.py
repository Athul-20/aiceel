# aiccel/fast.py
"""
Fast Import Module
===================

Unified lazy loading for fast startup. Use this instead of main package
when startup time is critical.

Usage:
    from aiccel.fast import Agent, GeminiProvider

    # Components loaded on first use, not on import
"""

import importlib
from typing import TYPE_CHECKING


# Version - must match __init__.py
__version__ = "3.5.0"

# Unified lazy loading mappings
_MAPPINGS = {
    # Core
    'Agent': ('aiccel.agent', 'Agent'),
    'SlimAgent': ('aiccel.agent', 'Agent'),
    'create_agent': ('aiccel.agent', 'create_agent'),

    # Providers
    'GeminiProvider': ('aiccel.providers', 'GeminiProvider'),
    'OpenAIProvider': ('aiccel.providers', 'OpenAIProvider'),
    'GroqProvider': ('aiccel.providers', 'GroqProvider'),
    'LLMProvider': ('aiccel.providers', 'LLMProvider'),

    # Tools
    'Tool': ('aiccel.tools', 'BaseTool'),
    'BaseTool': ('aiccel.tools', 'BaseTool'),
    'SearchTool': ('aiccel.tools', 'SearchTool'),
    'WeatherTool': ('aiccel.tools', 'WeatherTool'),
    'ToolRegistry': ('aiccel.tools', 'ToolRegistry'),

    # Manager
    'AgentManager': ('aiccel.manager', 'AgentManager'),

    # Memory
    'ConversationMemory': ('aiccel.conversation_memory', 'ConversationMemory'),

    # Workflows
    'Workflow': ('aiccel.workflows.graph', 'Workflow'),
    'WorkflowBuilder': ('aiccel.workflows.builder', 'WorkflowBuilder'),
    'WorkflowExecutor': ('aiccel.workflows.executor', 'WorkflowExecutor'),

    # Autonomous
    'GoalAgent': ('aiccel.autonomous.goal_agent', 'GoalAgent'),
    'Goal': ('aiccel.autonomous.goal_agent', 'Goal'),
    'TaskPlanner': ('aiccel.autonomous.planner', 'TaskPlanner'),

    # Logging (consolidated - use logging_config as source)
    'configure_logging': ('aiccel.logging_config', 'configure_logging'),
    'get_logger': ('aiccel.logging_config', 'get_logger'),
    'AgentLogger': ('aiccel.logging_config', 'AgentLogger'),
    'AILogger': ('aiccel.logging_config', 'AgentLogger'),

    # Privacy
    'EntityMasker': ('aiccel.privacy', 'EntityMasker'),
    'mask_text': ('aiccel.privacy', 'mask_text'),

    # Pipeline
    'MiddlewarePipeline': ('aiccel.pipeline.middleware', 'MiddlewarePipeline'),
    'create_default_pipeline': ('aiccel.pipeline.middleware', 'create_default_pipeline'),
    # Security
    'SecurityPolicy': ('aiccel.security', 'SecurityPolicy'),
    'RedactionPolicy': ('aiccel.security', 'RedactionPolicy'),
    'PromptInjectionGuard': ('aiccel.security', 'PromptInjectionGuard'),
    'SecurityAuditLogger': ('aiccel.security', 'SecurityAuditLogger'),
    'SecurityPipeline': ('aiccel.security', 'SecurityPipeline'),
    'create_security_pipeline': ('aiccel.security', 'create_security_pipeline'),

    # DI
    'Container': ('aiccel.di.container', 'Container'),
    'get_container': ('aiccel.di.container', 'get_container'),

    # Constants
    'Limits': ('aiccel.constants', 'Limits'),
    'Timeouts': ('aiccel.constants', 'Timeouts'),
    'Memory': ('aiccel.constants', 'Memory'),
}

# Cache for loaded modules
_CACHE = {}


def __getattr__(name: str):
    """Module-level lazy loading."""
    if name.startswith('_'):
        raise AttributeError(f"module 'aiccel.fast' has no attribute '{name}'")

    if name in _CACHE:
        return _CACHE[name]

    if name not in _MAPPINGS:
        raise ImportError(f"Cannot lazily import '{name}' from aiccel.fast")

    module_name, attr_name = _MAPPINGS[name]
    try:
        module = importlib.import_module(module_name)
        obj = getattr(module, attr_name)
        _CACHE[name] = obj
        return obj
    except (ImportError, AttributeError) as e:
        raise ImportError(f"Failed to import '{name}': {e}")


def __dir__():
    """List available lazy imports."""
    return [*list(_MAPPINGS.keys()), '__version__']


__all__ = [*list(_MAPPINGS.keys()), '__version__']


if TYPE_CHECKING:
    from .agent import Agent
    SlimAgent = Agent
