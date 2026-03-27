# aiccel/workflows/graph.py
"""
Workflow Graph - Core Data Structures
======================================

DAG representation for agent workflows.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional


class NodeStatus(Enum):
    """Status of workflow node."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class EdgeType(Enum):
    """Type of workflow edge."""
    DEFAULT = "default"      # Always follow
    CONDITIONAL = "conditional"  # Follow if condition true
    PARALLEL = "parallel"    # Execute in parallel


@dataclass
class WorkflowState:
    """
    Mutable state passed through workflow.
    """
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    current_node: Optional[str] = None
    error: Optional[str] = None

    def get(self, key: str, default: Any = None) -> Any:
        """Get value from outputs, then inputs, then context."""
        if key in self.outputs:
            return self.outputs[key]
        if key in self.inputs:
            return self.inputs[key]
        return self.context.get(key, default)

    def set(self, key: str, value: Any):
        """Set value in outputs."""
        self.outputs[key] = value

    def add_to_history(self, node_id: str, result: Any, status: NodeStatus):
        """Add execution to history."""
        self.history.append({
            "node_id": node_id,
            "result": result,
            "status": status.value,
            "timestamp": datetime.now().isoformat()
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "inputs": self.inputs,
            "outputs": self.outputs,
            "context": self.context,
            "history": self.history,
            "current_node": self.current_node,
            "error": self.error
        }


@dataclass
class WorkflowNode:
    """
    Node in workflow graph.
    """
    id: str
    name: str
    type: str = "generic"
    handler: Optional[Callable] = None
    config: dict[str, Any] = field(default_factory=dict)
    status: NodeStatus = NodeStatus.PENDING
    result: Any = None

    def __hash__(self):
        return hash(self.id)


@dataclass
class WorkflowEdge:
    """
    Edge connecting workflow nodes.
    """
    source: str
    target: str
    edge_type: EdgeType = EdgeType.DEFAULT
    condition: Optional[Callable[[WorkflowState], bool]] = None

    def should_follow(self, state: WorkflowState) -> bool:
        """Check if this edge should be followed."""
        if self.edge_type == EdgeType.DEFAULT:
            return True
        if self.edge_type == EdgeType.CONDITIONAL and self.condition:
            return self.condition(state)
        return True


class Workflow:
    """
    DAG-based workflow for agent orchestration.

    Usage:
        workflow = Workflow("my_workflow")
        workflow.add_node(AgentNode("research", agent=research_agent))
        workflow.add_node(AgentNode("write", agent=writer_agent))
        workflow.add_edge("research", "write")

        result = await workflow.run({"topic": "AI"})
    """

    def __init__(self, name: str, description: str = ""):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.description = description
        self.nodes: dict[str, WorkflowNode] = {}
        self.edges: list[WorkflowEdge] = []
        self.entry_node: Optional[str] = None
        self.end_nodes: list[str] = []

    def add_node(self, node: WorkflowNode) -> 'Workflow':
        """Add a node to the workflow."""
        self.nodes[node.id] = node

        # First node is entry by default
        if self.entry_node is None:
            self.entry_node = node.id

        return self

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: EdgeType = EdgeType.DEFAULT,
        condition: Optional[Callable[[WorkflowState], bool]] = None
    ) -> 'Workflow':
        """Add an edge between nodes."""
        edge = WorkflowEdge(
            source=source,
            target=target,
            edge_type=edge_type,
            condition=condition
        )
        self.edges.append(edge)
        return self

    def set_entry(self, node_id: str) -> 'Workflow':
        """Set the entry node."""
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")
        self.entry_node = node_id
        return self

    def set_end(self, node_id: str) -> 'Workflow':
        """Mark a node as an end node."""
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")
        if node_id not in self.end_nodes:
            self.end_nodes.append(node_id)
        return self

    def get_next_nodes(self, node_id: str, state: WorkflowState) -> list[str]:
        """Get nodes that should execute after the given node."""
        next_nodes = []
        for edge in self.edges:
            if edge.source == node_id and edge.should_follow(state):
                next_nodes.append(edge.target)
        return next_nodes

    def get_node(self, node_id: str) -> Optional[WorkflowNode]:
        """Get a node by ID."""
        return self.nodes.get(node_id)

    def validate(self) -> list[str]:
        """Validate workflow. Returns list of errors."""
        errors = []

        if not self.entry_node:
            errors.append("No entry node defined")

        if self.entry_node and self.entry_node not in self.nodes:
            errors.append(f"Entry node {self.entry_node} not found")

        # Check all edges reference valid nodes
        for edge in self.edges:
            if edge.source not in self.nodes:
                errors.append(f"Edge source {edge.source} not found")
            if edge.target not in self.nodes:
                errors.append(f"Edge target {edge.target} not found")

        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "nodes": [
                {"id": n.id, "name": n.name, "type": n.type}
                for n in self.nodes.values()
            ],
            "edges": [
                {"source": e.source, "target": e.target, "type": e.edge_type.value}
                for e in self.edges
            ],
            "entry_node": self.entry_node,
            "end_nodes": self.end_nodes
        }

    def __repr__(self) -> str:
        return f"<Workflow(name='{self.name}', nodes={len(self.nodes)}, edges={len(self.edges)})>"
