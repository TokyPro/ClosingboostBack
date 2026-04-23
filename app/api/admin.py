from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from ..database import get_db
from ..models.core import User, Opportunity, Document
from ..schemas.core import AdminStats

router = APIRouter()


@router.get("/stats", response_model=AdminStats, summary="Admin dashboard stats")
async def get_admin_stats(db: AsyncSession = Depends(get_db)) -> AdminStats:
    user_count = (await db.execute(select(func.count(User.id)))).scalar() or 0
    doc_count = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    opp_count = (await db.execute(select(func.count(Opportunity.id)))).scalar() or 0
    synced_count = (
        await db.execute(select(func.count(Document.id)).where(Document.status == "synced"))
    ).scalar() or 0
    return AdminStats(
        user_count=user_count,
        document_count=doc_count,
        opportunity_count=opp_count,
        synced_document_count=synced_count,
    )
