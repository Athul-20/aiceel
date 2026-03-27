# aiccel/integrations/fastapi_routes.py
"""
FastAPI Integration
====================

Ready-to-use FastAPI routes for AICCEL agents.
"""

from typing import TYPE_CHECKING, Any, Optional


if TYPE_CHECKING:
    from ..agent import Agent
    from ..manager import AgentManager


def create_agent_routes(
    agent: 'Agent' = None,
    manager: 'AgentManager' = None,
    prefix: str = "/api/agent"
):
    """
    Create FastAPI router for agent endpoints.

    Usage:
        from fastapi import FastAPI
        from aiccel import SlimAgent
        from aiccel.integrations import create_agent_routes

        agent = SlimAgent(provider=...)
        router = create_agent_routes(agent=agent)

        app = FastAPI()
        app.include_router(router)

    Endpoints:
        POST /api/agent/run - Run agent
        POST /api/agent/stream - Stream response
        GET /api/agent/health - Health check
    """
    try:
        from fastapi import APIRouter, HTTPException
        from fastapi.responses import StreamingResponse
        from pydantic import BaseModel
    except ImportError:
        raise ImportError("fastapi and pydantic required: pip install fastapi pydantic")

    router = APIRouter(prefix=prefix, tags=["agent"])

    class RunRequest(BaseModel):
        query: str
        context: Optional[dict[str, Any]] = None

    class RunResponse(BaseModel):
        response: str
        thinking: Optional[str] = None
        tools_used: list[Any] = []
        execution_time: float = 0.0

    @router.post("/run", response_model=RunResponse)
    async def run_agent(request: RunRequest):
        """Run agent with query."""
        try:
            if agent:
                result = await agent.run_async(request.query)
            elif manager:
                result = await manager.run_async(request.query)
            else:
                raise HTTPException(500, "No agent configured")

            return RunResponse(
                response=result.get("response", ""),
                thinking=result.get("thinking"),
                tools_used=result.get("tools_used", []),
                execution_time=result.get("execution_time", 0.0)
            )
        except Exception as e:
            raise HTTPException(500, str(e))

    @router.post("/stream")
    async def stream_agent(request: RunRequest):
        """Stream agent response."""
        if not agent:
            raise HTTPException(500, "No agent configured")

        async def generate():
            async for chunk in agent.stream(request.query):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream"
        )

    @router.get("/health")
    async def health():
        """Health check."""
        return {
            "status": "healthy",
            "agent": agent.config.name if agent else None,
            "manager": manager is not None
        }

    @router.get("/info")
    async def agent_info():
        """Get agent information."""
        if agent:
            return {
                "name": agent.config.name,
                "description": agent.config.description,
                "tools": [t.name for t in agent.tools],
                "memory_type": agent.config.memory_type
            }
        elif manager:
            return {
                "agents": [a.name for a in manager.agents.values()],
                "strategy": getattr(manager, 'strategy', 'unknown')
            }
        return {}

    @router.delete("/memory")
    async def clear_memory():
        """Clear agent memory."""
        if agent:
            agent.clear_memory()
            return {"status": "cleared"}
        raise HTTPException(400, "No agent with memory")

    return router


def create_workflow_routes(
    workflow,
    executor=None,
    prefix: str = "/api/workflow"
):
    """
    Create FastAPI router for workflow endpoints.

    Usage:
        router = create_workflow_routes(my_workflow)
        app.include_router(router)
    """
    try:
        from fastapi import APIRouter, HTTPException
        from pydantic import BaseModel
    except ImportError:
        raise ImportError("fastapi and pydantic required")

    from ..workflows import WorkflowExecutor

    router = APIRouter(prefix=prefix, tags=["workflow"])
    _executor = executor or WorkflowExecutor()

    class WorkflowRequest(BaseModel):
        inputs: dict[str, Any]

    @router.post("/run")
    async def run_workflow(request: WorkflowRequest):
        """Run workflow with inputs."""
        try:
            state = await _executor.run(workflow, request.inputs)
            return state.to_dict()
        except Exception as e:
            raise HTTPException(500, str(e))

    @router.get("/info")
    async def workflow_info():
        """Get workflow information."""
        return workflow.to_dict()

    return router
