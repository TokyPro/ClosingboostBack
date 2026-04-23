from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from ..database import get_db
from ..services.interaction_service import InteractionService
from ..schemas.core import InteractionSchema, InteractionCreate

router = APIRouter()

@router.get("/opportunity/{opportunity_id}", response_model=List[InteractionSchema], summary="List interactions by opportunity")
async def list_interactions_by_opportunity(
    opportunity_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Returns all interactions for a specific opportunity."""
    service = InteractionService(db)
    return await service.get_interactions_by_opportunity(opportunity_id)

@router.post("/", response_model=InteractionSchema, status_code=status.HTTP_201_CREATED, summary="Create a new interaction")
async def create_interaction(
    interaction_in: InteractionCreate,
    db: AsyncSession = Depends(get_db)
):
    """Creates a new contact interaction."""
    service = InteractionService(db)
    return await service.create_interaction(interaction_in)

@router.get("/{interaction_id}", response_model=InteractionSchema, summary="Get interaction by ID")
async def get_interaction(
    interaction_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Returns a single interaction by its UUID."""
    service = InteractionService(db)
    interaction = await service.get_interaction(interaction_id)
    if not interaction:
        raise HTTPException(status_code=404, detail="Interaction not found")
    return interaction

@router.delete("/{interaction_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete interaction")
async def delete_interaction(
    interaction_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Deletes an interaction."""
    service = InteractionService(db)
    success = await service.delete_interaction(interaction_id)
    if not success:
        raise HTTPException(status_code=404, detail="Interaction not found")
    return None
