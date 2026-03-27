# aiccel/workflows/executor.py
"""
Workflow Executor
==================

Executes workflow graphs with support for:
- Async execution
- Parallel branches
- Checkpointing
- Error recovery
"""

import asyncio
import time
from typing import Any, Optional

from ..logging_config import get_logger
from .graph import NodeStatus, Workflow, WorkflowState


logger = get_logger("workflow")


class WorkflowExecutor:
    """
    Executes workflow graphs.

    Features:
    - Async-first execution
    - Parallel branch support
    - Checkpointing for recovery
    - Detailed execution logs

    Usage:
        executor = WorkflowExecutor()
        result = await executor.run(workflow, {"query": "Research AI"})
    """

    def __init__(
        self,
        max_iterations: int = 100,
        timeout: float = 300.0,
        checkpoint_enabled: bool = False
    ):
        self.max_iterations = max_iterations
        self.timeout = timeout
        self.checkpoint_enabled = checkpoint_enabled
        self._checkpoints: dict[str, WorkflowState] = {}

    async def run(
        self,
        workflow: Workflow,
        inputs: dict[str, Any],
        resume_from: Optional[str] = None
    ) -> WorkflowState:
        """
        Execute a workflow.

        Args:
            workflow: Workflow to execute
            inputs: Input data
            resume_from: Node ID to resume from (if checkpointed)

        Returns:
            Final workflow state
        """
        # Validate workflow
        errors = workflow.validate()
        if errors:
            raise ValueError(f"Invalid workflow: {errors}")

        # Initialize state
        state = WorkflowState(inputs=inputs)

        # Resume from checkpoint if specified
        if resume_from and resume_from in self._checkpoints:
            state = self._checkpoints[resume_from]
            logger.info(f"Resuming workflow from checkpoint: {resume_from}")

        start_time = time.perf_counter()
        iterations = 0
        current_nodes = [workflow.entry_node]

        logger.info(f"Starting workflow: {workflow.name}")

        try:
            while current_nodes and iterations < self.max_iterations:
                iterations += 1

                # Check timeout
                if time.perf_counter() - start_time > self.timeout:
                    state.error = "Workflow timeout"
                    logger.error("Workflow timed out")
                    break

                # Execute current nodes (potentially in parallel)
                next_nodes = []

                if len(current_nodes) == 1:
                    # Single node - execute directly
                    node_id = current_nodes[0]
                    result = await self._execute_node(workflow, node_id, state)

                    if result:
                        next_nodes.extend(workflow.get_next_nodes(node_id, state))
                else:
                    # Multiple nodes - execute in parallel
                    tasks = [
                        self._execute_node(workflow, node_id, state)
                        for node_id in current_nodes
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for node_id, result in zip(current_nodes, results):
                        if result and not isinstance(result, Exception):
                            next_nodes.extend(workflow.get_next_nodes(node_id, state))

                # Remove duplicates and check for end
                current_nodes = list(set(next_nodes))

                # Check if we've reached end nodes
                if any(node in workflow.end_nodes for node in current_nodes):
                    for end_node in [n for n in current_nodes if n in workflow.end_nodes]:
                        await self._execute_node(workflow, end_node, state)
                    break

            execution_time = (time.perf_counter() - start_time) * 1000
            logger.info(f"Workflow completed in {execution_time:.0f}ms ({iterations} iterations)")

            return state

        except Exception as e:
            state.error = str(e)
            logger.error(f"Workflow failed: {e}")
            raise

    async def _execute_node(
        self,
        workflow: Workflow,
        node_id: str,
        state: WorkflowState
    ) -> bool:
        """Execute a single node."""
        node = workflow.get_node(node_id)
        if not node:
            logger.warning(f"Node not found: {node_id}")
            return False

        state.current_node = node_id
        node.status = NodeStatus.RUNNING

        start_time = time.perf_counter()

        try:
            # Execute node
            if hasattr(node, 'execute'):
                result = await node.execute(state)
            elif node.handler:
                if asyncio.iscoroutinefunction(node.handler):
                    result = await node.handler(state)
                else:
                    result = node.handler(state)
            else:
                result = None

            node.status = NodeStatus.SUCCESS
            node.result = result

            # Log execution
            duration = (time.perf_counter() - start_time) * 1000
            state.add_to_history(node_id, result, NodeStatus.SUCCESS)
            logger.debug(f"Node {node_id} completed in {duration:.0f}ms")

            # Checkpoint
            if self.checkpoint_enabled:
                self._checkpoints[node_id] = WorkflowState(
                    inputs=state.inputs.copy(),
                    outputs=state.outputs.copy(),
                    context=state.context.copy(),
                    history=state.history.copy()
                )

            return True

        except Exception as e:
            node.status = NodeStatus.FAILED
            state.add_to_history(node_id, str(e), NodeStatus.FAILED)
            logger.error(f"Node {node_id} failed: {e}")
            raise

    def run_sync(
        self,
        workflow: Workflow,
        inputs: dict[str, Any]
    ) -> WorkflowState:
        """Run workflow synchronously."""
        return asyncio.run(self.run(workflow, inputs))

    def get_checkpoint(self, node_id: str) -> Optional[WorkflowState]:
        """Get checkpoint state for a node."""
        return self._checkpoints.get(node_id)

    def clear_checkpoints(self):
        """Clear all checkpoints."""
        self._checkpoints.clear()
