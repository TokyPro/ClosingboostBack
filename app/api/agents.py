from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..repositories.outreach_repository import OutreachRepository
from ..schemas.leads import OutreachMessageSchema
from ..services.agent_service import AgentService
from ..services.ai_service import AIIntelligenceService

router = APIRouter()


def get_agent_service(db: AsyncSession = Depends(get_db)) -> AgentService:
    ai_service = AIIntelligenceService()
    return AgentService(db, ai_service)


@router.post("/run/{lead_id}")
async def run_agent(
    lead_id: str, svc: AgentService = Depends(get_agent_service)
):
    result = await svc.run_agent(lead_id)
    if not result:
        raise HTTPException(status_code=404, detail="Lead not found")
    return result


@router.get("/recommendation/{lead_id}")
async def get_recommendation(
    lead_id: str, svc: AgentService = Depends(get_agent_service)
):
    result = await svc.get_recommendation(lead_id)
    if not result:
        raise HTTPException(status_code=404, detail="Lead not found")
    return result


@router.get("/messages/{lead_id}", response_model=list[OutreachMessageSchema])
async def get_outreach_messages(
    lead_id: str, db: AsyncSession = Depends(get_db)
):
    repo = OutreachRepository(db)
    msgs = await repo.get_messages_by_lead(lead_id)
    return msgs


@router.put("/messages/{message_id}/status")
async def update_message_status(
    message_id: str, status: str, db: AsyncSession = Depends(get_db)
):
    repo = OutreachRepository(db)
    now_field = {
        "sent": "sent_at",
        "opened": "opened_at",
        "clicked": "clicked_at",
        "replied": "replied_at",
    }
    timestamps: dict = {}
    if status in now_field:
        timestamps[now_field[status]] = datetime.datetime.now(datetime.timezone.utc)
    msg = await repo.update_message_status(message_id, status, **timestamps)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"id": msg.id, "status": msg.status}
