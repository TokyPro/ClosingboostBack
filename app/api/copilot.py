from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..schemas.core import CopilotChatRequest, CopilotChatResponse, QuoteRequest, QuoteResponse, CopilotSaveRequest, InteractionSchema
from ..services.copilot_service import CopilotService
from ..database import get_db

router = APIRouter()

@router.post("/chat", response_model=CopilotChatResponse, summary="Requirements gathering chat")
async def copilot_chat(request: CopilotChatRequest) -> CopilotChatResponse:
    service = CopilotService()
    return await service.process_chat(request.messages)

@router.post("/save", response_model=InteractionSchema, summary="Save copilot session as interaction")
async def save_copilot_session(request: CopilotSaveRequest, db: AsyncSession = Depends(get_db)) -> InteractionSchema:
    service = CopilotService(db)
    return await service.save_session(request)

@router.post("/quote", response_model=QuoteResponse, summary="Generate project cost estimate")
async def generate_quote(request: QuoteRequest) -> QuoteResponse:
    service = CopilotService()
    result = await service.generate_quote(request.requirements)
    return QuoteResponse(**result)
