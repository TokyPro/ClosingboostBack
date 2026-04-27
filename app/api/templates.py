import datetime
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_db
from ..models.core import EmailTemplate
from ..schemas.templates import EmailTemplateCreate, EmailTemplateSchema, EmailTemplateUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=list[EmailTemplateSchema])
async def list_templates(db: AsyncSession = Depends(get_db)) -> list[EmailTemplate]:
    result = await db.execute(select(EmailTemplate).order_by(EmailTemplate.created_at.desc()))
    return list(result.scalars().all())


@router.post("/", response_model=EmailTemplateSchema, status_code=201)
async def create_template(data: EmailTemplateCreate, db: AsyncSession = Depends(get_db)) -> EmailTemplate:
    tpl = EmailTemplate(**data.model_dump())
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return tpl


@router.put("/{template_id}", response_model=EmailTemplateSchema)
async def update_template(
    template_id: str, data: EmailTemplateUpdate, db: AsyncSession = Depends(get_db)
) -> EmailTemplate:
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(tpl, field, value)
    tpl.updated_at = datetime.datetime.now(datetime.timezone.utc)
    await db.commit()
    await db.refresh(tpl)
    return tpl


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: str, db: AsyncSession = Depends(get_db)) -> None:
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.delete(tpl)
    await db.commit()
