from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional, List
from ..models.core import Document


class DocumentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_all(self) -> List[Document]:
        result = await self.db.execute(select(Document).order_by(Document.created_at.desc()))
        return list(result.scalars().all())

    async def get_by_id(self, doc_id: str) -> Optional[Document]:
        result = await self.db.execute(select(Document).where(Document.id == doc_id))
        return result.scalar_one_or_none()

    async def create(self, doc: Document) -> Document:
        self.db.add(doc)
        await self.db.commit()
        await self.db.refresh(doc)
        return doc

    async def update(self, doc: Document) -> Document:
        await self.db.commit()
        await self.db.refresh(doc)
        return doc

    async def delete(self, doc: Document) -> None:
        await self.db.delete(doc)
        await self.db.commit()
