# aiccel/workflows/__init__.py
"""
Agent Workflows
================

DAG-based workflow orchestration for complex multi-agent tasks.
Inspired by Prefect, Airflow, and LangGraph.

Features:
- DAG-based task execution
- Conditional branching
- Parallel execution
- State management
- Checkpointing
"""

from .builder import WorkflowBuilder
from .executor import WorkflowExecutor
from .graph import Workflow, WorkflowEdge, WorkflowNode, WorkflowState
from .nodes import AgentNode, ConditionalNode, ParallelNode, RouterNode, ToolNode


__all__ = [
    # Nodes
    'AgentNode',
    'ConditionalNode',
    'ParallelNode',
    'RouterNode',
    'ToolNode',
    # Core
    'Workflow',
    # Building
    'WorkflowBuilder',
    'WorkflowEdge',
    # Execution
    'WorkflowExecutor',
    'WorkflowNode',
    'WorkflowState',
]
