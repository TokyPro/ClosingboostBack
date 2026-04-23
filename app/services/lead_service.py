from __future__ import annotations

import datetime
import json
import logging
import re
import uuid
from typing import Optional
from uuid import UUID

import httpx
import urllib.parse
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
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

LEAD_EXTRACTION_PROMPT = """Tu es un expert en extraction de données de leads commerciaux B2B.

À partir des résultats de recherche suivants, extrais les informations structurées pour chaque lead potentiel.

Contexte de la recherche : thématique="{query}", localisation="{location}"

Résultats bruts (titre, URL, extrait) :
{results_text}

Pour chaque résultat pertinent, extrais :
- name : prénom et nom complet (uniquement pour profils individuels, null pour les entreprises)
- job_title : titre du poste actuel (null si non disponible)
- company : nom de l'entreprise actuelle (null si non disponible)
- location : ville et/ou pays (null si non disponible)
- source : "linkedin_profile" si l'URL contient linkedin.com/in/, "linkedin_company" si linkedin.com/company/, "datagouv" si l'URL contient data.gouv.fr ou annuaire-entreprises, sinon "web"
- summary : 1 phrase de présentation du lead ou de l'entreprise (en français)

Règles importantes :
- N'inclure que les résultats clairement pertinents pour la thématique et la localisation demandées
- Pour les pages linkedin.com/company/, name doit être null
- Si une information est absente ou incertaine, mettre null
- Le tableau "leads" doit avoir exactement autant d'éléments que les résultats fournis (même ordre)

Retourne UNIQUEMENT un objet JSON valide sans markdown ni explication :
{{"leads": [{{"name": null, "job_title": null, "company": null, "location": null, "source": "web", "summary": null}}]}}"""


