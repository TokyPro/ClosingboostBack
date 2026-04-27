from __future__ import annotations

import datetime
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.core import Lead, OutreachMessage
from ..repositories.lead_repository import LeadRepository
from ..repositories.outreach_repository import OutreachRepository
from .ai_service import AIIntelligenceService
from .scoring_service import ScoringService

logger = logging.getLogger(__name__)

AGENT_NAMES = {
    "cold": "Éclaireur",
    "warm": "Conseiller",
    "hot": "Closer",
}


class AgentService:
    def __init__(self, db: AsyncSession, ai_service: AIIntelligenceService) -> None:
        self.db = db
        self.lead_repo = LeadRepository(db)
        self.outreach_repo = OutreachRepository(db)
        self.ai_service = ai_service
        self.scoring_service = ScoringService(db)

    def _build_lead_context(self, lead: Lead) -> str:
        parts: list[str] = []
        if lead.contact_name:
            parts.append(f"Contact : {lead.contact_name}")
        if lead.contact_title:
            parts.append(f"Poste : {lead.contact_title}")
        if lead.company_name:
            parts.append(f"Entreprise : {lead.company_name}")
        if lead.activity_sector:
            parts.append(f"Secteur : {lead.activity_sector}")
        if lead.location:
            parts.append(f"Localisation : {lead.location}")
        if lead.summary:
            parts.append(f"Résumé : {lead.summary}")
        parts.append(
            f"Score actuel : {lead.score:.0f}/100 "
            f"(Fit: {lead.fit_score:.0f}, Intent: {lead.intent_score:.0f})"
        )
        return "\n".join(parts)

    async def run_agent(self, lead_id: str, sequence_id: Optional[str] = None) -> Optional[dict]:
        lead = await self.lead_repo.get_by_id(lead_id)
        if not lead:
            return None

        # Auto-score first if never scored
        if lead.score_updated_at is None:
            lead = await self.scoring_service.score_lead(lead_id)
            if not lead:
                return None

        lead_context = self._build_lead_context(lead)
        tier = lead.tier

        # If in a sequence, we might want to adjust the generation logic
        # For now, let's just pass the sequence_id to the OutreachMessage

        if tier == "cold":
            news_str = ""
            if lead.company_news:
                news_items = (
                    lead.company_news if isinstance(lead.company_news, list) else []
                )
                news_str = "\n".join(f"- {n}" for n in news_items[:3])
            result = await self.ai_service.generate_cold_message(lead_context, news_str)
            channel = "email"
            subject = result.get("subject")
            message = result.get("message", "")
            rationale = result.get("rationale", "")

        elif tier == "warm":
            prev_msgs = await self.outreach_repo.get_messages_by_lead(lead_id)
            prev_str = (
                "\n".join(
                    f"- {m.created_at.strftime('%Y-%m-%d')} [{m.tier}] {m.status}"
                    for m in prev_msgs[:3]
                )
                or "Aucune"
            )
            result = await self.ai_service.generate_warm_message(lead_context, prev_str)
            channel = result.get("channel", "linkedin")
            subject = result.get("subject")
            message = result.get("message", "")
            rationale = result.get("rationale", "")

        else:  # hot
            result = await self.ai_service.generate_hot_message(lead_context, lead.score)
            channel = "email"
            subject = result.get("subject")
            message = result.get("message", "")
            rationale = result.get("rationale", "")
            slack_notif = result.get("slack_notification", "")
            logger.info("HOT LEAD ALERT [%s] — Slack: %s", lead_id, slack_notif)

        # Save the generated message as draft
        outreach = OutreachMessage(
            lead_id=lead_id,
            sequence_id=sequence_id,
            tier=tier,
            channel=channel,
            subject=subject,
            message_content=message,
            status="draft",
            score_before=lead.score,
        )
        saved_msg = await self.outreach_repo.create_message(outreach)

        # Increment outreach_attempts
        lead.outreach_attempts = (lead.outreach_attempts or 0) + 1
        lead.last_outreach_at = datetime.datetime.now(datetime.timezone.utc)
        await self.lead_repo.update(lead)

        return {
            "lead_id": lead_id,
            "tier": tier,
            "agent_name": AGENT_NAMES.get(tier, "Inconnu"),
            "action": f"Message {tier} généré",
            "channel": channel,
            "subject": subject,
            "message_content": message,
            "rationale": rationale,
            "message_id": saved_msg.id,
        }

    async def get_recommendation(self, lead_id: str) -> Optional[dict]:
        lead = await self.lead_repo.get_by_id(lead_id)
        if not lead:
            return None
        tier = lead.tier
        actions = {
            "cold": "Envoyer un email de notoriété basé sur l'actualité de l'entreprise",
            "warm": "Envoyer un message LinkedIn ciblant un pain point ou inviter au webinar",
            "hot": "Envoyer un pitch direct avec lien Calendly + notifier le commercial",
        }
        return {
            "lead_id": lead_id,
            "tier": tier,
            "agent_name": AGENT_NAMES.get(tier, "Inconnu"),
            "recommended_action": actions.get(tier, "Scorer le lead"),
            "current_score": lead.score,
            "outreach_attempts": lead.outreach_attempts,
        }
