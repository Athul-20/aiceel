from typing import Optional

from pydantic import BaseModel, Field


class SubTask(BaseModel):
    sub_query: str = Field(..., description="The specific sub-task or query text")
    agent: str = Field(..., description="The name of the agent assigned to this task")

class CollaborationPlan(BaseModel):
    tasks: list[SubTask] = Field(..., description="List of sub-tasks for collaboration")

class RoutingDecision(BaseModel):
    agent: str = Field(..., description="The name of the selected agent")
    rationale: Optional[str] = Field(None, description="Brief explanation for the selection")
