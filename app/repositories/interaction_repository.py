from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from uuid import UUID
from typing import List, Optional
from ..models.core import Interaction

class InteractionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_by_opportunity(self, opportunity_id: UUID) -> List[Interaction]:
        query = select(Interaction).where(Interaction.opportunity_id == str(opportunity_id))
        query = query.order_by(Interaction.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, interaction_id: UUID) -> Optional[Interaction]:
        query = select(Interaction).where(Interaction.id == str(interaction_id))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create(self, interaction: Interaction) -> Interaction:
        self.db.add(interaction)
        await self.db.commit()
        await self.db.refresh(interaction)
        return interaction

    async def update(self, interaction: Interaction) -> Interaction:
        await self.db.commit()
        await self.db.refresh(interaction)
        return interaction

    async def delete(self, interaction: Interaction) -> None:
        await self.db.delete(interaction)
        await self.db.commit()
