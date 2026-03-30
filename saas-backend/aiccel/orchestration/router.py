
from datetime import datetime
from typing import Any, Optional

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..logger import AILogger


class Router:
    """Handles query routing to appropriate agents."""

    def __init__(self, agents: dict[str, Any], provider: Any, fallback_providers: list[Any], logger: AILogger, instructions: str):
        self.agents = agents
        self.provider = provider
        self.fallback_providers = fallback_providers
        self.logger = logger
        self.instructions = instructions
        self.history = []

    def _build_agent_descriptions(self) -> str:
        agent_descriptions = []
        for name, info in self.agents.items():
            tool_info = ""
            if agent := info["agent"]:
                if hasattr(agent, "tool_registry") and agent.tool_registry:
                    tools = agent.tool_registry.get_all()
                    if tools:
                        tool_names = [t.name for t in tools]
                        tool_info = f" (Tools: {', '.join(tool_names)})"
            agent_descriptions.append(f"- {name}: {info['description']}{tool_info}")
        return "\n".join(agent_descriptions)

    def _select_default_agent(self) -> str:
        """Select a default agent when routing fails."""
        if not self.agents:
            return None
        sorted_agents = sorted(self.agents.keys())
        selected_agent = sorted_agents[0]
        self.logger.info(f"Selected default agent: {selected_agent}")
        return selected_agent

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    def route(self, query: str, tpt=None) -> dict[str, Any]:
        trace_id = self.logger.trace_start("route_query", {"query": query[:100] + "..." if len(query) > 100 else query})

        if not self.agents:
            raise ValueError("No agents available")

        if len(self.agents) == 1:
            return self._execute_single_agent(query, trace_id, tpt=tpt)

        agent_descriptions_text = self._build_agent_descriptions()
        routing_prompt = (
            f"Instructions: {self.instructions}\n\n"
            f"Query: {query}\n\n"
            "Available agents:\n"
            f"{agent_descriptions_text}\n\n"
            "Select the most appropriate agent to handle this query based on their expertise and tools. "
            "You MUST return only the agent name as a plain string (e.g., 'weather_expert'). "
            "Do not include any additional text, explanations, or formatting."
        )

        selected_agent = self._get_routing_decision(routing_prompt, trace_id)

        if not selected_agent:
            selected_agent = self._select_default_agent()

        return self._execute_agent(selected_agent, query, trace_id, tpt=tpt)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def route_async(self, query: str, tpt=None) -> dict[str, Any]:
        trace_id = self.logger.trace_start("route_query_async", {"query": query[:100] + "..." if len(query) > 100 else query})

        if not self.agents:
            raise ValueError("No agents available")

        if len(self.agents) == 1:
            return await self._execute_single_agent_async(query, trace_id, tpt=tpt)

        agent_descriptions_text = self._build_agent_descriptions()
        routing_prompt = (
            f"Instructions: {self.instructions}\n\n"
            f"Query: {query}\n\n"
            "Available agents:\n"
            f"{agent_descriptions_text}\n\n"
            "Select the most appropriate agent to handle this query based on their expertise and tools. "
            "You MUST return only the agent name as a plain string (e.g., 'weather_expert'). "
            "Do not include any additional text, explanations, or formatting."
        )

        selected_agent = await self._get_routing_decision_async(routing_prompt, trace_id)

        if not selected_agent:
            selected_agent = self._select_default_agent()

        return await self._execute_agent_async(selected_agent, query, trace_id, tpt=tpt)

    def _execute_single_agent(self, query: str, trace_id: int, tpt=None) -> dict[str, Any]:
        agent_name = next(iter(self.agents.keys()))
        return self._execute_agent(agent_name, query, trace_id, tpt=tpt)

    async def _execute_single_agent_async(self, query: str, trace_id: int, tpt=None) -> dict[str, Any]:
        agent_name = next(iter(self.agents.keys()))
        return await self._execute_agent_async(agent_name, query, trace_id, tpt=tpt)

    def _get_routing_decision(self, prompt: str, trace_id: int) -> Optional[str]:
        providers = [self.provider, *self.fallback_providers]
        for provider in providers:
            try:
                selected_agent = provider.generate(prompt).strip()
                if selected_agent in self.agents:
                    return selected_agent
            except Exception as e:
                self.logger.trace_error(trace_id, e, f"Routing with provider {type(provider).__name__} failed")
        return None

    async def _get_routing_decision_async(self, prompt: str, trace_id: int) -> Optional[str]:
        providers = [self.provider, *self.fallback_providers]
        for provider in providers:
            try:
                selected_agent = (await provider.generate_async(prompt)).strip()
                if selected_agent in self.agents:
                    return selected_agent
            except Exception as e:
                self.logger.trace_error(trace_id, e, f"Async routing with provider {type(provider).__name__} failed")
        return None

    def _execute_agent(self, agent_name: str, query: str, trace_id: int, tpt=None) -> dict[str, Any]:
        agent = self.agents[agent_name]["agent"]
        self.logger.info(f"Routing query to agent: {agent_name}")
        try:
            result = agent.run(query)
            result["agent_used"] = agent_name

            # CABTP: Canary scan on agent response
            if tpt is not None:
                from ..cabtp.canary import scan_response
                response_text = result.get("response", "")
                is_poisoned, scan_result = scan_response(response_text, tpt.canary_token)
                result["cabtp_status"] = "SESSION_POISONED" if is_poisoned else "CLEAN"
                result["canary_scan"] = {
                    "is_poisoned": is_poisoned,
                    "scan_time_ms": scan_result.scan_time_ms,
                }
                if is_poisoned:
                    self.logger.info(f"CABTP: Canary leak detected in agent '{agent_name}'")
                    result["response"] = (
                        "[SESSION TERMINATED] Security violation detected: "
                        "agent leaked session integrity data."
                    )
            else:
                result["cabtp_status"] = "DISABLED"

            self.history.append({
                "query": query,
                "agent": agent_name,
                "response": result["response"],
                "timestamp": datetime.now().isoformat()
            })
            self.logger.trace_end(trace_id, result)
            return result
        except Exception as e:
            self.logger.trace_error(trace_id, e, f"Agent {agent_name} execution failed")
            raise

    async def _execute_agent_async(self, agent_name: str, query: str, trace_id: int, tpt=None) -> dict[str, Any]:
        agent = self.agents[agent_name]["agent"]
        self.logger.info(f"Routing query to agent: {agent_name}")
        try:
            result = await agent.run_async(query)
            result["agent_used"] = agent_name

            # CABTP: Canary scan on agent response
            if tpt is not None:
                from ..cabtp.canary import scan_response
                response_text = result.get("response", "")
                is_poisoned, scan_result = scan_response(response_text, tpt.canary_token)
                result["cabtp_status"] = "SESSION_POISONED" if is_poisoned else "CLEAN"
                result["canary_scan"] = {
                    "is_poisoned": is_poisoned,
                    "scan_time_ms": scan_result.scan_time_ms,
                }
                if is_poisoned:
                    self.logger.info(f"CABTP: Canary leak detected in agent '{agent_name}'")
                    result["response"] = (
                        "[SESSION TERMINATED] Security violation detected: "
                        "agent leaked session integrity data."
                    )
            else:
                result["cabtp_status"] = "DISABLED"

            self.history.append({
                "query": query,
                "agent": agent_name,
                "response": result["response"],
                "timestamp": datetime.now().isoformat()
            })
            self.logger.trace_end(trace_id, result)
            return result
        except Exception as e:
            self.logger.trace_error(trace_id, e, f"Agent {agent_name} execution failed")
            raise
