
import asyncio
import threading
import time
from collections import OrderedDict
from typing import Any, Optional

import aiohttp

from .agent import Agent
from .logger import AILogger
from .orchestration.collaborator import Collaborator
from .orchestration.router import Router


class AgentManager:
    """Manages multiple specialized agents with thread-safe caching"""

    def __init__(self, llm_provider, agents=None, verbose=False, instructions: Optional[str] = None,
                 log_file: Optional[str] = None, structured_logging: bool = False,
                 fallback_providers: Optional[list] = None):
        self.provider = llm_provider
        self.agents = {}
        self.history = []
        self.verbose = verbose
        self.instructions = instructions or (
            "Route queries to the most appropriate agent based on their expertise and available tools. "
            "Consider the query's intent, required knowledge, and tool capabilities."
        )
        self.logger = AILogger(
            name="AgentManager",
            verbose=verbose,
            log_file=log_file,
            structured_logging=structured_logging
        )
        self.fallback_providers = fallback_providers or []
        self.http_session = None
        self.semaphore = asyncio.Semaphore(2)

        # Thread-safe tool cache with LRU eviction
        self._tool_cache_lock = threading.RLock()
        self._tool_cache = OrderedDict()
        self._tool_cache_max_size = 1000
        self._tool_cache_ttl = 3600  # 1 hour
        self._tool_cache_timestamps = {}

        if agents:
            if isinstance(agents, list):
                for agent in agents:
                    self.add_agent(agent.name, agent, f"Agent specialized in {agent.name} tasks")
            elif isinstance(agents, dict):
                for name, agent_info in agents.items():
                    if isinstance(agent_info, dict):
                        self.add_agent(name, agent_info.get("agent"), agent_info.get("description", f"Agent specialized in {name} tasks"))
                    else:
                        self.add_agent(name, agent_info, f"Agent specialized in {name} tasks")

        # Initialize Orchestration components
        self.router = Router(
            agents=self.agents,
            provider=self.provider,
            fallback_providers=self.fallback_providers,
            logger=self.logger,
            instructions=self.instructions
        )
        self.collaborator = Collaborator(
            agents=self.agents,
            provider=self.provider,
            fallback_providers=self.fallback_providers,
            logger=self.logger,
            instructions=self.instructions,
            semaphore=self.semaphore,
            cache_callback=self._set_in_cache
        )

    async def __aenter__(self):
        self.http_session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.http_session:
            await self.http_session.close()

    def _get_from_cache(self, key: str) -> Optional[Any]:
        with self._tool_cache_lock:
            if key not in self._tool_cache:
                return None
            timestamp = self._tool_cache_timestamps.get(key, 0)
            if time.time() - timestamp > self._tool_cache_ttl:
                del self._tool_cache[key]
                del self._tool_cache_timestamps[key]
                return None
            self._tool_cache.move_to_end(key)
            return self._tool_cache[key]

    def _set_in_cache(self, key: str, value: Any):
        with self._tool_cache_lock:
            if len(self._tool_cache) >= self._tool_cache_max_size:
                oldest_key = next(iter(self._tool_cache))
                del self._tool_cache[oldest_key]
                del self._tool_cache_timestamps[oldest_key]
            self._tool_cache[key] = value
            self._tool_cache_timestamps[key] = time.time()

    def _clear_cache(self):
        with self._tool_cache_lock:
            self._tool_cache.clear()
            self._tool_cache_timestamps.clear()

    @classmethod
    def from_agents(cls, agents: list[Agent], llm_provider=None, verbose=False,
                    instructions: Optional[str] = None, log_file: Optional[str] = None,
                    structured_logging: bool = False,
                    fallback_providers: Optional[list] = None) -> 'AgentManager':
        if not llm_provider and agents:
            llm_provider = agents[0].provider
        manager = cls(llm_provider, agents=None, verbose=verbose, instructions=instructions,
                     log_file=log_file, structured_logging=structured_logging, fallback_providers=fallback_providers)
        for agent in agents:
            manager.add_agent(agent.name, agent, f"Agent specialized in {agent.name} tasks")
        return manager

    def set_verbose(self, verbose: bool = True) -> 'AgentManager':
        self.verbose = verbose
        self.logger.verbose = verbose
        for _name, info in self.agents.items():
            info["agent"].set_verbose(verbose)
        self.logger.info(f"Verbose mode set to: {verbose}")
        return self

    def set_instructions(self, instructions: str) -> 'AgentManager':
        self.instructions = instructions
        self.router.instructions = instructions
        self.collaborator.instructions = instructions
        self.logger.info(f"Updated routing instructions: {instructions[:50]}...")
        return self

    def add_agent(self, name: str, agent: Agent, description: str) -> 'AgentManager':
        self.agents[name] = {
            "agent": agent,
            "description": description
        }
        agent.name = name
        agent.set_verbose(self.verbose)
        agent._get_from_shared_cache = self._get_from_cache
        agent._set_in_shared_cache = self._set_in_cache
        self.logger.info(f"Added agent: {name} - {description}")
        return self

    def route(self, query: str) -> dict[str, Any]:
        """Route query to the most appropriate agent."""
        return self.router.route(query)

    async def route_async(self, query: str) -> dict[str, Any]:
        """Route query asynchronously."""
        return await self.router.route_async(query)

    def collaborate(self, query: str, max_agents: int = 5, agent_ids: Optional[list[str]] = None) -> dict[str, Any]:
        """Orchestrate collaboration between agents."""
        return self.collaborator.collaborate(query, max_agents, agent_ids)

    async def collaborate_async(self, query: str, max_agents: int = 5, agent_ids: Optional[list[str]] = None) -> dict[str, Any]:
        """Orchestrate collaboration asynchronously."""
        async with self:  # Ensure HTTP session used if needed
            return await self.collaborator.collaborate_async(query, max_agents, agent_ids)
