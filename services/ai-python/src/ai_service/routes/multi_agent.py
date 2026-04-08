"""Multi-agent coordination routes.

Migrated from:
  - src/agent_framework/platform/multi_agent.py
  - src/agent_framework/platform/multi_agent_impl.py

Owns agent team creation, message routing between agents,
and collaborative task orchestration.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["multi-agent"])


class AgentSpec(BaseModel):
    name: str
    role: str = "assistant"
    model: str | None = None
    system_prompt: str | None = None
    tools: list[str] = Field(default_factory=list)


class TeamCreateRequest(BaseModel):
    team_name: str
    agents: list[AgentSpec]
    routing_strategy: str = "round_robin"


class TeamCreateResponse(BaseModel):
    success: bool = True
    team_id: str = ""
    agents: list[str] = Field(default_factory=list)


@router.post("/multi-agent/teams", response_model=TeamCreateResponse)
async def create_team(req: TeamCreateRequest):
    """Create a multi-agent team with specified agents and routing."""
    return TeamCreateResponse(
        team_id="team_scaffold",
        agents=[a.name for a in req.agents],
    )


class TeamMessageRequest(BaseModel):
    team_id: str
    message: str
    target_agent: str | None = None


class TeamMessageResponse(BaseModel):
    success: bool = True
    responses: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/multi-agent/chat", response_model=TeamMessageResponse)
async def team_chat(req: TeamMessageRequest):
    """Send a message to a multi-agent team."""
    return TeamMessageResponse(
        responses=[
            {
                "agent": "scaffold",
                "message": "[ai-python scaffold] multi-agent not yet migrated",
            }
        ],
    )


@router.get("/multi-agent/teams")
async def list_teams():
    """List active agent teams."""
    return {"success": True, "teams": []}


@router.get("/multi-agent/teams/{team_id}")
async def get_team(team_id: str):
    """Get details of an agent team."""
    return {"success": False, "error": "team not found"}
