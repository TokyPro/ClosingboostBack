import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.core import OutreachSequence, OutreachMessage
from ..repositories.outreach_sequence_repository import OutreachSequenceRepository
from ..repositories.lead_repository import LeadRepository
from .agent_service import AgentService

logger = logging.getLogger(__name__)

class SequenceService:
    def __init__(self, db: AsyncSession, agent_service: AgentService):
        self.db = db
        self.sequence_repo = OutreachSequenceRepository(db)
        self.lead_repo = LeadRepository(db)
        self.agent_service = agent_service

    async def start_sequence(self, lead_id: str, total_steps: int = 3) -> Optional[OutreachSequence]:
        """Starts a new outreach sequence for a lead."""
        lead = await self.lead_repo.get_by_id(lead_id)
        if not lead:
            logger.error(f"Lead {lead_id} not found.")
            return None

        # Check if an active sequence already exists
        existing = await self.sequence_repo.get_active_by_lead(lead_id)
        if existing:
            logger.warning(f"Active sequence already exists for lead {lead_id}.")
            return existing

        sequence = OutreachSequence(
            lead_id=lead_id,
            total_steps=total_steps,
            current_step=1,
            status="active"
        )
        sequence = await self.sequence_repo.create(sequence)
        
        # Trigger the first step immediately (generate message)
        await self.process_next_step(sequence.id)
        
        return sequence

    async def process_next_step(self, sequence_id: str) -> bool:
        """Generates the message for the current step of the sequence."""
        sequence = await self.sequence_repo.get_by_id(sequence_id)
        if not sequence or sequence.status != "active":
            return False

        lead_id = sequence.lead_id
        
        # Use AgentService to generate a personalized message
        # We pass the sequence_id so it's linked correctly
        agent_result = await self.agent_service.run_agent(lead_id, sequence_id=sequence.id)
        
        return agent_result is not None and "message_id" in agent_result

    async def advance_sequence(self, sequence_id: str) -> Optional[OutreachSequence]:
        """Advances the sequence to the next step."""
        sequence = await self.sequence_repo.get_by_id(sequence_id)
        if not sequence or sequence.status != "active":
            return None

        if sequence.current_step < sequence.total_steps:
            sequence.current_step += 1
            await self.sequence_repo.update(sequence)
            await self.process_next_step(sequence.id)
        else:
            sequence.status = "completed"
            await self.sequence_repo.update(sequence)
            
        return sequence
