from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List, Optional
from ..repositories.interaction_repository import InteractionRepository
from ..models.core import Interaction
from ..schemas.core import InteractionCreate

class InteractionService:
    def __init__(self, db: AsyncSession):
        self.repository = InteractionRepository(db)

    async def get_interactions_by_opportunity(self, opportunity_id: UUID) -> List[Interaction]:
        return await self.repository.get_all_by_opportunity(opportunity_id)

    async def get_interaction(self, interaction_id: UUID) -> Optional[Interaction]:
        return await self.repository.get_by_id(interaction_id)

    async def create_interaction(self, interaction_in: InteractionCreate) -> Interaction:
        interaction = Interaction(
            opportunity_id=str(interaction_in.opportunity_id),
            type=interaction_in.type,
            summary=interaction_in.summary,
            raw_transcript=interaction_in.raw_transcript,
            requirements=interaction_in.requirements
        )
        return await self.repository.create(interaction)

    async def delete_interaction(self, interaction_id: UUID) -> bool:
        interaction = await self.repository.get_by_id(interaction_id)
        if not interaction:
            return False
        await self.repository.delete(interaction)
        return True
