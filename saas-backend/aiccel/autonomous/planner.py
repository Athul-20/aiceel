# aiccel/autonomous/planner.py
"""
Task Planner
=============

AI-powered task decomposition and planning.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class TaskStatus(Enum):
    """Status of a task."""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """A single task in a plan."""
    id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    dependencies: list[str] = field(default_factory=list)
    assigned_agent: Optional[str] = None
    priority: int = 1
    estimated_time: Optional[float] = None
    actual_time: Optional[float] = None
    result: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_ready(self, completed: set) -> bool:
        """Check if all dependencies completed."""
        return all(dep in completed for dep in self.dependencies)


@dataclass
class Plan:
    """A plan consisting of ordered tasks."""
    id: str
    name: str
    goal: str
    tasks: list[Task] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    status: str = "active"

    def add_task(self, task: Task) -> 'Plan':
        self.tasks.append(task)
        return self

    def get_next_task(self, completed: set) -> Optional[Task]:
        """Get next ready task."""
        for task in self.tasks:
            if task.status == TaskStatus.TODO and task.is_ready(completed):
                return task
        return None

    def get_progress(self) -> dict[str, Any]:
        """Get plan progress."""
        total = len(self.tasks)
        done = sum(1 for t in self.tasks if t.status == TaskStatus.DONE)

        return {
            "total_tasks": total,
            "completed": done,
            "progress_pct": (done / total * 100) if total > 0 else 0,
            "remaining": total - done
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "goal": self.goal,
            "tasks": [
                {"id": t.id, "title": t.title, "status": t.status.value}
                for t in self.tasks
            ],
            "progress": self.get_progress()
        }


class TaskPlanner:
    """
    AI-powered task planner.

    Uses LLM to decompose goals into executable tasks.

    Usage:
        planner = TaskPlanner(provider=...)
        plan = await planner.create_plan("Build a web scraper")

        for task in plan.tasks:
            print(f"- {task.title}")
    """

    def __init__(
        self,
        provider,
        max_tasks: int = 10,
        include_estimates: bool = True
    ):
        self.provider = provider
        self.max_tasks = max_tasks
        self.include_estimates = include_estimates

    async def create_plan(
        self,
        goal: str,
        context: str = "",
        constraints: Optional[list[str]] = None
    ) -> Plan:
        """
        Create a plan for achieving a goal.

        Args:
            goal: High-level goal description
            context: Additional context
            constraints: Any constraints to consider

        Returns:
            Plan with decomposed tasks
        """
        import uuid

        plan_id = str(uuid.uuid4())[:8]

        constraints_text = ""
        if constraints:
            constraints_text = "\nConstraints:\n" + "\n".join(f"- {c}" for c in constraints)

        prompt = f"""You are a task planning expert. Create a detailed plan for this goal:

Goal: {goal}

{f'Context: {context}' if context else ''}
{constraints_text}

Break this into {self.max_tasks} or fewer specific, actionable tasks.
For each task, provide:
1. Task ID (T1, T2, etc.)
2. Title (brief description)
3. Dependencies (list of task IDs this depends on, or "none")
{'4. Time estimate (in minutes)' if self.include_estimates else ''}

Format each task as:
T[N]: [Title] | Deps: [T1, T2 or none] {'| Time: [X min]' if self.include_estimates else ''}

List tasks in recommended execution order."""

        response = self.provider.generate(prompt)

        # Parse tasks
        tasks = self._parse_tasks(response)

        return Plan(
            id=plan_id,
            name=f"Plan: {goal[:30]}...",
            goal=goal,
            tasks=tasks
        )

    def _parse_tasks(self, response: str) -> list[Task]:
        """Parse tasks from LLM response."""
        tasks = []
        lines = response.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line or not line.startswith("T"):
                continue

            try:
                # Parse: T1: Title | Deps: none | Time: 10 min
                parts = line.split("|")

                # Task ID and title
                id_title = parts[0].strip()
                if ":" in id_title:
                    task_id, title = id_title.split(":", 1)
                    task_id = task_id.strip()
                    title = title.strip()
                else:
                    continue

                # Dependencies
                deps = []
                for part in parts[1:]:
                    if "dep" in part.lower():
                        deps_text = part.split(":", 1)[1].strip().lower()
                        if deps_text != "none":
                            deps = [d.strip() for d in deps_text.split(",")]

                # Time estimate
                time_estimate = None
                for part in parts[1:]:
                    if "time" in part.lower() or "min" in part.lower():
                        import re
                        numbers = re.findall(r'\d+', part)
                        if numbers:
                            time_estimate = float(numbers[0])

                tasks.append(Task(
                    id=task_id,
                    title=title,
                    dependencies=deps,
                    estimated_time=time_estimate
                ))

            except Exception:
                continue

        return tasks

    async def refine_task(
        self,
        task: Task,
        feedback: str = ""
    ) -> Task:
        """Refine a task based on feedback."""
        prompt = f"""Refine this task based on feedback:

Task: {task.title}
Current Description: {task.description}
Feedback: {feedback}

Provide:
1. Improved title
2. Detailed description
3. Any additional considerations

Keep it actionable and specific."""

        response = self.provider.generate(prompt)

        # Update task
        task.description = response

        return task

    async def estimate_complexity(self, goal: str) -> dict[str, Any]:
        """Estimate complexity of a goal."""
        prompt = f"""Estimate the complexity of this goal:

Goal: {goal}

Provide:
1. Complexity (low/medium/high)
2. Estimated total time (hours)
3. Required skills/tools
4. Potential blockers

Be realistic and concise."""

        response = self.provider.generate(prompt)

        # Parse (simplified)
        complexity = "medium"
        if "low" in response.lower():
            complexity = "low"
        elif "high" in response.lower():
            complexity = "high"

        return {
            "goal": goal,
            "complexity": complexity,
            "analysis": response
        }
