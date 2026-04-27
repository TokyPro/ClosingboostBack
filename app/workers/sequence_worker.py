import asyncio
import logging
import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import AsyncSessionLocal
from ..models.core import OutreachSequence, OutreachMessage, Lead
from ..services.sequence_service import SequenceService
from ..services.agent_service import AgentService
from ..services.ai_service import AIIntelligenceService
from ..repositories.outreach_sequence_repository import OutreachSequenceRepository
from ..repositories.outreach_repository import OutreachRepository

logger = logging.getLogger(__name__)

class SequenceWorker:
    def __init__(self):
        self.ai_service = AIIntelligenceService()

    async def run_forever(self):
        """Main loop for the background worker."""
        logger.info("SequenceWorker started.")
        while True:
            try:
                await self.process_pending_sequences()
            except Exception as e:
                logger.error(f"Error in SequenceWorker loop: {e}", exc_info=True)
            
            # Sleep for 1 hour between checks
            # In a real production app, this would be a cron job or a more sophisticated scheduler
            await asyncio.sleep(3600)

    async def process_pending_sequences(self):
        """Checks and advances sequences that are ready for the next step."""
        async with AsyncSessionLocal() as db:
            sequence_repo = OutreachSequenceRepository(db)
            outreach_repo = OutreachRepository(db)
            agent_service = AgentService(db, self.ai_service)
            sequence_service = SequenceService(db, agent_service)
            
            active_sequences = await sequence_repo.list_active()
            logger.info(f"Checking {len(active_sequences)} active sequences.")
            
            for sequence in active_sequences:
                # Logic: If the last message was sent > 3 days ago, advance
                last_msg = await self.get_last_sent_message(db, sequence.id)
                
                if last_msg and last_msg.sent_at:
                    now = datetime.datetime.now(datetime.timezone.utc)
                    # Convert last_msg.sent_at to UTC if it's naive
                    sent_at = last_msg.sent_at
                    if sent_at.tzinfo is None:
                        sent_at = sent_at.replace(tzinfo=datetime.timezone.utc)
                        
                    diff = now - sent_at
                    
                    # Target: 3 days between steps (72 hours)
                    if diff.total_seconds() >= (3 * 24 * 3600):
                        logger.info(f"Advancing sequence {sequence.id} for lead {sequence.lead_id}")
                        await sequence_service.advance_sequence(sequence.id)
                elif not last_msg and sequence.current_step == 1:
                    # If no message yet but sequence is active at step 1, 
                    # it means it was just started or needs its first generation.
                    # start_sequence already does this, but good for robustness.
                    await sequence_service.process_next_step(sequence.id)

    async def get_last_sent_message(self, db: AsyncSession, sequence_id: str) -> Optional[OutreachMessage]:
        result = await db.execute(
            select(OutreachMessage)
            .where(OutreachMessage.sequence_id == sequence_id, OutreachMessage.status == "sent")
            .order_by(OutreachMessage.sent_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

# Example of how to start this worker in main.py or a separate entry point
async def start_worker():
    worker = SequenceWorker()
    await worker.run_forever()
