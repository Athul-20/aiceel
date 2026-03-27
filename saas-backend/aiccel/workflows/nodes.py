# aiccel/workflows/nodes.py
"""
Workflow Nodes
===============

Pre-built node types for common workflow patterns.
"""

import asyncio
from typing import TYPE_CHECKING, Any, Callable, Optional

from .graph import WorkflowNode, WorkflowState


if TYPE_CHECKING:
    from ..agent_slim import SlimAgent
    from ..tools import Tool


class AgentNode(WorkflowNode):
    """
    Node that executes an AI agent.

    Usage:
        node = AgentNode(
            id="research",
            name="Research Agent",
            agent=research_agent,
            input_key="topic",
            output_key="research_results"
        )
    """

    def __init__(
        self,
        id: str,
        name: str = "",
        agent: Optional['SlimAgent'] = None,
        input_key: str = "query",
        output_key: str = "response",
        prompt_template: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            id=id,
            name=name or id,
            type="agent",
            config={
                "input_key": input_key,
                "output_key": output_key,
                "prompt_template": prompt_template
            }
        )
        self.agent = agent
        self.input_key = input_key
        self.output_key = output_key
        self.prompt_template = prompt_template

    async def execute(self, state: WorkflowState) -> Any:
        """Execute the agent node."""
        if not self.agent:
            raise ValueError(f"No agent configured for node {self.id}")

        # Get input
        query = state.get(self.input_key, "")

        # Apply template if provided
        if self.prompt_template:
            query = self.prompt_template.format(**state.outputs, **state.inputs)

        # Run agent
        result = await self.agent.run_async(query)

        # Store output
        state.set(self.output_key, result.get("response", ""))

        return result


class ToolNode(WorkflowNode):
    """
    Node that executes a tool directly.

    Usage:
        node = ToolNode(
            id="search",
            name="Web Search",
            tool=search_tool,
            args_mapping={"query": "search_query"}
        )
    """

    def __init__(
        self,
        id: str,
        name: str = "",
        tool: Optional['Tool'] = None,
        args_mapping: Optional[dict[str, str]] = None,
        output_key: str = "tool_result",
        **kwargs
    ):
        super().__init__(
            id=id,
            name=name or id,
            type="tool",
            config={
                "args_mapping": args_mapping or {},
                "output_key": output_key
            }
        )
        self.tool = tool
        self.args_mapping = args_mapping or {}
        self.output_key = output_key

    async def execute(self, state: WorkflowState) -> Any:
        """Execute the tool node."""
        if not self.tool:
            raise ValueError(f"No tool configured for node {self.id}")

        # Map arguments from state
        args = {}
        for tool_arg, state_key in self.args_mapping.items():
            args[tool_arg] = state.get(state_key)

        # Execute tool
        if hasattr(self.tool, 'execute_async'):
            result = await self.tool.execute_async(**args)
        else:
            result = self.tool.execute(**args)

        # Store output
        state.set(self.output_key, result)

        return result


class RouterNode(WorkflowNode):
    """
    Node that routes to different paths based on conditions.

    Usage:
        node = RouterNode(
            id="router",
            routes={
                "weather": lambda s: "weather" in s.get("query", "").lower(),
                "search": lambda s: True  # default
            }
        )
    """

    def __init__(
        self,
        id: str,
        name: str = "",
        routes: Optional[dict[str, Callable[[WorkflowState], bool]]] = None,
        output_key: str = "route",
        **kwargs
    ):
        super().__init__(
            id=id,
            name=name or id,
            type="router",
            config={"output_key": output_key}
        )
        self.routes = routes or {}
        self.output_key = output_key

    async def execute(self, state: WorkflowState) -> str:
        """Determine which route to take."""
        for route_name, condition in self.routes.items():
            if condition(state):
                state.set(self.output_key, route_name)
                return route_name

        # Default route
        state.set(self.output_key, "default")
        return "default"


class ParallelNode(WorkflowNode):
    """
    Node that executes multiple sub-nodes in parallel.

    Usage:
        node = ParallelNode(
            id="parallel_search",
            nodes=[search_node_1, search_node_2, search_node_3],
            combine_strategy="merge"
        )
    """

    def __init__(
        self,
        id: str,
        name: str = "",
        nodes: Optional[list[WorkflowNode]] = None,
        combine_strategy: str = "merge",  # merge, list, first
        output_key: str = "parallel_results",
        **kwargs
    ):
        super().__init__(
            id=id,
            name=name or id,
            type="parallel",
            config={
                "combine_strategy": combine_strategy,
                "output_key": output_key
            }
        )
        self.sub_nodes = nodes or []
        self.combine_strategy = combine_strategy
        self.output_key = output_key

    async def execute(self, state: WorkflowState) -> Any:
        """Execute all sub-nodes in parallel."""
        tasks = []
        for node in self.sub_nodes:
            if hasattr(node, 'execute'):
                tasks.append(node.execute(state))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Combine results
        if self.combine_strategy == "merge":
            combined = {}
            for result in results:
                if isinstance(result, dict):
                    combined.update(result)
            state.set(self.output_key, combined)
            return combined

        elif self.combine_strategy == "list":
            state.set(self.output_key, list(results))
            return results

        elif self.combine_strategy == "first":
            first = results[0] if results else None
            state.set(self.output_key, first)
            return first

        return results


class ConditionalNode(WorkflowNode):
    """
    Node that executes different logic based on a condition.

    Usage:
        node = ConditionalNode(
            id="check_quality",
            condition=lambda s: len(s.get("response", "")) > 100,
            true_node=continue_node,
            false_node=retry_node
        )
    """

    def __init__(
        self,
        id: str,
        name: str = "",
        condition: Optional[Callable[[WorkflowState], bool]] = None,
        true_node: Optional[WorkflowNode] = None,
        false_node: Optional[WorkflowNode] = None,
        **kwargs
    ):
        super().__init__(
            id=id,
            name=name or id,
            type="conditional",
            config={}
        )
        self.condition = condition
        self.true_node = true_node
        self.false_node = false_node

    async def execute(self, state: WorkflowState) -> Any:
        """Execute based on condition."""
        if self.condition and self.condition(state):
            if self.true_node:
                return await self.true_node.execute(state)
        elif self.false_node:
            return await self.false_node.execute(state)

        return None


class TransformNode(WorkflowNode):
    """
    Node that transforms state data.

    Usage:
        node = TransformNode(
            id="format_output",
            transform=lambda s: {"formatted": s.get("response", "").upper()}
        )
    """

    def __init__(
        self,
        id: str,
        name: str = "",
        transform: Optional[Callable[[WorkflowState], dict[str, Any]]] = None,
        **kwargs
    ):
        super().__init__(
            id=id,
            name=name or id,
            type="transform",
            config={}
        )
        self.transform = transform

    async def execute(self, state: WorkflowState) -> dict[str, Any]:
        """Transform state data."""
        if self.transform:
            result = self.transform(state)
            if isinstance(result, dict):
                state.outputs.update(result)
            return result
        return {}
