from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.core import OutreachMessage, ScoreEvent, ScoringConfig


class OutreachRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_message(self, msg: OutreachMessage) -> OutreachMessage:
        self.db.add(msg)
        await self.db.commit()
        await self.db.refresh(msg)
        return msg

    async def get_messages_by_lead(self, lead_id: str) -> list[OutreachMessage]:
        result = await self.db.execute(
            select(OutreachMessage)
            .where(OutreachMessage.lead_id == lead_id)
            .order_by(OutreachMessage.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_message_status(
        self, msg_id: str, status: str, **timestamps
    ) -> Optional[OutreachMessage]:
        result = await self.db.execute(
            select(OutreachMessage).where(OutreachMessage.id == msg_id)
        )
        msg = result.scalar_one_or_none()
        if not msg:
            return None
        msg.status = status
        for k, v in timestamps.items():
            setattr(msg, k, v)
        await self.db.commit()
        await self.db.refresh(msg)
        return msg

    async def get_message_by_id(self, msg_id: str) -> Optional[OutreachMessage]:
        result = await self.db.execute(
            select(OutreachMessage).where(OutreachMessage.id == msg_id)
        )
        return result.scalar_one_or_none()

    async def create_score_event(self, event: ScoreEvent) -> ScoreEvent:
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def get_score_events_by_lead(
        self, lead_id: str, limit: int = 20
    ) -> list[ScoreEvent]:
        result = await self.db.execute(
            select(ScoreEvent)
            .where(ScoreEvent.lead_id == lead_id)
            .order_by(ScoreEvent.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_scoring_config(self) -> Optional[ScoringConfig]:
        result = await self.db.execute(select(ScoringConfig).limit(1))
        return result.scalar_one_or_none()

    async def create_or_update_config(self, updates: dict) -> ScoringConfig:
        config = await self.get_scoring_config()
        if not config:
            config = ScoringConfig(**updates)
            self.db.add(config)
        else:
            for k, v in updates.items():
                if v is not None:
                    setattr(config, k, v)
            config.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await self.db.commit()
        await self.db.refresh(config)
        return config
