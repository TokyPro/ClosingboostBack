from __future__ import annotations

import datetime
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.core import Lead, ScoreEvent, ScoringConfig
from ..repositories.lead_repository import LeadRepository
from ..repositories.outreach_repository import OutreachRepository

logger = logging.getLogger(__name__)


class ScoringService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.lead_repo = LeadRepository(db)
        self.outreach_repo = OutreachRepository(db)

    async def _get_config(self) -> ScoringConfig:
        config = await self.outreach_repo.get_scoring_config()
        if not config:
            # SQLAlchemy Column defaults are only applied on INSERT, not on Python init.
            # Create a transient instance with explicit defaults.
            return ScoringConfig(
                warm_threshold=30.0,
                hot_threshold=70.0,
                fit_weight=0.4,
                intent_weight=0.6,
                click_score_boost=20.0,
                linkedin_boost=25.0,
                reply_score_boost=30.0,
                webinar_score_boost=40.0,
                meeting_score_boost=50.0,
                max_hot_attempts=3,
                cooldown_score_penalty=30.0,
            )
        return config

    def _compute_score(
        self, fit: float, intent: float, fit_w: float, intent_w: float
    ) -> float:
        return round(min(100.0, max(0.0, fit * fit_w + intent * intent_w)), 2)

    def _assign_tier(
        self, score: float, warm_threshold: float, hot_threshold: float
    ) -> str:
        if score >= hot_threshold:
            return "hot"
        if score >= warm_threshold:
            return "warm"
        return "cold"

    async def score_lead(self, lead_id: str) -> Optional[Lead]:
        lead = await self.lead_repo.get_by_id(lead_id)
        if not lead:
            return None
        config = await self._get_config()

        fit = lead.fit_score if lead.fit_score else lead.relevance_score * 100
        intent = lead.intent_score if lead.intent_score else 10.0

        score_before = lead.score
        new_score = self._compute_score(fit, intent, config.fit_weight, config.intent_weight)
        new_tier = self._assign_tier(new_score, config.warm_threshold, config.hot_threshold)

        lead.fit_score = round(fit, 2)
        lead.score = new_score
        lead.tier = new_tier
        lead.score_updated_at = datetime.datetime.now(datetime.timezone.utc)

        await self.lead_repo.update(lead)

        event = ScoreEvent(
            lead_id=lead.id,
            event_type="scored",
            score_delta=round(new_score - score_before, 2),
            score_before=score_before,
            score_after=new_score,
            event_metadata={"tier": new_tier},
        )
        await self.outreach_repo.create_score_event(event)
        return lead

    async def apply_event(
        self, lead_id: str, event_type: str, metadata: Optional[dict] = None
    ) -> Optional[Lead]:
        """Apply score boost based on engagement event."""
        lead = await self.lead_repo.get_by_id(lead_id)
        if not lead:
            return None
        config = await self._get_config()

        boost_map = {
            "link_clicked": config.click_score_boost,
            "linkedin_interaction": config.linkedin_boost,
            "email_replied": config.reply_score_boost,
            "webinar_registered": config.webinar_score_boost,
            "meeting_booked": config.meeting_score_boost,
        }
        boost = boost_map.get(event_type, 0.0)
        if boost == 0.0:
            return lead

        score_before = lead.score
        lead.intent_score = min(100.0, (lead.intent_score or 10.0) + boost)
        new_score = self._compute_score(
            lead.fit_score, lead.intent_score, config.fit_weight, config.intent_weight
        )
        new_tier = self._assign_tier(new_score, config.warm_threshold, config.hot_threshold)

        lead.score = new_score
        lead.tier = new_tier
        lead.score_updated_at = datetime.datetime.now(datetime.timezone.utc)
        await self.lead_repo.update(lead)

        event = ScoreEvent(
            lead_id=lead_id,
            event_type=event_type,
            score_delta=round(new_score - score_before, 2),
            score_before=score_before,
            score_after=new_score,
            event_metadata=metadata,
        )
        await self.outreach_repo.create_score_event(event)
        return lead

    async def run_hot_cooldown(self) -> list[str]:
        """Degrade hot leads that exceeded max outreach attempts back to warm."""
        config = await self._get_config()
        candidates = await self.lead_repo.get_hot_with_max_attempts(config.max_hot_attempts)
        degraded_ids: list[str] = []
        for lead in candidates:
            score_before = lead.score
            lead.score = max(0.0, lead.score - config.cooldown_score_penalty)
            lead.tier = self._assign_tier(
                lead.score, config.warm_threshold, config.hot_threshold
            )
            lead.score_updated_at = datetime.datetime.now(datetime.timezone.utc)
            await self.lead_repo.update(lead)
            event = ScoreEvent(
                lead_id=lead.id,
                event_type="hot_timeout",
                score_delta=-config.cooldown_score_penalty,
                score_before=score_before,
                score_after=lead.score,
                event_metadata={"reason": "max_attempts_exceeded"},
            )
            await self.outreach_repo.create_score_event(event)
            degraded_ids.append(lead.id)
        return degraded_ids

    async def get_pipeline_stats(self) -> dict:
        cold = await self.lead_repo.count_by_tier("cold")
        warm = await self.lead_repo.count_by_tier("warm")
        hot = await self.lead_repo.count_by_tier("hot")
        total = cold + warm + hot
        
        # Simple conversion stats based on events
        scored_events = await self.outreach_repo.get_events_by_type("scored")
        
        warm_conversions = len([e for e in scored_events if e.event_metadata and e.event_metadata.get("tier") == "warm"])
        hot_conversions = len([e for e in scored_events if e.event_metadata and e.event_metadata.get("tier") == "hot"])
        
        return {
            "cold_count": cold,
            "warm_count": warm,
            "hot_count": hot,
            "total": total,
            "cold_pct": round(cold / total * 100, 1) if total else 0.0,
            "warm_pct": round(warm / total * 100, 1) if total else 0.0,
            "hot_pct": round(hot / total * 100, 1) if total else 0.0,
            "conversions": {
                "to_warm": warm_conversions,
                "to_hot": hot_conversions,
                "warm_rate": round(warm_conversions / total * 100, 1) if total else 0.0,
                "hot_rate": round(hot_conversions / total * 100, 1) if total else 0.0,
            }
        }
