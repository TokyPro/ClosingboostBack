import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db, AsyncSessionLocal
from ..schemas.leads import (
    AirtableExportRequest,
    AirtableImportRequest,
    BatchEnrichRequest,
    ExportResult,
    ImportResult,
    LeadRecord,
    LeadResult,
    LeadSaveRequest,
    LeadSearchRequest,
    LeadSearchResponse,
    LeadUpdateRequest,
    LeadsListResponse,
    NotionExportRequest,
    NotionImportRequest,
)
from ..services.ai_service import AIIntelligenceService
from ..services.export_service import ExportService
from ..services.lead_service import LeadDBService, LeadService
from ..services.enrichment_service import EnrichmentService

logger = logging.getLogger(__name__)
router = APIRouter()

_ai_service = AIIntelligenceService()
_search_service = LeadService(ai_service=_ai_service)

# --- Dependency Functions ---
async def get_enrichment_service(db: AsyncSession = Depends(get_db)) -> EnrichmentService:
    return EnrichmentService(db, _ai_service)

AUTO_SAVE_THRESHOLD = 0.10


async def _bg_enrich(lead_id: str) -> None:
    async with AsyncSessionLocal() as db:
        svc = EnrichmentService(db, _ai_service)
        try:
            await svc.enrich_lead(lead_id)
        except Exception as exc:
            logger.debug("Background enrich failed for %s: %s", lead_id, exc)


async def _auto_save_qualifying_leads(leads: list[LeadResult], query_used: str) -> None:
    qualifying = [l for l in leads if l.relevance_score > AUTO_SAVE_THRESHOLD]
    if not qualifying:
        return
    async with AsyncSessionLocal() as db:
        svc = LeadDBService(db)
        for lead in qualifying:
            is_linkedin = "linkedin.com" in (lead.url or "")
            try:
                await svc.save(LeadSaveRequest(
                    company_name=lead.company,
                    contact_name=lead.name,
                    contact_title=lead.job_title,
                    location=lead.location,
                    linkedin_url=lead.url if is_linkedin else None,
                    website_url=lead.url if not is_linkedin else None,
                    summary=lead.summary,
                    source=lead.source,
                    relevance_score=lead.relevance_score,
                    search_query=query_used,
                ))
            except Exception as exc:
                logger.debug("Auto-save skipped for %s: %s", lead.url, exc)


# ── Search (stateless) ────────────────────────────────────────────────────────

@router.post("/search", response_model=LeadSearchResponse, summary="Search leads via Crawl4AI + Gemini")
async def search_leads(
    request: LeadSearchRequest,
    background_tasks: BackgroundTasks,
) -> LeadSearchResponse:
    result = await _search_service.search_leads(request)
    if result.leads:
        background_tasks.add_task(_auto_save_qualifying_leads, result.leads, result.query_used)
    return result


# ── Persistence CRUD ──────────────────────────────────────────────────────────

@router.post(
    "/save",
    response_model=LeadRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Save a lead to the database",
)
async def save_lead(
    data: LeadSaveRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> LeadRecord:
    svc = LeadDBService(db)
    record = await svc.save(data)
    # Auto-enrich in background
    background_tasks.add_task(_bg_enrich, record.id)
    return record


@router.get("/saved", response_model=LeadsListResponse, summary="List all saved leads")
async def list_saved_leads(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> LeadsListResponse:
    svc = LeadDBService(db)
    return await svc.list(status=status_filter, page=page, limit=limit)


@router.put("/saved/{lead_id}", response_model=LeadRecord, summary="Update a saved lead")
async def update_saved_lead(
    lead_id: str,
    data: LeadUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> LeadRecord:
    svc = LeadDBService(db)
    lead = await svc.update(lead_id, data)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.delete(
    "/saved/{lead_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a saved lead",
)
async def delete_saved_lead(
    lead_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    svc = LeadDBService(db)
    if not await svc.delete(lead_id):
        raise HTTPException(status_code=404, detail="Lead not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/saved/batch-enrich", summary="Batch enrich multiple leads")
async def batch_enrich_leads(
    data: BatchEnrichRequest,
    service: EnrichmentService = Depends(get_enrichment_service),
) -> dict:
    results = []
    for lead_id in data.lead_ids:
        try:
            result = await service.enrich_lead(lead_id)
            if result:
                results.append(result)
        except Exception as exc:
            logger.warning("Batch enrich failed for %s: %s", lead_id, exc)
    return {"enriched": len(results), "total": len(data.lead_ids)}


@router.post("/saved/{lead_id}/enrich", summary="Enrich a lead with AI and web research")
async def enrich_lead(
    lead_id: str,
    service: EnrichmentService = Depends(get_enrichment_service),
) -> dict:
    result = await service.enrich_lead(lead_id)
    if not result:
        raise HTTPException(status_code=404, detail="Lead not found")
    return result


@router.get("/saved/{lead_id}/signals", summary="Detect buying signals for a lead")
async def get_lead_signals(
    lead_id: str,
    service: EnrichmentService = Depends(get_enrichment_service),
) -> dict:
    result = await service.fetch_signals(lead_id)
    if not result:
        raise HTTPException(status_code=404, detail="Lead not found")
    return result


@router.post("/saved/{lead_id}/convert", summary="Convert a lead to an opportunity")
async def convert_lead(
    lead_id: str,
    user_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    svc = LeadDBService(db)
    result = await svc.convert_to_opportunity(lead_id, str(user_id))
    if not result:
        raise HTTPException(status_code=404, detail="Lead not found")
    return result


# ── Export ────────────────────────────────────────────────────────────────────

@router.post("/export/airtable", response_model=ExportResult, summary="Export leads to Airtable")
async def export_airtable(
    data: AirtableExportRequest,
    db: AsyncSession = Depends(get_db),
) -> ExportResult:
    svc = ExportService(db)
    result = await svc.export_to_airtable(data.lead_ids, data.api_key, data.base_id, data.table_name)
    return ExportResult(**result)


@router.post("/export/notion", response_model=ExportResult, summary="Export leads to Notion")
async def export_notion(
    data: NotionExportRequest,
    db: AsyncSession = Depends(get_db),
) -> ExportResult:
    svc = ExportService(db)
    result = await svc.export_to_notion(data.lead_ids, data.token, data.database_id)
    return ExportResult(**result)


@router.post("/import/airtable", response_model=ImportResult, summary="Import leads from Airtable")
async def import_airtable(
    data: AirtableImportRequest,
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    svc = ExportService(db)
    result = await svc.import_from_airtable(data.api_key, data.base_id, data.table_name)
    return ImportResult(**result)


@router.post("/import/notion", response_model=ImportResult, summary="Import leads from Notion")
async def import_notion(
    data: NotionImportRequest,
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    svc = ExportService(db)
    result = await svc.import_from_notion(data.token, data.database_id)
    return ImportResult(**result)
