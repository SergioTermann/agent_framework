"""RLHF training and feedback routes.

Migrated from: src/agent_framework/reasoning/llm_rlhf_engine.py

Manages reward model training, preference data collection,
and reinforcement learning from human feedback loops.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["rlhf"])


class PreferenceRecord(BaseModel):
    prompt: str
    chosen: str
    rejected: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrainRequest(BaseModel):
    dataset_id: str | None = None
    preferences: list[PreferenceRecord] = Field(default_factory=list)
    epochs: int = 3
    learning_rate: float = 1e-5
    batch_size: int = 4


@router.post("/rlhf/train")
async def start_training(req: TrainRequest):
    """Start RLHF training run."""
    return {
        "success": True,
        "job_id": "rlhf_scaffold",
        "status": "queued",
        "epochs": req.epochs,
        "message": "[model-python scaffold] RLHF training not yet migrated",
    }


@router.get("/rlhf/jobs")
async def list_training_jobs():
    """List RLHF training jobs."""
    return {"success": True, "jobs": []}


@router.get("/rlhf/jobs/{job_id}")
async def get_training_job(job_id: str):
    """Get status of an RLHF training job."""
    return {"success": False, "error": "job not found"}


@router.post("/rlhf/preferences")
async def submit_preferences(records: list[PreferenceRecord]):
    """Submit human preference data for RLHF."""
    return {
        "success": True,
        "recorded": len(records),
    }
