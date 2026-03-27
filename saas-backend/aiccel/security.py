# aiccel/security.py
"""
Security helpers for AICCEL.

This module provides a manual, opt-in security pipeline that users can wire
into their agents as needed. It is dependency-free and cross-platform.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .logging_config import get_logger
from .ratelimit import TokenBucketLimiter


logger = get_logger("security")


@dataclass
class SecurityPolicy:
    """Allow/deny rules for tool usage."""
    allow_tools: list[str] = field(default_factory=list)
    deny_tools: list[str] = field(default_factory=list)
    allow_regex: list[str] = field(default_factory=list)
    deny_regex: list[str] = field(default_factory=list)

    def is_tool_allowed(self, tool_name: str) -> bool:
        name = (tool_name or "").lower()

        if self.allow_tools and name not in {t.lower() for t in self.allow_tools}:
            return False

        if name in {t.lower() for t in self.deny_tools}:
            return False

        for pattern in self.deny_regex:
            if re.search(pattern, name):
                return False

        if self.allow_regex:
            for pattern in self.allow_regex:
                if re.search(pattern, name):
                    return True
            return False

        return True


@dataclass
class RedactionPolicy:
    """Pattern-based redaction policy."""
    replacement: str = "[REDACTED]"
    patterns: list[re.Pattern] = field(default_factory=list)

    @classmethod
    def default(cls) -> "RedactionPolicy":
        patterns = [
            re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE),
            re.compile(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"),
            re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
            re.compile(r"sk-[A-Za-z0-9]{20,}"),
            re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
            re.compile(r"(?i)api[_-]?key\s*[:=]\s*[A-Za-z0-9\-_]{8,}"),
        ]
        return cls(patterns=patterns)

    def redact(self, text: str) -> str:
        if not text:
            return text
        redacted = text
        for pattern in self.patterns:
            redacted = pattern.sub(self.replacement, redacted)
        return redacted


@dataclass
class PromptInjectionGuard:
    """Simple prompt injection detector."""
    patterns: list[re.Pattern] = field(default_factory=list)

    @classmethod
    def default(cls) -> "PromptInjectionGuard":
        patterns = [
            re.compile(r"ignore (all|previous) (instructions|messages)", re.IGNORECASE),
            re.compile(r"reveal (the )?system prompt", re.IGNORECASE),
            re.compile(r"developer message", re.IGNORECASE),
            re.compile(r"bypass (safety|policy|guard)", re.IGNORECASE),
            re.compile(r"jailbreak", re.IGNORECASE),
            re.compile(r"exfiltrate", re.IGNORECASE),
        ]
        return cls(patterns=patterns)

    def scan(self, text: str) -> tuple[bool, list[str]]:
        if not text:
            return True, []
        matches = []
        for pattern in self.patterns:
            if pattern.search(text):
                matches.append(pattern.pattern)
        return (len(matches) == 0), matches


class SecurityAuditLogger:
    """Structured audit log for security decisions."""

    def __init__(self, component: str = "security"):
        self._logger = get_logger(component)

    def log(self, event: str, details: dict[str, Any]) -> None:
        payload = {
            "event": event,
            "timestamp": time.time(),
            **details,
        }
        self._logger.info(json.dumps(payload, default=str))


class PolicyToolRegistry:
    """Tool registry wrapper that enforces a SecurityPolicy."""

    def __init__(self, registry: Any, policy: SecurityPolicy, audit: Optional[SecurityAuditLogger] = None):
        self._registry = registry
        self._policy = policy
        self._audit = audit

    @property
    def tools(self) -> dict[str, Any]:
        # Provide compatibility for code that accesses .tools
        if hasattr(self._registry, "tools"):
            return self._registry.tools
        if hasattr(self._registry, "_tools"):
            return self._registry._tools
        return {}

    def register(self, tool: Any) -> "PolicyToolRegistry":
        self._registry.register(tool)
        return self

    def unregister(self, name: str) -> bool:
        return self._registry.unregister(name)

    def get(self, name: str) -> Optional[Any]:
        if not self._policy.is_tool_allowed(name):
            if self._audit:
                self._audit.log("tool_denied", {"tool": name})
            return None
        return self._registry.get(name)

    def get_all(self) -> list[Any]:
        tools = self._registry.get_all()
        return [t for t in tools if self._policy.is_tool_allowed(getattr(t, "name", ""))]

    def find_relevant_tools(self, query: str) -> list[Any]:
        tools = self._registry.find_relevant_tools(query)
        return [t for t in tools if self._policy.is_tool_allowed(getattr(t, "name", ""))]

    def validate(self, name: str, args: dict[str, Any]) -> tuple[bool, list[str]]:
        if not self._policy.is_tool_allowed(name):
            return False, [f"Tool not allowed: {name}"]
        return self._registry.validate(name, args)

    def execute(self, name: str, args: dict[str, Any], validate: bool = True) -> Any:
        if not self._policy.is_tool_allowed(name):
            raise ValueError(f"Tool not allowed: {name}")
        return self._registry.execute(name, args, validate=validate)

    @property
    def names(self) -> list[str]:
        return [t.name for t in self.get_all()]

    @property
    def count(self) -> int:
        return len(self.get_all())


class SecurityPipeline:
    """
    Manual security pipeline that users can wire into agent execution.

    Provides:
    - Prompt injection guard
    - Input/Output redaction
    - Tool allow/deny policy
    - Rate limiting
    - Structured audit log
    """

    def __init__(
        self,
        policy: Optional[SecurityPolicy] = None,
        redaction: Optional[RedactionPolicy] = None,
        guard: Optional[PromptInjectionGuard] = None,
        limiter: Optional[TokenBucketLimiter] = None,
        audit: Optional[SecurityAuditLogger] = None,
        redact_response: bool = True,
    ):
        self.policy = policy or SecurityPolicy()
        self.redaction = redaction or RedactionPolicy.default()
        self.guard = guard or PromptInjectionGuard.default()
        self.limiter = limiter or TokenBucketLimiter(requests_per_minute=60)
        self.audit = audit or SecurityAuditLogger()
        self.redact_response = redact_response

    def attach(self, agent: Any) -> None:
        """Attach policy enforcement to an agent's tool registry."""
        if not hasattr(agent, "tool_registry"):
            return

        agent.tool_registry = PolicyToolRegistry(agent.tool_registry, self.policy, self.audit)
        if hasattr(agent, "prompt_builder"):
            agent.prompt_builder.tool_registry = agent.tool_registry
        if hasattr(agent, "tool_executor"):
            agent.tool_executor.tool_registry = agent.tool_registry

    def prepare_query(self, query: str, key: str = "default") -> str:
        if not self.limiter.allow(key):
            self.audit.log("rate_limited", {"key": key})
            raise ValueError("Rate limit exceeded")

        ok, matches = self.guard.scan(query)
        if not ok:
            self.audit.log("prompt_injection_blocked", {"matches": matches})
            raise ValueError("Prompt injection detected")

        redacted = self.redaction.redact(query)
        if redacted != query:
            self.audit.log("input_redacted", {"original_len": len(query), "redacted_len": len(redacted)})
        return redacted

    def finalize_response(self, response: str) -> str:
        if not self.redact_response:
            return response
        redacted = self.redaction.redact(response)
        if redacted != response:
            self.audit.log("output_redacted", {"original_len": len(response), "redacted_len": len(redacted)})
        return redacted

    def run(self, agent: Any, query: str, key: str = "default") -> dict[str, Any]:
        """Run an agent with security controls applied."""
        self.attach(agent)
        safe_query = self.prepare_query(query, key=key)
        self.audit.log("run_start", {"key": key})
        result = agent.run(safe_query)

        if isinstance(result, dict):
            response = result.get("response", "")
            result["response"] = self.finalize_response(response)
        else:
            result = {"response": self.finalize_response(str(result))}

        self.audit.log("run_complete", {"key": key})
        return result


def create_security_pipeline() -> SecurityPipeline:
    """Convenience factory for a default security pipeline."""
    return SecurityPipeline()

