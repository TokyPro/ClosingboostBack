from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from ..database import get_db
from ..services.document_service import DocumentService
from ..schemas.core import DocumentSchema

router = APIRouter()

MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".csv": "text/csv",
}


@router.get("/", response_model=List[DocumentSchema], summary="List knowledge base documents")
async def list_documents(db: AsyncSession = Depends(get_db)) -> List[DocumentSchema]:
    service = DocumentService(db)
    return await service.list_documents()


@router.post("/upload", response_model=DocumentSchema, status_code=status.HTTP_201_CREATED, summary="Upload document to knowledge base")
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form(default="general"),
    db: AsyncSession = Depends(get_db),
) -> DocumentSchema:
    from pathlib import Path
    ext = Path(file.filename or "").suffix.lower()
    mime_type = file.content_type or MIME_BY_EXT.get(ext, "application/octet-stream")
    file_bytes = await file.read()
    if len(file_bytes) > 50 * 1024 * 1024:  # 50 MB limit
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")
    service = DocumentService(db)
    try:
        return await service.upload_document(
            file_bytes=file_bytes,
            original_name=file.filename or "unnamed",
            mime_type=mime_type,
            category=category,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/{doc_id}/reindex", response_model=DocumentSchema, summary="Reindex a document")
async def reindex_document(doc_id: str, db: AsyncSession = Depends(get_db)) -> DocumentSchema:
    service = DocumentService(db)
    doc = await service.reindex_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/reindex-all", summary="Reindex all documents")
async def reindex_all(db: AsyncSession = Depends(get_db)) -> dict:
    service = DocumentService(db)
    count = await service.reindex_all()
    return {"reindexed": count}


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete document")
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db)) -> None:
    service = DocumentService(db)
    deleted = await service.delete_document(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
