import asyncio
import sys
import os

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import engine
from sqlalchemy import text
from app.models.core import Lead, OutreachSequence, OutreachMessage
from app.repositories.lead_repository import LeadRepository
from app.repositories.outreach_sequence_repository import OutreachSequenceRepository
from app.services.agent_service import AgentService
from app.services.ai_service import AIIntelligenceService
from app.services.sequence_service import SequenceService
from app.database import AsyncSessionLocal

async def test_sequence():
    async with AsyncSessionLocal() as db:
        lead_repo = LeadRepository(db)
        # Get a lead
        leads = await lead_repo.get_all(limit=1)
        if not leads:
            print("No leads found to test.")
            return
        
        lead = leads[0]
        print(f"Testing sequence for lead: {lead.company_name} (ID: {lead.id})")
        
        ai_service = AIIntelligenceService()
        agent_service = AgentService(db, ai_service)
        sequence_service = SequenceService(db, agent_service)
        
        # Start sequence
        sequence = await sequence_service.start_sequence(lead.id)
        if sequence:
            print(f"Sequence started: {sequence.id}, current step: {sequence.current_step}")
            
            # Check if a message was generated
            from app.repositories.outreach_repository import OutreachRepository
            outreach_repo = OutreachRepository(db)
            messages = await outreach_repo.get_messages_by_lead(lead.id)
            print(f"Messages found for lead: {len(messages)}")
            for msg in messages:
                print(f"- Message ID: {msg.id}, Tier: {msg.tier}, Sequence ID: {msg.sequence_id}")
        else:
            print("Failed to start sequence.")

async def main():
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = [row[0] for row in res.fetchall()]
        print(f"Tables in DB: {tables}")
        
    await test_sequence()

if __name__ == "__main__":
    asyncio.run(main())
