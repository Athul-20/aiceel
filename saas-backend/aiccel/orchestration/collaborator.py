
import asyncio
import json
from datetime import datetime
from typing import Any, Callable, Optional

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..logger import AILogger
from ..utils.parsers import ResponseParser


class Collaborator:
    """Handles multi-agent collaboration and query splitting."""

    def __init__(self, agents: dict[str, Any], provider: Any, fallback_providers: list[Any],
                 logger: AILogger, instructions: str, semaphore: asyncio.Semaphore,
                 cache_callback: Optional[Callable[[str, Any], None]] = None):
        self.agents = agents
        self.provider = provider
        self.fallback_providers = fallback_providers
        self.logger = logger
        self.instructions = instructions
        self.semaphore = semaphore
        self.cache_callback = cache_callback
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
        if not self.agents:
            return None
        sorted_agents = sorted(self.agents.keys())
        return sorted_agents[0]

    def _validate_sub_queries(self, parsed: Any) -> bool:
        if not isinstance(parsed, list):
            return False
        for item in parsed:
            if not isinstance(item, dict):
                return False
            if "sub_query" not in item or "agent" not in item:
                return False
            if item["agent"] not in self.agents:
                return False
        return True

    def generate_dynamic_instructions(self, query: str) -> str:
        """Generate dynamic instructions based on the query."""
        agent_descriptions = self._build_agent_descriptions()
        prompt = (
            f"Query: {query}\n\n"
            f"Available agents:\n{agent_descriptions}\n\n"
            "Based on the query, determine the best way to split it into sub-queries and assign them to agents. "
            "Provide instructions on how to handle the query effectively, considering the agents' expertise and tools."
        )
        try:
             return self.provider.generate(prompt)
        except Exception:
             return self.instructions

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    def collaborate(self, query: str, max_agents: int = 5, agent_ids: Optional[list[str]] = None) -> dict[str, Any]:
        trace_id = self.logger.trace_start("collaborate", {"query": query[:100], "max_agents": max_agents})
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.collaborate_async(query, max_agents, agent_ids)
                )
                self.logger.trace_end(trace_id, {
                    "response": result["response"][:100],
                    "agents_used": result["agents_used"]
                })
                return result
            finally:
                loop.close()
        except Exception as e:
            self.logger.trace_error(trace_id, e, "Synchronous collaboration failed")
            raise Exception(f"Collaboration failed: {e!s}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def collaborate_async(self, query: str, max_agents: int = 5, agent_ids: Optional[list[str]] = None) -> dict[str, Any]:
        trace_id = self.logger.trace_start("collaborate_async", {"query": query[:100], "max_agents": max_agents})

        if not self.agents:
            raise ValueError("No agents available")

        # Dynamic instructions
        self.instructions = self.generate_dynamic_instructions(query) or self.instructions

        sub_queries = []
        if agent_ids:
             # Explicit agents
             valid_ids = [aid for aid in agent_ids if aid in self.agents]
             if valid_ids:
                 sub_queries = [{"sub_query": query, "agent": aid} for aid in valid_ids[:max_agents]]

        if not sub_queries:
            # LLM Splitting
            sub_queries = await self._split_query_async(query, max_agents, trace_id)

        # Execution
        results = await self._execute_sub_queries(sub_queries, trace_id)

        # Synthesis
        final_response = await self._synthesize_results(query, results, trace_id)

        agents_used = list({sq["agent"] for sq in sub_queries})

        final_result = {
            "response": final_response,
            "agent_results": results,
            "agents_used": agents_used,
            "sub_queries": sub_queries
        }

        self.history.append({
            "query": query,
            "agents": agents_used,
            "response": final_response,
            "timestamp": datetime.now().isoformat()
        })

        return final_result

    async def _split_query_async(self, query: str, max_agents: int, trace_id: int) -> list[dict[str, str]]:
        agent_descriptions = self._build_agent_descriptions()
        split_prompt = (
            f"Instructions: {self.instructions}\n\n"
            f"Query: {query}\n\n"
            f"Available agents:\n{agent_descriptions}\n\n"
            "Analyze the query and split it into distinct sub-queries, assigning each to the most appropriate agent based on their expertise and tools. "
            "Return a JSON array where each item is an object with 'sub_query' (the sub-query text) and 'agent' (the agent name). "
            "If the query cannot be split, return a single sub-query with the most suitable agent. "
            "The output MUST be valid JSON."
        )

        providers = [self.provider, *self.fallback_providers]
        for provider in providers:
            try:
                response = await provider.generate_async(split_prompt)
                parsed = ResponseParser.parse_json(response, list)
                if parsed and self._validate_sub_queries(parsed):
                     return parsed
            except Exception:
                continue

        # Default fallback
        return [{"sub_query": query, "agent": self._select_default_agent()}]

    async def _execute_sub_queries(self, sub_queries: list[dict[str, str]], trace_id: int) -> list[dict[str, Any]]:
        tasks = []
        for sq in sub_queries:
            agent_name = sq["agent"]
            query = sq["sub_query"]
            tasks.append(self._run_agent_task(agent_name, query, trace_id))

        return await asyncio.gather(*tasks)

    async def _run_agent_task(self, agent_name: str, query: str, trace_id: int) -> dict[str, Any]:
        agent = self.agents[agent_name]["agent"]
        async with self.semaphore:
            try:
                # Timeout calculation
                timeout = 45.0 if "search" in str(agent.tool_registry.get_all()) else 30.0

                result = await asyncio.wait_for(agent.run_async(query), timeout=timeout)

                # Cache callback
                if self.cache_callback and result.get("tool_used") and result.get("tool_output"):
                    cache_key = f"{result['tool_used']}:{json.dumps(result['tool_output'], sort_keys=True)}"
                    self.cache_callback(cache_key, result["tool_output"])

                return {
                    "agent": agent_name,
                    "response": result.get("response", ""),
                    "tool_used": result.get("tool_used"),
                    "tool_output": result.get("tool_output"),
                    "queries": [query]
                }
            except Exception as e:
                self.logger.trace_error(trace_id, e, f"Agent {agent_name} failed")
                return {"agent": agent_name, "response": f"Error: {e}", "queries": [query]}

    async def _synthesize_results(self, query: str, results: list[dict], trace_id: int) -> str:
        synthesis_prompt_parts = [
            "You are tasked with combining the following agent responses into a single, concise, and coherent paragraph. "
            "Avoid redundancy. "
            f"Original Query: {query}\n\nAgent Responses:\n"
        ]

        for r in results:
            agent_name = r.get("agent", "Unknown")
            response = r.get("response", "")
            synthesis_prompt_parts.append(f"Agent {agent_name}: {response}\n\n")

        prompt = "".join(synthesis_prompt_parts)

        providers = [self.provider, *self.fallback_providers]
        for provider in providers:
            try:
                return await provider.generate_async(prompt)
            except Exception:
                continue
        return "Failed to synthesize response."
