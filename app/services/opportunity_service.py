import json
import logging
from uuid import UUID
from datetime import datetime
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from ..repositories.opportunity_repository import OpportunityRepository
from ..repositories.briefing_repository import BriefingRepository
from ..models.core import Opportunity, Briefing
from .ai_service import AIIntelligenceService

logger = logging.getLogger(__name__)


def _coerce_text(value: Any) -> Optional[str]:
    """Normalize a value for a Text column: strings pass through, dicts/lists
    are serialized to JSON so SQLAlchemy can bind them."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)

class OpportunityService:
    def __init__(
        self,
        db: AsyncSession,
        opp_repo: Optional[OpportunityRepository] = None,
        brief_repo: Optional[BriefingRepository] = None,
        ai_service: Optional[AIIntelligenceService] = None,
    ):
        self.db = db
        self.opp_repo = opp_repo or OpportunityRepository(db)
        self.brief_repo = brief_repo or BriefingRepository(db)
        self.ai_service = ai_service or AIIntelligenceService()

    async def list_opportunities(self, user_id: UUID) -> List[Opportunity]:
        return await self.opp_repo.get_all(owner_id=user_id)

    async def get_opportunity(self, opportunity_id: UUID) -> Optional[Opportunity]:
        return await self.opp_repo.get_by_id(opportunity_id)

    async def create_opportunity(
        self,
        title: str,
        company_name: str,
        value: float,
        user_id: UUID,
        priority: str = "medium",
        win_probability: float = 0.0,
        contact_name: str | None = None,
        contact_email: str | None = None,
        contact_phone: str | None = None,
        meeting_date: datetime | None = None,
    ) -> Opportunity:
        opp = Opportunity(
            title=title,
            company_name=company_name,
            value=value,
            owner_id=str(user_id),
            stage="creation",
            priority=priority,
            win_probability=win_probability,
            contact_name=contact_name,
            contact_email=contact_email,
            contact_phone=contact_phone,
            meeting_date=meeting_date,
        )
        created_opp = await self.opp_repo.create(opp)
        await self.db.commit()
        await self.db.refresh(created_opp)

        try:
            await self._generate_and_save_briefing(created_opp)
        except Exception:
            logger.exception(
                "Briefing generation failed for opportunity %s", created_opp.id
            )

        return created_opp

    def _build_briefing_context(self, opp: Opportunity) -> str:
        context_parts = [
            f"Opportunité : {opp.title}",
            f"Client : {opp.company_name}",
            f"Valeur estimée : {opp.value} $",
            f"Priorité : {opp.priority}",
        ]
        if opp.contact_name:
            context_parts.append(f"Contact principal : {opp.contact_name}")
        if opp.meeting_date:
            context_parts.append(
                f"Date du rendez-vous : {opp.meeting_date.strftime('%Y-%m-%d %H:%M')}"
            )
        return "\n".join(context_parts)

    async def _generate_and_save_briefing(self, opp: Opportunity) -> Briefing:
        ai_brief = await self.ai_service.generate_briefing(
            context=self._build_briefing_context(opp)
        )
        briefing = Briefing(
            opportunity_id=opp.id,
            ai_strategy=_coerce_text(ai_brief.get("ai_strategy")),
            ai_risk_assessment=_coerce_text(ai_brief.get("ai_risk_assessment")),
            market_insights=ai_brief.get("market_insights"),
            buyer_persona=_coerce_text(ai_brief.get("buyer_persona")),
            value_prop_alignment=_coerce_text(ai_brief.get("value_prop_alignment")),
        )
        created_briefing = await self.brief_repo.create(briefing)
        await self.db.commit()
        return created_briefing

    async def update_opportunity(
        self,
        opportunity_id: UUID,
        title: str | None = None,
        company_name: str | None = None,
        value: float | None = None,
        stage: str | None = None,
        win_probability: float | None = None,
        priority: str | None = None,
        contact_name: str | None = None,
        contact_email: str | None = None,
        contact_phone: str | None = None,
        meeting_date: datetime | None = None,
    ) -> Optional[Opportunity]:
        opp = await self.opp_repo.get_by_id(opportunity_id)
        if not opp:
            return None
        if title is not None:
            opp.title = title
        if company_name is not None:
            opp.company_name = company_name
        if value is not None:
            opp.value = value
        if stage is not None:
            opp.stage = stage
        if win_probability is not None:
            opp.win_probability = win_probability
        if priority is not None:
            opp.priority = priority
        if contact_name is not None:
            opp.contact_name = contact_name
        if contact_email is not None:
            opp.contact_email = contact_email
        if contact_phone is not None:
            opp.contact_phone = contact_phone
        if meeting_date is not None:
            opp.meeting_date = meeting_date
        
        updated_opp = await self.opp_repo.update(opp)
        await self.db.commit()
        await self.db.refresh(updated_opp)
        return updated_opp

    async def delete_opportunity(self, opportunity_id: UUID) -> bool:
        success = await self.opp_repo.delete(opportunity_id)
        if success:
            await self.db.commit()
        return success

    async def search_opportunities(self, user_id: UUID, query: str) -> List[Opportunity]:
        return await self.opp_repo.search(owner_id=user_id, query=query)

    async def get_briefing(self, opportunity_id: UUID) -> Optional[Briefing]:
        briefing = await self.brief_repo.get_by_opportunity_id(opportunity_id)
        if briefing:
            return briefing

        opp = await self.opp_repo.get_by_id(opportunity_id)
        if not opp:
            return None

        try:
            return await self._generate_and_save_briefing(opp)
        except Exception:
            logger.exception(
                "Lazy briefing generation failed for opportunity %s",
                opportunity_id,
            )
            return None
