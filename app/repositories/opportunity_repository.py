from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from uuid import UUID
from typing import List, Optional
from ..models.core import Opportunity

class OpportunityRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all(self, owner_id: Optional[UUID] = None) -> List[Opportunity]:
        stmt = select(Opportunity)
        if owner_id:
            stmt = stmt.filter(Opportunity.owner_id == str(owner_id))
        stmt = stmt.order_by(Opportunity.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, opportunity_id: UUID) -> Optional[Opportunity]:
        stmt = select(Opportunity).where(Opportunity.id == str(opportunity_id))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, opportunity: Opportunity) -> Opportunity:
        self.db.add(opportunity)
        return opportunity

    async def update(self, opportunity: Opportunity) -> Opportunity:
        # State is already modified on the object, no action needed for ORM
        return opportunity

    async def delete(self, opportunity_id: UUID) -> bool:
        opp = await self.get_by_id(opportunity_id)
        if not opp:
            return False
        await self.db.delete(opp)
        return True

    async def search(self, owner_id: UUID, query: str) -> List[Opportunity]:
        stmt = (
            select(Opportunity)
            .where(
                Opportunity.owner_id == str(owner_id),
                or_(
                    Opportunity.title.ilike(f"%{query}%"),
                    Opportunity.company_name.ilike(f"%{query}%"),
                ),
            )
            .order_by(Opportunity.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
