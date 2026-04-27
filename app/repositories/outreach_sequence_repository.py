from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.core import OutreachSequence


class OutreachSequenceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, sequence: OutreachSequence) -> OutreachSequence:
        self.db.add(sequence)
        await self.db.commit()
        await self.db.refresh(sequence)
        return sequence

    async def get_by_id(self, sequence_id: str) -> Optional[OutreachSequence]:
        result = await self.db.execute(
            select(OutreachSequence).where(OutreachSequence.id == sequence_id)
        )
        return result.scalar_one_or_none()

    async def get_active_by_lead(self, lead_id: str) -> Optional[OutreachSequence]:
        result = await self.db.execute(
            select(OutreachSequence)
            .where(OutreachSequence.lead_id == lead_id, OutreachSequence.status == "active")
        )
        return result.scalar_one_or_none()

    async def update(self, sequence: OutreachSequence) -> OutreachSequence:
        sequence.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await self.db.commit()
        await self.db.refresh(sequence)
        return sequence

    async def list_active(self) -> list[OutreachSequence]:
        result = await self.db.execute(
            select(OutreachSequence).where(OutreachSequence.status == "active")
        )
        return list(result.scalars().all())
