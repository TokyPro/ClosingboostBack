from __future__ import annotations

import asyncio
import datetime
import json
import logging
import platform
import re
import uuid
from typing import Optional
from uuid import UUID

from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import CrawlerRunConfig
from ddgs import DDGS
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.core import Lead
from ..repositories.lead_repository import LeadRepository
from ..schemas.leads import (
    LeadRecord,
    LeadResult,
    LeadSaveRequest,
    LeadSearchRequest,
    LeadSearchResponse,
    LeadUpdateRequest,
    LeadsListResponse,
)
from .ai_service import AIIntelligenceService

logger = logging.getLogger(__name__)

CHAT_PARSE_PROMPT = """Tu es un assistant de recherche de leads commerciaux B2B.

L'utilisateur demande : "{message}"

Analyse sa demande et extrais les paramètres de recherche.

Retourne UNIQUEMENT un objet JSON valide (sans markdown) :
{{"query": "<mots-clés principaux : poste, rôle, ou type de profil>", "location": "<ville/région/pays ou null>", "activity_sector": "<secteur d'activité ou null>", "ai_response": "<réponse en 1-2 phrases en français confirmant ce que tu vas chercher>"}}"""

LEAD_EXTRACTION_PROMPT = """Tu es un expert en extraction de données de leads commerciaux B2B.

À partir des résultats de recherche suivants, extrais les informations structurées pour TOUS les leads.

Contexte de la recherche : thématique="{query}", localisation="{location}"

Résultats bruts (titre, URL, extrait) :
{results_text}

Pour CHAQUE résultat (sans exception), extrais :
- name : prénom et nom complet (uniquement pour profils individuels, null pour les entreprises)
- job_title : titre du poste actuel (null si non disponible)
- company : nom de l'entreprise actuelle (null si non disponible)
- location : ville et/ou pays (null si non disponible)
- source : "linkedin_profile" si l'URL contient linkedin.com/in/, "linkedin_company" si linkedin.com/company/, "datagouv" si l'URL contient data.gouv.fr ou annuaire-entreprises, sinon "web"
- summary : 1 phrase de présentation du lead ou de l'entreprise (en français), null si vraiment impossible
- relevance_score : score de pertinence entre 0.10 et 1.0 selon la correspondance avec la thématique et la localisation

Règles importantes :
- Inclure TOUS les résultats, même ceux peu pertinents (score minimum 0.10)
- Les résultats très pertinents reçoivent un score >= 0.70, les moyennement pertinents entre 0.30 et 0.69, les faiblement pertinents entre 0.10 et 0.29
- Pour les pages linkedin.com/company/, name doit être null
- Si une information est absente ou incertaine, mettre null
- Le tableau "leads" doit avoir exactement autant d'éléments que les résultats fournis (même ordre)

Retourne UNIQUEMENT un objet JSON valide sans markdown ni explication :
{{"leads": [{{"name": null, "job_title": null, "company": null, "location": null, "source": "web", "summary": null, "relevance_score": 0.5}}]}}"""


