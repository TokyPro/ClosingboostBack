from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas.leads import (
    AirtableExportRequest,
    AirtableImportRequest,
    ExportResult,
    ImportResult,
    LeadRecord,
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

router = APIRouter()

_ai_service = AIIntelligenceService()
_search_service = LeadService(ai_service=_ai_service)


# ── Search (stateless) ────────────────────────────────────────────────────────

@router.post("/search", response_model=LeadSearchResponse, summary="Search leads via Crawl4AI + Gemini")
async def search_leads(request: LeadSearchRequest) -> LeadSearchResponse:
    return await _search_service.search_leads(request)


# ── Persistence CRUD ──────────────────────────────────────────────────────────

@router.post(
    "/save",
    response_model=LeadRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Save a lead to the database",
)
async def save_lead(
    data: LeadSaveRequest,
    db: AsyncSession = Depends(get_db),
) -> LeadRecord:
    svc = LeadDBService(db)
    return await svc.save(data)


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
