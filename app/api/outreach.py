from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from ..database import get_db
from ..services.sequence_service import SequenceService
from ..services.agent_service import AgentService
from ..services.ai_service import AIIntelligenceService
from ..schemas.leads import OutreachMessageSchema # We'll need a SequenceSchema too

router = APIRouter()

# --- Dependency Functions ---

async def get_agent_service(db: AsyncSession = Depends(get_db)) -> AgentService:
    ai_service = AIIntelligenceService()
    return AgentService(db=db, ai_service=ai_service)

async def get_sequence_service(
    db: AsyncSession = Depends(get_db),
    agent_service: AgentService = Depends(get_agent_service)
) -> SequenceService:
    return SequenceService(db, agent_service)

# --- API Endpoints ---

@router.post("/sequences/start/{lead_id}", status_code=201)
async def start_sequence(
    lead_id: str,
    total_steps: int = 3,
    service: SequenceService = Depends(get_sequence_service)
):
    """Starts an outreach sequence for a lead."""
    sequence = await service.start_sequence(lead_id, total_steps)
    if not sequence:
        raise HTTPException(status_code=400, detail="Could not start sequence. Maybe an active one already exists.")
    
    return {
        "sequence_id": sequence.id,
        "lead_id": sequence.lead_id,
        "status": sequence.status,
        "current_step": sequence.current_step,
        "total_steps": sequence.total_steps
    }

@router.post("/sequences/advance/{sequence_id}")
async def advance_sequence(
    sequence_id: str,
    service: SequenceService = Depends(get_sequence_service)
):
    """Manually advances a sequence to the next step."""
    sequence = await service.advance_sequence(sequence_id)
    if not sequence:
        raise HTTPException(status_code=404, detail="Sequence not found or not active.")
    
    return {
        "sequence_id": sequence.id,
        "status": sequence.status,
        "current_step": sequence.current_step
    }
