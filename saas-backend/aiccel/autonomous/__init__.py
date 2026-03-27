# aiccel/autonomous/__init__.py
"""
Autonomous Agent Capabilities
==============================

Self-improving, goal-driven autonomous agents.

Features:
- Goal decomposition
- Self-reflection
- Memory and learning
- Plan execution
- Error recovery
"""

from .goal_agent import Goal, GoalAgent, GoalStatus
from .planner import Plan, Task, TaskPlanner
from .self_reflection import ReflectionMixin, SelfReflection


__all__ = [
    'Goal',
    'GoalAgent',
    'GoalStatus',
    'Plan',
    'ReflectionMixin',
    'SelfReflection',
    'Task',
    'TaskPlanner',
]
