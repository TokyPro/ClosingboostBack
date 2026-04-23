from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.core import ScoringConfig
from ..repositories.outreach_repository import OutreachRepository
from ..schemas.leads import (
    OutreachEventRequest,
    PipelineStats,
    ScoreEventSchema,
    ScoringConfigSchema,
    ScoringConfigUpdate,
)
from ..services.scoring_service import ScoringService

router = APIRouter()


@router.get("/config", response_model=ScoringConfigSchema)
async def get_scoring_config(db: AsyncSession = Depends(get_db)):
    repo = OutreachRepository(db)
    config = await repo.get_scoring_config()
    if not config:
        config = ScoringConfig()
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return config


@router.put("/config", response_model=ScoringConfigSchema)
async def update_scoring_config(
    data: ScoringConfigUpdate, db: AsyncSession = Depends(get_db)
):
    repo = OutreachRepository(db)
    config = await repo.create_or_update_config(data.model_dump(exclude_none=True))
    return config


@router.post("/score/{lead_id}")
async def score_lead(lead_id: str, db: AsyncSession = Depends(get_db)):
    svc = ScoringService(db)
    lead = await svc.score_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {
        "lead_id": lead_id,
        "score": lead.score,
        "tier": lead.tier,
        "fit_score": lead.fit_score,
        "intent_score": lead.intent_score,
    }


@router.post("/event/{lead_id}")
async def record_event(
    lead_id: str, data: OutreachEventRequest, db: AsyncSession = Depends(get_db)
):
    svc = ScoringService(db)
    lead = await svc.apply_event(lead_id, data.event_type, data.metadata)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {
        "lead_id": lead_id,
        "score": lead.score,
        "tier": lead.tier,
        "event": data.event_type,
    }


@router.get("/pipeline/stats", response_model=PipelineStats)
async def get_pipeline_stats(db: AsyncSession = Depends(get_db)):
    svc = ScoringService(db)
    return await svc.get_pipeline_stats()


@router.post("/cooldown")
async def run_cooldown(db: AsyncSession = Depends(get_db)):
    svc = ScoringService(db)
    degraded = await svc.run_hot_cooldown()
    return {"degraded_count": len(degraded), "lead_ids": degraded}


@router.get("/events/{lead_id}", response_model=list[ScoreEventSchema])
async def get_score_events(lead_id: str, db: AsyncSession = Depends(get_db)):
    repo = OutreachRepository(db)
    events = await repo.get_score_events_by_lead(lead_id)
    return events