class LeadService:
    def __init__(self, ai_service: AIIntelligenceService) -> None:
        self.ai_service = ai_service

    async def search_leads(self, request: LeadSearchRequest) -> LeadSearchResponse:
        # Parse natural language message via Gemini
        parsed = await self._parse_chat_message(request.message)
        query: str = parsed.get("query") or ""
        location: str = parsed.get("location") or ""
        activity_sector: str = parsed.get("activity_sector") or ""
        ai_response: Optional[str] = parsed.get("ai_response") or None

        query_parts = [p for p in [query, activity_sector, location] if p]
        combined_query = " ".join(query_parts) if query_parts else request.message or "professionnel contact"

        # Build per-source search tasks and run them in parallel
        tasks: list = []
        task_labels: list[str] = []

        if "linkedin" in request.sources:
            tasks.append(self._ddgs_search(
                query=combined_query,
                include_domains=["linkedin.com"],
            ))
            task_labels.append("linkedin")

        if "datagouv" in request.sources:
            dg_query = " ".join(filter(None, [query, activity_sector, location, "entreprise"])) or "entreprise annuaire"
            tasks.append(self._ddgs_search(
                query=dg_query,
                include_domains=["data.gouv.fr", "annuaire-entreprises.data.gouv.fr", "entreprises.data.gouv.fr"],
            ))
            task_labels.append("datagouv")

        if "web" in request.sources:
            web_query = " ".join(filter(None, [query, activity_sector, location, "contact professionnel"])) or "contact professionnel B2B"
            tasks.append(self._ddgs_search(
                query=web_query,
                include_domains=[],
            ))
            task_labels.append("web")

        if not tasks:
            return LeadSearchResponse(
                leads=[], total=0,
                query_used=combined_query, demo_mode=False, ai_response=ai_response,
            )

        source_results = await asyncio.gather(*tasks)
        logger.info("DDGS results per source: %s", {
            label: len(res) for label, res in zip(task_labels, source_results)
        })

        # Deduplicate by URL across sources
        seen_urls: set[str] = set()
        all_raw: list[dict] = []
        for results in source_results:
            for r in results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_raw.append(r)

        if not all_raw:
            return LeadSearchResponse(
                leads=[], total=0,
                query_used=combined_query, demo_mode=False, ai_response=ai_response,
            )

        # Enrich results that have thin snippets using Crawl4AI
        all_raw = await self._enrich_with_crawl4ai(all_raw)

        leads = await self._extract_with_ai(all_raw, query, location, activity_sector)
        return LeadSearchResponse(
            leads=leads,
            total=len(leads),
            query_used=combined_query,
            demo_mode=False,
            ai_response=ai_response,
        )

    async def _parse_chat_message(self, message: str) -> dict:
        """Use Gemini to extract query params from a natural language message."""
        if not message.strip():
            return {"query": "", "location": None, "activity_sector": None, "ai_response": None}
        prompt = CHAT_PARSE_PROMPT.format(message=message)
        try:
            raw_text = await self.ai_service.generate_text(prompt)
            clean = re.sub(r"```(?:json)?\n?([\s\S]*?)\n?```", r"\1", raw_text).strip()
            return json.loads(clean)
        except Exception as exc:
            logger.warning("Chat message parsing failed: %s", exc)
            return {"query": message, "location": None, "activity_sector": None, "ai_response": None}

    async def _ddgs_search(
        self,
        query: str,
        include_domains: list[str] | None = None,
    ) -> list[dict]:
        """Search via duckduckgo-search library with no result cap."""
        search_query = query
        if include_domains:
            site_parts = " OR ".join(f"site:{d}" for d in include_domains)
            search_query = f"{query} ({site_parts})"

        def _sync() -> list[dict]:
            results: list[dict] = []
            try:
                with DDGS() as ddgs:
                    for r in ddgs.text(search_query, max_results=None, safesearch="off"):
                        results.append({
                            "url": r["href"],
                            "title": r["title"],
                            "content": r.get("body", ""),
                            "score": 0.5,
                        })
            except Exception as exc:
                logger.error("DDGS search error for '%s': %s", search_query, exc)
            return results

        return await asyncio.to_thread(_sync)

    async def _enrich_with_crawl4ai(self, results: list[dict]) -> list[dict]:
        """Scrape result pages with Crawl4AI to enrich thin snippets."""
        # Crawl4AI relies on subprocess transport which is unsupported on Windows
        if platform.system() == "Windows":
            return results

        enriched = [r.copy() for r in results]
        to_crawl = [
            (i, r) for i, r in enumerate(enriched)
            if r.get("url", "").startswith("http") and len(r.get("content", "")) < 80
        ]
        if not to_crawl:
            return enriched

        try:
            crawl_config = CrawlerRunConfig(page_timeout=10000)
            async with AsyncWebCrawler(verbose=False) as crawler:
                crawl_tasks = [
                    crawler.arun(url=r["url"], config=crawl_config) for _, r in to_crawl
                ]
                crawl_results = await asyncio.gather(*crawl_tasks, return_exceptions=True)
                for (idx, _), result in zip(to_crawl, crawl_results):
                    if isinstance(result, Exception):
                        logger.debug("Crawl4AI failed for idx %d: %s", idx, result)
                        continue
                    md = getattr(result, "markdown", None)
                    raw = getattr(md, "raw_markdown", None) if md else None
                    if raw:
                        enriched[idx]["content"] = raw[:600]
        except Exception as exc:
            logger.warning("Crawl4AI enrichment skipped: %s", exc)

        return enriched

    async def _extract_with_ai(
        self,
        raw_results: list[dict],
        query: str,
        location: str,
        activity_sector: str,
    ) -> list[LeadResult]:
        results_for_prompt = [
            {
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "content": (r.get("content") or "")[:300],
            }
            for r in raw_results
        ]

        prompt = LEAD_EXTRACTION_PROMPT.format(
            query=f"{query} (secteur: {activity_sector})" if activity_sector else query,
            location=location,
            results_text=json.dumps(results_for_prompt, ensure_ascii=False, indent=2),
        )

        extracted: list[dict] = []
        try:
            raw_text = await self.ai_service.generate_text(prompt)
            clean = re.sub(r"```(?:json)?\n?([\s\S]*?)\n?```", r"\1", raw_text).strip()
            data = json.loads(clean)
            extracted = data.get("leads", [])
        except Exception as exc:
            logger.error("AI lead extraction failed: %s — falling back to basic parse", exc)
            return self._basic_parse(raw_results)

        leads: list[LeadResult] = []
        for i, item in enumerate(extracted):
            source_url = raw_results[i]["url"] if i < len(raw_results) else ""
            ai_score = item.get("relevance_score")
            score = float(ai_score) if ai_score is not None else float(raw_results[i].get("score", 0.5)) if i < len(raw_results) else 0.5
            score = max(0.10, min(1.0, score))
            name = item.get("name") or ""
            leads.append(LeadResult(
                id=str(uuid.uuid4()),
                name=name or None,
                job_title=item.get("job_title") or None,
                company=item.get("company") or None,
                location=item.get("location") or None,
                url=source_url,
                summary=item.get("summary") or None,
                source=item.get("source", "web"),
                relevance_score=round(score, 2),
                avatar_initials=self._initials(name),
            ))
        return leads

    def _basic_parse(self, results: list[dict]) -> list[LeadResult]:
        leads: list[LeadResult] = []
        for r in results:
            url = r.get("url", "")
            source = "web"
            if "linkedin.com/in/" in url:
                source = "linkedin_profile"
            elif "linkedin.com/company/" in url:
                source = "linkedin_company"
            elif "data.gouv.fr" in url or "annuaire-entreprises" in url or "entreprises.data.gouv" in url:
                source = "datagouv"

            name: Optional[str] = None
            if source == "linkedin_profile":
                slug = url.split("linkedin.com/in/")[-1].strip("/").split("?")[0]
                name = " ".join(p.capitalize() for p in slug.split("-") if p)

            title_raw = r.get("title", "")
            parts = title_raw.split(" - ")
            leads.append(LeadResult(
                id=str(uuid.uuid4()),
                name=name or None,
                job_title=parts[0].strip() if parts else None,
                company=parts[1].strip() if len(parts) > 1 else None,
                location=None,
                url=url,
                summary=(r.get("content") or "")[:200] or None,
                source=source,
                relevance_score=round(float(r.get("score", 0.5)), 2),
                avatar_initials=self._initials(name or ""),
            ))
        return leads

    @staticmethod
    def _initials(name: str) -> str:
        parts = name.strip().split()
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[-1][0]}".upper()
        if parts and parts[0]:
            return parts[0][0].upper()
        return "?"

    def _demo_response(self, request: LeadSearchRequest) -> LeadSearchResponse:
        q = request.message or "Commercial"
        loc = "France"
        demo = [
            LeadResult(id="d1", name="Sophie Martin", job_title=f"Directrice {q}", company="TechCorp France", location=loc, url="https://www.linkedin.com/in/sophie-martin-tech", summary=f"Experte en {q.lower()} B2B avec 10 ans d'expérience dans le SaaS.", source="linkedin_profile", relevance_score=0.96, avatar_initials="SM"),
            LeadResult(id="d2", name="Thomas Dubois", job_title="CEO & Co-Founder", company="StartupIA", location=loc, url="https://www.linkedin.com/in/thomas-dubois-startup", summary="Serial entrepreneur spécialisé dans l'IA appliquée aux processus métier.", source="linkedin_profile", relevance_score=0.91, avatar_initials="TD"),
            LeadResult(id="d3", name="Marie Lefebvre", job_title=f"Head of {q}", company="CloudSolutions SAS", location=loc, url="https://www.linkedin.com/in/marie-lefebvre-cloud", summary="Responsable avec expertise en Enterprise SaaS et transformation digitale.", source="linkedin_profile", relevance_score=0.87, avatar_initials="ML"),
            LeadResult(id="d4", name="Antoine Bernard", job_title="Directeur des Opérations", company="DataInsight Group", location=loc, url="https://www.linkedin.com/in/antoine-bernard-data", summary="COO passionné par les solutions d'analyse de données en temps réel.", source="linkedin_profile", relevance_score=0.83, avatar_initials="AB"),
            LeadResult(id="d5", name="Camille Rousseau", job_title="VP Business Development", company="ScaleUp Ventures", location=loc, url="https://www.linkedin.com/in/camille-rousseau-biz", summary="Spécialiste du développement commercial et des partenariats stratégiques.", source="linkedin_profile", relevance_score=0.79, avatar_initials="CR"),
            LeadResult(id="d6", name=None, job_title=None, company="InnovateTech SARL", location=loc, url="https://www.linkedin.com/company/innovatetech", summary="Scale-up de 50 personnes, spécialisée en solutions cloud B2B.", source="linkedin_company", relevance_score=0.73, avatar_initials="IT"),
            LeadResult(id="d7", name="Julien Moreau", job_title=f"Senior {q} Manager", company="GrowthLab", location=loc, url="https://www.linkedin.com/in/julien-moreau-growth", summary="Expert en stratégies de croissance et acquisition client B2B.", source="linkedin_profile", relevance_score=0.71, avatar_initials="JM"),
            LeadResult(id="d8", name="Isabelle Petit", job_title="Responsable Développement Commercial", company="ConsultingPro", location=loc, url="https://www.linkedin.com/in/isabelle-petit-consulting", summary="15 ans d'expérience en conseil et développement commercial pour PME/ETI.", source="linkedin_profile", relevance_score=0.68, avatar_initials="IP"),
        ]
        return LeadSearchResponse(
            leads=demo, total=len(demo),
            query_used=request.message.strip(),
            demo_mode=True,
        )


