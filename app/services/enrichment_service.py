import logging
import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.lead_repository import LeadRepository
from .ai_service import AIIntelligenceService

logger = logging.getLogger(__name__)

class EnrichmentService:
    def __init__(self, db: AsyncSession, ai_service: AIIntelligenceService):
        self.db = db
        self.lead_repo = LeadRepository(db)
        self.ai_service = ai_service

    async def enrich_lead(self, lead_id: str) -> Optional[dict]:
        """Enriches a lead using AI and web research."""
        lead = await self.lead_repo.get_by_id(lead_id)
        if not lead:
            return None

        logger.info(f"Starting enrichment for lead: {lead.company_name or lead.id}")

        # Construct context for AI
        context = {
            "company_name": lead.company_name,
            "website_url": lead.website_url,
            "linkedin_url": lead.linkedin_url,
            "activity_sector": lead.activity_sector,
            "location": lead.location
        }

        # 1. Fetch Company News & Signals
        # We can reuse or enhance the existing news fetching logic in AI service
        news_data = await self.ai_service.fetch_company_news(lead.company_name or lead.website_url)
        
        # 2. Use Gemini to extract details and verify data
        enrichment_prompt = f"""
        Analyze the following lead information and provide enriched data:
        {context}
        
        Recent News found:
        {news_data}
        
        Please provide:
        1. Refined activity sector.
        2. A concise summary of the company's current challenges or growth signals.
        3. Potential business email pattern (e.g. first.last@company.com).
        4. Verified location if different.
        """
        
        # For now, let's assume we have a method in AI service for this
        # or we use a general purpose generation
        enriched_info = await self.ai_service.generate_enrichment_data(enrichment_prompt)
        
        # 3. Update Lead Model
        if enriched_info:
            lead.activity_sector = enriched_info.get("activity_sector", lead.activity_sector)
            lead.summary = enriched_info.get("summary", lead.summary)
            lead.company_news = news_data
            lead.enriched_at = datetime.datetime.now(datetime.timezone.utc)
            
            # If we guessed an email and it was missing
            if not lead.contact_email and enriched_info.get("suggested_email"):
                lead.contact_email = enriched_info.get("suggested_email")
                lead.email_status = "suggested"

            await self.lead_repo.update(lead)
            
        return {
            "lead_id": lead_id,
            "enriched_at": lead.enriched_at,
            "news_count": len(news_data) if news_data else 0,
            "status": "success"
        }

    async def fetch_signals(self, lead_id: str) -> Optional[dict]:
        """Specific focus on buying signals (fundraising, recruitment, expansion)."""
        lead = await self.lead_repo.get_by_id(lead_id)
        if not lead:
            return None

        news_data = await self.ai_service.fetch_company_news(lead.company_name or lead.website_url)
        
        signal_prompt = f"""
        Analyze these news items for buying signals (fundraising, new leadership, geographic expansion, recruitment spike) 
        for {lead.company_name}:
        {news_data}
        
        Provide:
        1. A 'signal_type' (e.g. FUNDRAISING, EXPANSION, RECRUITMENT, OTHER).
        2. A 'confidence' score (0-100).
        3. A 'recommended_outreach_angle' for the sales team.
        """
        
        signal_info = await self.ai_service.generate_enrichment_data(signal_prompt)
        
        if signal_info:
            # Update company_news and summary if significant
            lead.company_news = news_data
            await self.lead_repo.update(lead)
            
        return signal_info
