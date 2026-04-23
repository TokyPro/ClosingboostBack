from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from uuid import UUID
from typing import Optional, List
from ..models.core import Briefing

class BriefingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_opportunity_id(self, opportunity_id: UUID) -> Optional[Briefing]:
        query = select(Briefing).where(Briefing.opportunity_id == str(opportunity_id))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create(self, briefing: Briefing) -> Briefing:
        self.db.add(briefing)
        await self.db.commit()
        await self.db.refresh(briefing)
        return briefing

    async def update(self, briefing: Briefing) -> Briefing:
        await self.db.commit()
        await self.db.refresh(briefing)
        return briefing