# ── DB persistence service ────────────────────────────────────────────────────

class LeadDBService:
    """Handles CRUD operations for persisted leads."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = LeadRepository(db)

    async def save(self, data: LeadSaveRequest) -> LeadRecord:
        if data.linkedin_url:
            existing = await self.repo.get_by_linkedin_url(data.linkedin_url)
            if existing:
                return LeadRecord.model_validate(existing)
        if data.website_url:
            existing = await self.repo.get_by_website_url(data.website_url)
            if existing:
                return LeadRecord.model_validate(existing)

        lead = Lead(
            company_name=data.company_name,
            contact_name=data.contact_name,
            contact_title=data.contact_title,
            activity_sector=data.activity_sector,
            website_url=data.website_url,
            linkedin_url=data.linkedin_url,
            location=data.location,
            summary=data.summary,
            source=data.source,
            relevance_score=data.relevance_score,
            search_query=data.search_query,
            search_location=data.search_location,
        )
        saved = await self.repo.create(lead)

        saved.fit_score = round((data.relevance_score or 0.0) * 100, 2)
        saved.intent_score = 10.0
        raw_score = saved.fit_score * 0.4 + saved.intent_score * 0.6
        saved.score = round(raw_score, 2)
        saved.tier = (
            "hot" if raw_score >= 70 else ("warm" if raw_score >= 30 else "cold")
        )
        saved.score_updated_at = datetime.datetime.now(datetime.timezone.utc)
        await self.repo.update(saved)

        return LeadRecord.model_validate(saved)

    async def list(
        self,
        status: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> LeadsListResponse:
        offset = (page - 1) * limit
        leads = await self.repo.get_all(status=status, limit=limit, offset=offset)
        total = await self.repo.count(status=status)
        return LeadsListResponse(
            leads=[LeadRecord.model_validate(l) for l in leads],
            total=total,
            page=page,
            limit=limit,
        )

    async def update(self, lead_id: str, data: LeadUpdateRequest) -> Optional[LeadRecord]:
        lead = await self.repo.get_by_id(lead_id)
        if not lead:
            return None
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(lead, field, value)
        updated = await self.repo.update(lead)
        return LeadRecord.model_validate(updated)

    async def delete(self, lead_id: str) -> bool:
        return await self.repo.delete(lead_id)

    async def convert_to_opportunity(
        self, lead_id: str, owner_id: str
    ) -> Optional[dict]:
        from .opportunity_service import OpportunityService

        lead = await self.repo.get_by_id(lead_id)
        if not lead:
            return None

        opp_service = OpportunityService(self.db)
        opp = await opp_service.create_opportunity(
            title=(
                f"{lead.contact_name} — {lead.company_name}"
                if lead.contact_name and lead.company_name
                else lead.company_name or lead.contact_name or "Lead converti"
            ),
            company_name=lead.company_name or "Unknown",
            value=0.0,
            user_id=UUID(owner_id),
            priority="medium",
            win_probability=lead.relevance_score or 0.0,
            contact_name=lead.contact_name,
            contact_email=lead.contact_email,
            contact_phone=lead.contact_phone,
        )

        lead.status = "converted"
        lead.opportunity_id = str(opp.id)
        await self.repo.update(lead)

        return {"opportunity_id": str(opp.id), "lead_id": lead_id}
