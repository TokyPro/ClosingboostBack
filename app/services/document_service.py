import io
import logging
import datetime
from pathlib import Path
from typing import List, Optional

import google.genai as genai
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..repositories.document_repository import DocumentRepository
from ..models.core import Document

logger = logging.getLogger(__name__)

UPLOADS_DIR = Path(__file__).parent.parent.parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
}


class DocumentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = DocumentRepository(db)
        self.api_key = settings.GOOGLE_API_KEY

    def _client(self) -> genai.Client:
        if not self.api_key:
            raise RuntimeError("GOOGLE_API_KEY not configured")
        return genai.Client(api_key=self.api_key)

    async def list_documents(self) -> List[Document]:
        return await self.repo.get_all()

    async def upload_document(
        self, file_bytes: bytes, original_name: str, mime_type: str, category: str
    ) -> Document:
        if mime_type not in ALLOWED_MIME_TYPES:
            raise ValueError(f"Unsupported file type: {mime_type}")

        # Persist locally for reindexing
        import uuid
        doc_id = uuid.uuid4().hex
        safe_name = f"{doc_id}_{original_name}"
        local_path = UPLOADS_DIR / safe_name
        local_path.write_bytes(file_bytes)

        # Upload to Google File API
        client = self._client()
        response = client.files.upload(
            file=io.BytesIO(file_bytes),
            config=genai.types.UploadFileConfig(
                display_name=original_name,
                mime_type=mime_type,
            ),
        )

        doc = Document(
            original_name=original_name,
            category=category,
            status="synced",
            file_size=len(file_bytes),
            local_path=str(safe_name),
            mime_type=mime_type,
            google_file_id=response.name,
        )
        return await self.repo.create(doc)

    async def reindex_document(self, doc_id: str) -> Optional[Document]:
        doc = await self.repo.get_by_id(doc_id)
        if not doc:
            return None

        if not doc.local_path:
            doc.status = "error"
            doc.updated_at = datetime.datetime.now(datetime.timezone.utc)
            return await self.repo.update(doc)

        file_path = UPLOADS_DIR / doc.local_path
        if not file_path.exists():
            doc.status = "error"
            doc.updated_at = datetime.datetime.now(datetime.timezone.utc)
            return await self.repo.update(doc)

        doc.status = "indexing"
        doc.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await self.repo.update(doc)

        try:
            client = self._client()
            # Delete old Google file if exists
            if doc.google_file_id:
                try:
                    client.files.delete(name=doc.google_file_id)
                except Exception:
                    pass

            file_bytes = file_path.read_bytes()
            response = client.files.upload(
                file=io.BytesIO(file_bytes),
                config=genai.types.UploadFileConfig(
                    display_name=doc.original_name,
                    mime_type=doc.mime_type or "application/octet-stream",
                ),
            )
            doc.google_file_id = response.name
            doc.status = "synced"
        except Exception as exc:
            logger.error("Reindex failed for %s: %s", doc_id, exc)
            doc.status = "error"

        doc.updated_at = datetime.datetime.now(datetime.timezone.utc)
        return await self.repo.update(doc)

    async def reindex_all(self) -> int:
        docs = await self.repo.get_all()
        count = 0
        for doc in docs:
            result = await self.reindex_document(doc.id)
            if result and result.status == "synced":
                count += 1
        return count

    async def delete_document(self, doc_id: str) -> bool:
        doc = await self.repo.get_by_id(doc_id)
        if not doc:
            return False

        if doc.google_file_id and self.api_key:
            try:
                self._client().files.delete(name=doc.google_file_id)
            except Exception as exc:
                logger.warning("Could not delete Google file %s: %s", doc.google_file_id, exc)

        if doc.local_path:
            local = UPLOADS_DIR / doc.local_path
            if local.exists():
                local.unlink(missing_ok=True)

        await self.repo.delete(doc)
        return True
