from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from typing import Optional, Dict, Any, List
from datetime import datetime

class UserBase(BaseModel):
    email: str

class UserCreate(UserBase):
    password: str

class UserSchema(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    role: str
    status: str = "active"
    created_at: datetime

class Token(BaseModel):
    access_token: str
    token_type: str

class RegisterRequest(BaseModel):
    email: str
    password: str

class OpportunityCreate(BaseModel):
    title: str = Field(..., example="Cloud ERP Modernization")
    company_name: str = Field(..., example="Enterprise Corp")
    value: float = Field(0.0, example=250000.0)
    priority: str = Field("medium", example="high")
    win_probability: float = Field(0.0, example=0.0)
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    meeting_date: Optional[datetime] = None

class OpportunityUpdate(BaseModel):
    title: Optional[str] = None
    company_name: Optional[str] = None
    value: Optional[float] = None
    # creation, qualification, first_meeting, waiting_signature, signed, quote_needed, offer_sent
    stage: Optional[str] = None
    win_probability: Optional[float] = None
    priority: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    meeting_date: Optional[datetime] = None

class BriefingSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    opportunity_id: UUID
    ai_strategy: str
    ai_risk_assessment: str
    market_insights: Dict[str, Any]
    buyer_persona: Optional[str] = None
    value_prop_alignment: Optional[str] = None

class OpportunitySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    company_name: str
    stage: str
    value: float
    win_probability: float
    priority: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    meeting_date: Optional[datetime] = None
    created_at: datetime

# ── Interactions ─────────────────────────────────────────────────────────────

class InteractionBase(BaseModel):
    opportunity_id: UUID
    type: str = "visit"
    summary: Optional[str] = None
    raw_transcript: Optional[str] = None
    requirements: Optional[Dict[str, Any]] = None

class InteractionCreate(InteractionBase):
    pass

class InteractionSchema(InteractionBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime

# ── Copilot / Requirements Gathering ─────────────────────────────────────────

class CopilotMessage(BaseModel):
    role: str  # "assistant" | "user"
    content: str

class CopilotChatRequest(BaseModel):
    messages: List[CopilotMessage]

class RequirementsSummary(BaseModel):
    description: Optional[str] = None
    platform: Optional[str] = None
    features: Optional[str] = None
    hosting: Optional[str] = None
    data_volume: Optional[str] = None
    users: Optional[str] = None
    timeline: Optional[str] = None
    integrations: Optional[str] = None

class CopilotChatResponse(BaseModel):
    message: str
    suggestions: List[str]
    requirements: RequirementsSummary
    tactical_advice: Optional[str] = None
    progress: int
    is_complete: bool

class CopilotSaveRequest(BaseModel):
    opportunity_id: UUID
    messages: List[CopilotMessage]
    requirements: RequirementsSummary
    type: str = "meeting"

class UserUpdate(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None

class UserCreateAdmin(BaseModel):
    email: str
    password: str
    role: str = "executive"
    status: str = "active"

class DocumentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    original_name: str
    category: str
    status: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    google_file_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class AdminStats(BaseModel):
    user_count: int
    document_count: int
    opportunity_count: int
    synced_document_count: int

class QuotePhase(BaseModel):
    name: str
    duration_days: int
    cost: float
    description: str

class QuoteRequest(BaseModel):
    requirements: RequirementsSummary
    custom_fields: Optional[Dict[str, str]] = None

class QuoteResponse(BaseModel):
    project_title: str
    daily_rate: float
    total_cost: float
    total_duration_days: int
    phases: List[QuotePhase]
    assumptions: List[str]
