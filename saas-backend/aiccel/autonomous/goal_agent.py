# aiccel/autonomous/goal_agent.py
"""
Goal-Driven Autonomous Agent
=============================

Agent that pursues goals autonomously with self-correction.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from ..logging_config import get_logger


logger = get_logger("goal_agent")


class GoalStatus(Enum):
    """Status of a goal."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class Goal:
    """
    Represents a goal for the agent to achieve.
    """
    id: str
    description: str
    success_criteria: str
    priority: int = 1
    deadline: Optional[datetime] = None
    dependencies: list[str] = field(default_factory=list)
    status: GoalStatus = GoalStatus.PENDING
    result: Any = None
    attempts: int = 0
    max_attempts: int = 3
    subtasks: list['Goal'] = field(default_factory=list)

    def is_ready(self, completed_goals: set) -> bool:
        """Check if all dependencies are met."""
        return all(dep in completed_goals for dep in self.dependencies)

    def can_retry(self) -> bool:
        """Check if goal can be retried."""
        return self.attempts < self.max_attempts


class GoalAgent:
    """
    Autonomous agent that pursues goals with self-correction.

    Features:
    - Goal decomposition
    - Priority-based execution
    - Automatic retry with reflection
    - Success verification

    Usage:
        agent = GoalAgent(provider=...)

        # Add goals
        agent.add_goal(Goal(
            id="research",
            description="Research AI trends",
            success_criteria="Found at least 5 recent AI developments"
        ))

        # Run autonomously
        results = await agent.run_until_complete()
    """

    def __init__(
        self,
        provider,
        tools: Optional[list] = None,
        max_iterations: int = 50,
        reflection_enabled: bool = True,
        verbose: bool = True
    ):
        self.provider = provider
        self.tools = tools or []
        self.max_iterations = max_iterations
        self.reflection_enabled = reflection_enabled
        self.verbose = verbose

        self.goals: dict[str, Goal] = {}
        self.completed_goals: set = set()
        self.execution_log: list[dict] = []

        # Import here to avoid circular
        from ..agent import Agent

        self._agent = Agent(
            provider=provider,
            tools=tools,
            name="GoalAgent",
            instructions=self._get_instructions(),
            verbose=verbose
        )

    def _get_instructions(self) -> str:
        return """You are an autonomous AI agent that achieves goals systematically.

When given a goal:
1. Break it into smaller tasks if complex
2. Execute each task using available tools
3. Verify success against criteria
4. Reflect on failures and adjust approach
5. Report completion or blockers

Be thorough and persistent. If one approach fails, try alternatives."""

    def add_goal(self, goal: Goal) -> 'GoalAgent':
        """Add a goal to pursue."""
        self.goals[goal.id] = goal
        return self

    def add_goals(self, goals: list[Goal]) -> 'GoalAgent':
        """Add multiple goals."""
        for goal in goals:
            self.add_goal(goal)
        return self

    async def decompose_goal(self, goal: Goal) -> list[Goal]:
        """Use LLM to decompose complex goal into subtasks."""
        prompt = f"""Decompose this goal into smaller, actionable subtasks:

Goal: {goal.description}
Success Criteria: {goal.success_criteria}

Return a numbered list of subtasks, each with:
- Clear action to take
- Expected outcome

Keep subtasks atomic and achievable."""

        result = await self._agent.run_async(prompt)
        response = result.get("response", "")

        # Parse subtasks (simplified - could use structured output)
        subtasks = []
        lines = response.strip().split("\n")

        for i, line in enumerate(lines):
            if line.strip() and line[0].isdigit():
                subtasks.append(Goal(
                    id=f"{goal.id}_sub_{i}",
                    description=line.strip(),
                    success_criteria=f"Completed: {line.strip()}",
                    priority=goal.priority
                ))

        return subtasks

    async def execute_goal(self, goal: Goal) -> bool:
        """Execute a single goal."""
        goal.status = GoalStatus.IN_PROGRESS
        goal.attempts += 1

        logger.info(f"Executing goal: {goal.description} (attempt {goal.attempts})")

        # Build execution prompt
        prompt = f"""Execute this goal:

Description: {goal.description}
Success Criteria: {goal.success_criteria}

Use available tools as needed. Report your progress and final result."""

        try:
            result = await self._agent.run_async(prompt)
            response = result.get("response", "")

            # Verify success
            success = await self._verify_success(goal, response)

            if success:
                goal.status = GoalStatus.COMPLETED
                goal.result = response
                self.completed_goals.add(goal.id)
                logger.info(f"Goal completed: {goal.id}")
                return True
            elif goal.can_retry() and self.reflection_enabled:
                # Reflect and retry
                reflection = await self._reflect_failure(goal, response)
                logger.warning(f"Goal failed, reflecting: {reflection[:100]}")
                return False
            else:
                goal.status = GoalStatus.FAILED
                goal.result = response
                logger.error(f"Goal failed permanently: {goal.id}")
                return False

        except Exception as e:
            logger.error(f"Goal execution error: {e}")
            if goal.can_retry():
                return False
            goal.status = GoalStatus.FAILED
            return False

    async def _verify_success(self, goal: Goal, result: str) -> bool:
        """Verify if goal was successfully achieved."""
        prompt = f"""Evaluate if this goal was achieved:

Goal: {goal.description}
Success Criteria: {goal.success_criteria}

Result:
{result[:2000]}

Answer with only YES or NO, followed by brief explanation."""

        verification = await self._agent.run_async(prompt)
        response = verification.get("response", "").upper()

        return response.startswith("YES")

    async def _reflect_failure(self, goal: Goal, result: str) -> str:
        """Reflect on failure and suggest improvements."""
        prompt = f"""This goal execution failed:

Goal: {goal.description}
Success Criteria: {goal.success_criteria}
Attempts: {goal.attempts}/{goal.max_attempts}

Result:
{result[:1000]}

Analyze what went wrong and suggest a different approach for the next attempt."""

        reflection = await self._agent.run_async(prompt)
        return reflection.get("response", "")

    async def run_until_complete(
        self,
        timeout: float = 300.0
    ) -> dict[str, Any]:
        """
        Run autonomously until all goals complete or timeout.

        Returns:
            Dict with completed_goals, failed_goals, results
        """
        start_time = time.time()
        iterations = 0

        logger.info(f"Starting autonomous execution with {len(self.goals)} goals")

        while iterations < self.max_iterations:
            iterations += 1

            # Check timeout
            if time.time() - start_time > timeout:
                logger.warning("Autonomous execution timed out")
                break

            # Find next goal to execute
            next_goal = self._get_next_goal()

            if not next_goal:
                # All goals done or blocked
                break

            # Execute
            success = await self.execute_goal(next_goal)

            # Log
            self.execution_log.append({
                "iteration": iterations,
                "goal_id": next_goal.id,
                "success": success,
                "timestamp": datetime.now().isoformat()
            })

        # Compile results
        results = {
            "completed": [g.id for g in self.goals.values() if g.status == GoalStatus.COMPLETED],
            "failed": [g.id for g in self.goals.values() if g.status == GoalStatus.FAILED],
            "pending": [g.id for g in self.goals.values() if g.status == GoalStatus.PENDING],
            "iterations": iterations,
            "duration_s": time.time() - start_time,
            "results": {g.id: g.result for g in self.goals.values() if g.result}
        }

        logger.info(f"Autonomous execution complete: {len(results['completed'])} completed, {len(results['failed'])} failed")

        return results

    def _get_next_goal(self) -> Optional[Goal]:
        """Get next goal to execute based on priority and dependencies."""
        ready_goals = [
            g for g in self.goals.values()
            if g.status == GoalStatus.PENDING and g.is_ready(self.completed_goals)
        ]

        # Also include failed goals that can retry
        retryable = [
            g for g in self.goals.values()
            if g.status == GoalStatus.FAILED and g.can_retry()
        ]

        candidates = ready_goals + retryable

        if not candidates:
            return None

        # Sort by priority (lower = higher priority)
        candidates.sort(key=lambda g: (g.priority, g.attempts))

        return candidates[0]

    def get_status(self) -> dict[str, Any]:
        """Get current status of all goals."""
        return {
            "goals": {
                g.id: {
                    "description": g.description,
                    "status": g.status.value,
                    "attempts": g.attempts
                }
                for g in self.goals.values()
            },
            "completed": len(self.completed_goals),
            "total": len(self.goals)
        }