class LeadService:
    def __init__(self, ai_service: AIIntelligenceService) -> None:
        self.ai_service = ai_service

    async def search_leads(self, request: LeadSearchRequest) -> LeadSearchResponse:
        # Instead of Tavily, we now use Crawl4AI to search via DuckDuckGo HTML
        all_raw: list[dict] = []

        # Sources logic: we map sources to specific search queries or domain filters
        if "linkedin" in request.sources:
            linkedin_results = await self._crawl4ai_search(
                query=self._build_query(request),
                max_results=request.max_results,
                include_domains=["linkedin.com"],
            )
            all_raw.extend(linkedin_results)

        if "datagouv" in request.sources:
            dg_parts = [p for p in [request.query, request.activity_sector, request.location] if p]
            dg_query = " ".join(dg_parts + ["entreprise"]) if dg_parts else "entreprise annuaire"
            dg_results = await self._crawl4ai_search(
                query=dg_query,
                max_results=max(5, request.max_results // 2),
                include_domains=["data.gouv.fr", "annuaire-entreprises.data.gouv.fr", "entreprises.data.gouv.fr"],
            )
            existing_urls = {r["url"] for r in all_raw}
            all_raw.extend(r for r in dg_results if r["url"] not in existing_urls)

        if "web" in request.sources:
            web_parts = [p for p in [request.query, request.activity_sector, request.location] if p]
            web_query = " ".join(web_parts + ["contact professionnel"]) if web_parts else "contact professionnel B2B"
            web_results = await self._crawl4ai_search(
                query=web_query,
                max_results=max(5, request.max_results // 2),
                include_domains=[],
            )
            existing_urls = {r["url"] for r in all_raw}
            all_raw.extend(r for r in web_results if r["url"] not in existing_urls)

        if not all_raw:
            return LeadSearchResponse(
                leads=[], total=0,
                query_used=self._build_query(request), demo_mode=False,
            )

        leads = await self._extract_with_ai(all_raw, request)
        return LeadSearchResponse(
            leads=leads,
            total=len(leads),
            query_used=self._build_query(request),
            demo_mode=False,
        )

    def _build_query(self, request: LeadSearchRequest) -> str:
        parts = [p for p in [request.query, request.activity_sector, request.location] if p]
        return " ".join(parts) if parts else "professionnel contact"

    async def _crawl4ai_search(
        self,
        query: str,
        max_results: int,
        include_domains: list[str] = None,
    ) -> list[dict]:
        """Search via DuckDuckGo HTML with pagination to retrieve more results."""
        search_query = query
        if include_domains:
            search_query += " site:" + " OR site:".join(include_domains)
        
        results = []
        # Initial URL
        current_url = "https://html.duckduckgo.com/html/"
        payload = {"q": search_query}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                while len(results) < max_results:
                    # DuckDuckGo HTML uses POST for the search and pagination
                    resp = await client.post(current_url, data=payload, headers=headers)
                    if resp.status_code != 200:
                        logger.error("DuckDuckGo search failed with status %s", resp.status_code)
                        break
                    
                    soup = BeautifulSoup(resp.text, "html.parser")
                    items = soup.select(".result")
                    
                    if not items:
                        break

                    for item in items:
                        if len(results) >= max_results:
                            break
                            
                        link_tag = item.select_one(".result__a")
                        snippet_tag = item.select_one(".result__snippet")
                        if link_tag and link_tag.get("href"):
                            link_url = link_tag.get("href")
                            if "uddg=" in link_url:
                                parsed_url = urllib.parse.urlparse(link_url)
                                query_params = urllib.parse.parse_qs(parsed_url.query)
                                if "uddg" in query_params:
                                    link_url = query_params["uddg"][0]
                            
                            results.append({
                                "url": link_url,
                                "title": link_tag.get_text(strip=True),
                                "content": snippet_tag.get_text(strip=True) if snippet_tag else "",
                                "score": 0.8,
                            })
                    
                    # Look for the "Next" button form
                    next_form = soup.find("form", attrs={"action": "/html/"})
                    if not next_form:
                        # Sometimes the action is absolute or different
                        next_form = soup.find("form", attrs={"action": re.compile(r".*/html/.*")})
                    
                    if next_form:
                        # Extract all hidden inputs for the next page
                        next_payload = {}
                        for inp in next_form.find_all("input", type="hidden"):
                            next_payload[inp.get("name")] = inp.get("value")
                        
                        # The search query 'q' is also usually in the form
                        if "q" not in next_payload:
                            next_payload["q"] = search_query
                            
                        payload = next_payload
                        # current_url remains the same for the form action usually
                    else:
                        break
                
                return results
        except Exception as exc:
            logger.error("Search pagination exception: %s", exc)
            return []

    async def _extract_with_ai(
        self,
        raw_results: list[dict],
        request: LeadSearchRequest,
    ) -> list[LeadResult]:
        # We process all results found, or a larger batch (e.g. 50) to avoid LLM context issues, 
        # but the user requested 'not to limit', so we'll increase the processing window.
        results_for_prompt = [
            {
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "content": (r.get("content") or "")[:400],
            }
            for r in raw_results
        ]

        prompt = LEAD_EXTRACTION_PROMPT.format(
            query=f"{request.query} (secteur: {request.activity_sector})",
            location=request.location,
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
            score = float(raw_results[i].get("score", 0.5)) if i < len(raw_results) else 0.5
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
        q = request.query or "Commercial"
        loc = request.location or "France"
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
            query_used=f"{request.query} {request.location}".strip(),
            demo_mode=True,
        )


# ── DB persistence service ────────────────────────────────────────────────────

class LeadDBService:
    """Handles CRUD operations for persisted leads."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = LeadRepository(db)

    async def save(self, data: LeadSaveRequest) -> LeadRecord:
        # Deduplicate by LinkedIn URL when available
        if data.linkedin_url:
            existing = await self.repo.get_by_linkedin_url(data.linkedin_url)
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

        # Initialize scoring fields inline to avoid circular imports
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
