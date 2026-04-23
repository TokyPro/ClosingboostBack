from fastapi import APIRouter, Depends, HTTPException, Response, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from ..database import get_db
from ..services.opportunity_service import OpportunityService
from ..schemas.core import OpportunitySchema, OpportunityCreate, OpportunityUpdate, BriefingSchema
from uuid import UUID

router = APIRouter()

@router.get("/", response_model=List[OpportunitySchema], summary="List all opportunities")
@router.get("/list", response_model=List[OpportunitySchema], include_in_schema=False)
async def list_opportunities(
    user_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Returns all sales opportunities for the given user."""
    service = OpportunityService(db)
    return await service.list_opportunities(user_id)

@router.post("/", response_model=OpportunitySchema, status_code=status.HTTP_201_CREATED, summary="Create a new opportunity")
@router.post("/create", response_model=OpportunitySchema, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_opportunity(
    opp_in: OpportunityCreate,
    user_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Creates an opportunity and triggers a Gemini 2.5 Flash briefing via RAG."""
    service = OpportunityService(db)
    return await service.create_opportunity(
        title=opp_in.title,
        company_name=opp_in.company_name,
        value=opp_in.value,
        user_id=user_id,
        priority=opp_in.priority,
        win_probability=opp_in.win_probability,
        contact_name=opp_in.contact_name,
        contact_email=opp_in.contact_email,
        contact_phone=opp_in.contact_phone,
        meeting_date=opp_in.meeting_date,
    )

@router.get("/search", response_model=List[OpportunitySchema], summary="Search opportunities")
async def search_opportunities(
    user_id: UUID = Query(...),
    q: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Full-text search on title and company name."""
    service = OpportunityService(db)
    return await service.search_opportunities(user_id, q)

@router.get("/{opportunity_id}", response_model=OpportunitySchema, summary="Get opportunity by ID")
async def get_opportunity(
    opportunity_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Returns a single opportunity by its UUID."""
    service = OpportunityService(db)
    opp = await service.get_opportunity(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opp

@router.put("/{opportunity_id}", response_model=OpportunitySchema, summary="Update opportunity")
async def update_opportunity(
    opportunity_id: UUID,
    update_in: OpportunityUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Updates any field of an opportunity."""
    service = OpportunityService(db)
    opp = await service.update_opportunity(
        opportunity_id=opportunity_id,
        title=update_in.title,
        company_name=update_in.company_name,
        value=update_in.value,
        stage=update_in.stage,
        win_probability=update_in.win_probability,
        priority=update_in.priority,
        contact_name=update_in.contact_name,
        contact_email=update_in.contact_email,
        contact_phone=update_in.contact_phone,
        meeting_date=update_in.meeting_date,
    )
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opp

@router.delete("/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete opportunity")
async def delete_opportunity(
    opportunity_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Permanently deletes an opportunity and its associated briefing."""
    service = OpportunityService(db)
    deleted = await service.delete_opportunity(opportunity_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/{opportunity_id}/briefing", response_model=BriefingSchema, summary="Get AI briefing")
async def get_briefing(
    opportunity_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Retrieves the strategic AI briefing for a specific opportunity."""
    service = OpportunityService(db)
    briefing = await service.get_briefing(opportunity_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    return briefing
