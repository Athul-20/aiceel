# aiccel/workflows/builder.py
"""
Workflow Builder
=================

Fluent API for building workflows.
"""

from typing import TYPE_CHECKING, Callable, Optional

from .graph import EdgeType, Workflow, WorkflowNode
from .nodes import AgentNode, ConditionalNode, ParallelNode, RouterNode, ToolNode, TransformNode


if TYPE_CHECKING:
    from ..agent_slim import SlimAgent
    from ..tools import Tool


class WorkflowBuilder:
    """
    Fluent builder for creating workflows.

    Usage:
        workflow = (
            WorkflowBuilder("research_pipeline")
            .add_agent("researcher", research_agent)
            .add_agent("writer", writer_agent, input_key="research_results")
            .connect("researcher", "writer")
            .build()
        )
    """

    def __init__(self, name: str, description: str = ""):
        self.workflow = Workflow(name=name, description=description)
        self._node_count = 0

    def add_node(self, node: WorkflowNode) -> 'WorkflowBuilder':
        """Add a generic node."""
        self.workflow.add_node(node)
        self._node_count += 1
        return self

    def add_agent(
        self,
        id: str,
        agent: 'SlimAgent',
        name: str = "",
        input_key: str = "query",
        output_key: str = "response",
        prompt_template: Optional[str] = None
    ) -> 'WorkflowBuilder':
        """Add an agent node."""
        node = AgentNode(
            id=id,
            name=name or id,
            agent=agent,
            input_key=input_key,
            output_key=output_key,
            prompt_template=prompt_template
        )
        return self.add_node(node)

    def add_tool(
        self,
        id: str,
        tool: 'Tool',
        name: str = "",
        args_mapping: Optional[dict[str, str]] = None,
        output_key: str = "tool_result"
    ) -> 'WorkflowBuilder':
        """Add a tool node."""
        node = ToolNode(
            id=id,
            name=name or id,
            tool=tool,
            args_mapping=args_mapping,
            output_key=output_key
        )
        return self.add_node(node)

    def add_router(
        self,
        id: str,
        routes: dict[str, Callable],
        name: str = ""
    ) -> 'WorkflowBuilder':
        """Add a router node."""
        node = RouterNode(
            id=id,
            name=name or id,
            routes=routes
        )
        return self.add_node(node)

    def add_parallel(
        self,
        id: str,
        nodes: list[WorkflowNode],
        name: str = "",
        combine_strategy: str = "merge"
    ) -> 'WorkflowBuilder':
        """Add a parallel execution node."""
        node = ParallelNode(
            id=id,
            name=name or id,
            nodes=nodes,
            combine_strategy=combine_strategy
        )
        return self.add_node(node)

    def add_conditional(
        self,
        id: str,
        condition: Callable,
        true_node: WorkflowNode,
        false_node: Optional[WorkflowNode] = None,
        name: str = ""
    ) -> 'WorkflowBuilder':
        """Add a conditional node."""
        node = ConditionalNode(
            id=id,
            name=name or id,
            condition=condition,
            true_node=true_node,
            false_node=false_node
        )
        return self.add_node(node)

    def add_transform(
        self,
        id: str,
        transform: Callable,
        name: str = ""
    ) -> 'WorkflowBuilder':
        """Add a transform node."""
        node = TransformNode(
            id=id,
            name=name or id,
            transform=transform
        )
        return self.add_node(node)

    def add_function(
        self,
        id: str,
        func: Callable,
        name: str = ""
    ) -> 'WorkflowBuilder':
        """Add a simple function node."""
        node = WorkflowNode(
            id=id,
            name=name or id,
            type="function",
            handler=func
        )
        return self.add_node(node)

    def connect(
        self,
        source: str,
        target: str,
        condition: Optional[Callable] = None
    ) -> 'WorkflowBuilder':
        """Connect two nodes with an edge."""
        edge_type = EdgeType.CONDITIONAL if condition else EdgeType.DEFAULT
        self.workflow.add_edge(source, target, edge_type, condition)
        return self

    def connect_conditional(
        self,
        source: str,
        routes: dict[str, str],
        condition_key: str = "route"
    ) -> 'WorkflowBuilder':
        """Connect to multiple targets based on state value."""
        for route_value, target in routes.items():
            def condition(s, v=route_value, k=condition_key):
                return s.get(k) == v
            self.workflow.add_edge(source, target, EdgeType.CONDITIONAL, condition)
        return self

    def set_entry(self, node_id: str) -> 'WorkflowBuilder':
        """Set the entry node."""
        self.workflow.set_entry(node_id)
        return self

    def set_end(self, node_id: str) -> 'WorkflowBuilder':
        """Mark a node as an end node."""
        self.workflow.set_end(node_id)
        return self

    def chain(self, *node_ids: str) -> 'WorkflowBuilder':
        """Connect nodes in sequence."""
        for i in range(len(node_ids) - 1):
            self.connect(node_ids[i], node_ids[i + 1])
        return self

    def build(self) -> Workflow:
        """Build and return the workflow."""
        errors = self.workflow.validate()
        if errors:
            raise ValueError(f"Invalid workflow: {errors}")
        return self.workflow

    def __repr__(self) -> str:
        return f"<WorkflowBuilder(name='{self.workflow.name}', nodes={self._node_count})>"


# Convenience function
def workflow(name: str, description: str = "") -> WorkflowBuilder:
    """Create a new workflow builder."""
    return WorkflowBuilder(name, description)
