# aiccel/autonomous/self_reflection.py
"""
Self-Reflection Capabilities
=============================

Enables agents to learn from mistakes and improve.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Reflection:
    """A reflection on an action or outcome."""
    action: str
    outcome: str
    analysis: str
    learnings: list[str]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_prompt(self) -> str:
        """Convert to prompt context."""
        return f"""Previous Action: {self.action}
Outcome: {self.outcome}
Learnings: {', '.join(self.learnings)}"""


class SelfReflection:
    """
    Self-reflection system for agent improvement.

    Maintains a memory of past actions and their outcomes
    to inform future decisions.
    """

    def __init__(self, max_memories: int = 50):
        self.memories: list[Reflection] = []
        self.max_memories = max_memories
        self.patterns: dict[str, list[str]] = {}  # error_type -> fixes

    def add_reflection(
        self,
        action: str,
        outcome: str,
        success: bool,
        analysis: str = "",
        learnings: Optional[list[str]] = None
    ):
        """Add a reflection to memory."""
        reflection = Reflection(
            action=action,
            outcome=outcome,
            analysis=analysis,
            learnings=learnings or []
        )

        self.memories.append(reflection)

        # Trim if too many
        if len(self.memories) > self.max_memories:
            self.memories = self.memories[-self.max_memories:]

        # Update patterns
        if not success:
            error_type = self._extract_error_type(outcome)
            if error_type and learnings:
                if error_type not in self.patterns:
                    self.patterns[error_type] = []
                self.patterns[error_type].extend(learnings)

    def _extract_error_type(self, outcome: str) -> Optional[str]:
        """Extract error type from outcome."""
        outcome_lower = outcome.lower()

        if "timeout" in outcome_lower:
            return "timeout"
        if "rate limit" in outcome_lower:
            return "rate_limit"
        if "not found" in outcome_lower:
            return "not_found"
        if "invalid" in outcome_lower:
            return "validation"
        if "error" in outcome_lower:
            return "general_error"

        return None

    def get_relevant_learnings(self, context: str) -> list[str]:
        """Get learnings relevant to current context."""
        learnings = []
        context_lower = context.lower()

        for reflection in reversed(self.memories[-10:]):
            if any(word in context_lower for word in reflection.action.lower().split()):
                learnings.extend(reflection.learnings)

        return list(set(learnings))[:5]  # Dedupe and limit

    def get_fix_for_error(self, error_type: str) -> Optional[str]:
        """Get suggested fix for error type."""
        fixes = self.patterns.get(error_type, [])
        if fixes:
            return fixes[-1]  # Most recent fix
        return None

    def get_context_prompt(self, max_reflections: int = 3) -> str:
        """Get reflection context for prompting."""
        if not self.memories:
            return ""

        recent = self.memories[-max_reflections:]

        prompt_parts = ["<reflections>"]
        for r in recent:
            prompt_parts.append(r.to_prompt())
        prompt_parts.append("</reflections>")

        return "\n".join(prompt_parts)

    def clear(self):
        """Clear all memories."""
        self.memories.clear()
        self.patterns.clear()


class ReflectionMixin:
    """
    Mixin to add self-reflection to any agent.

    Usage:
        class MyAgent(SlimAgent, ReflectionMixin):
            pass

        agent = MyAgent(provider=...)
        agent.enable_reflection()
    """

    _reflection_system: Optional[SelfReflection] = None

    def enable_reflection(self, max_memories: int = 50):
        """Enable self-reflection."""
        self._reflection_system = SelfReflection(max_memories=max_memories)
        return self

    def reflect(
        self,
        action: str,
        outcome: str,
        success: bool,
        analysis: str = "",
        learnings: Optional[list[str]] = None
    ):
        """Add a reflection about an action."""
        if self._reflection_system:
            self._reflection_system.add_reflection(
                action, outcome, success, analysis, learnings
            )

    def get_reflection_context(self) -> str:
        """Get reflection context for prompts."""
        if self._reflection_system:
            return self._reflection_system.get_context_prompt()
        return ""

    def get_learnings(self, context: str) -> list[str]:
        """Get relevant learnings for context."""
        if self._reflection_system:
            return self._reflection_system.get_relevant_learnings(context)
        return []
