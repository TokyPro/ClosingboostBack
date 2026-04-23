from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.core import Lead


class LeadRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, lead: Lead) -> Lead:
        self.db.add(lead)
        await self.db.commit()
        await self.db.refresh(lead)
        return lead

    async def get_by_id(self, lead_id: str) -> Optional[Lead]:
        result = await self.db.execute(select(Lead).where(Lead.id == lead_id))
        return result.scalar_one_or_none()

    async def get_by_linkedin_url(self, url: str) -> Optional[Lead]:
        result = await self.db.execute(select(Lead).where(Lead.linkedin_url == url))
        return result.scalar_one_or_none()

    async def get_by_notion_id(self, notion_id: str) -> Optional[Lead]:
        result = await self.db.execute(select(Lead).where(Lead.notion_id == notion_id))
        return result.scalar_one_or_none()

    async def get_by_airtable_id(self, airtable_id: str) -> Optional[Lead]:
        result = await self.db.execute(select(Lead).where(Lead.airtable_id == airtable_id))
        return result.scalar_one_or_none()

    async def get_all(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Lead]:
        query = select(Lead)
        if status:
            query = query.where(Lead.status == status)
        query = query.order_by(Lead.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count(self, status: Optional[str] = None) -> int:
        query = select(func.count(Lead.id))
        if status:
            query = query.where(Lead.status == status)
        result = await self.db.execute(query)
        return result.scalar_one()

    async def update(self, lead: Lead) -> Lead:
        lead.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await self.db.commit()
        await self.db.refresh(lead)
        return lead

    async def delete(self, lead_id: str) -> bool:
        lead = await self.get_by_id(lead_id)
        if not lead:
            return False
        await self.db.delete(lead)
        await self.db.commit()
        return True

    async def get_by_tier(self, tier: str) -> list[Lead]:
        result = await self.db.execute(
            select(Lead).where(Lead.tier == tier).order_by(Lead.score.desc())
        )
        return list(result.scalars().all())

    async def count_by_tier(self, tier: str) -> int:
        result = await self.db.execute(
            select(func.count(Lead.id)).where(Lead.tier == tier)
        )
        return result.scalar_one()

    async def get_hot_with_max_attempts(self, max_attempts: int) -> list[Lead]:
        """Hot leads that exceeded max outreach attempts — candidates for cooldown."""
        result = await self.db.execute(
            select(Lead).where(Lead.tier == "hot", Lead.outreach_attempts >= max_attempts)
        )
        return list(result.scalars().all())
