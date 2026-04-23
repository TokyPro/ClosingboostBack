from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Search (stateless, no DB) ─────────────────────────────────────────────────

class LeadSearchRequest(BaseModel):
    query: str = ""
    location: str = ""
    activity_sector: str = ""
    sources: list[str] = ["linkedin", "datagouv", "web"]
    max_results: int = Field(default=20, ge=1)


class LeadResult(BaseModel):
    id: str
    name: Optional[str] = None
    job_title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    url: str
    summary: Optional[str] = None
    source: str = "web"
    relevance_score: float = 0.0
    avatar_initials: str = "?"


class LeadSearchResponse(BaseModel):
    leads: list[LeadResult]
    total: int
    query_used: str
    demo_mode: bool = False


# ── DB persistence ────────────────────────────────────────────────────────────

class LeadSaveRequest(BaseModel):
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_title: Optional[str] = None
    activity_sector: Optional[str] = None
    website_url: Optional[str] = None
    linkedin_url: Optional[str] = None     # None for pure-web results
    location: Optional[str] = None
    summary: Optional[str] = None
    source: str = "web"
    relevance_score: float = 0.0
    search_query: Optional[str] = None
    search_location: Optional[str] = None


class LeadRecord(BaseModel):
    id: str
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_title: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    activity_sector: Optional[str] = None
    website_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    location: Optional[str] = None
    summary: Optional[str] = None
    source: str = "web"
    relevance_score: float = 0.0
    status: str = "new"
    notes: Optional[str] = None
    search_query: Optional[str] = None
    search_location: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    opportunity_id: Optional[str] = None

    # Scoring
    score: float = 0.0
    tier: str = "cold"
    fit_score: float = 0.0
    intent_score: float = 10.0
    score_updated_at: Optional[datetime] = None
    outreach_attempts: int = 0
    last_outreach_at: Optional[datetime] = None
    email_verified: bool = False
    email_status: str = "unknown"
    company_news: Optional[list] = None
    enriched_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LeadUpdateRequest(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_title: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    activity_sector: Optional[str] = None
    website_url: Optional[str] = None


class LeadsListResponse(BaseModel):
    leads: list[LeadRecord]
    total: int
    page: int
    limit: int


class ScoringConfigSchema(BaseModel):
    id: str
    warm_threshold: float
    hot_threshold: float
    fit_weight: float
    intent_weight: float
    click_score_boost: float
    linkedin_boost: float
    reply_score_boost: float
    webinar_score_boost: float
    meeting_score_boost: float
    max_hot_attempts: int
    cooldown_score_penalty: float
    updated_at: datetime

    class Config:
        from_attributes = True


class ScoringConfigUpdate(BaseModel):
    warm_threshold: Optional[float] = None
    hot_threshold: Optional[float] = None
    fit_weight: Optional[float] = None
    intent_weight: Optional[float] = None
    click_score_boost: Optional[float] = None
    linkedin_boost: Optional[float] = None
    reply_score_boost: Optional[float] = None
    webinar_score_boost: Optional[float] = None
    meeting_score_boost: Optional[float] = None
    max_hot_attempts: Optional[int] = None
    cooldown_score_penalty: Optional[float] = None


class OutreachMessageCreate(BaseModel):
    lead_id: str
    tier: str
    channel: str = "email"
    subject: Optional[str] = None
    message_content: str
    score_before: Optional[float] = None


class OutreachMessageSchema(BaseModel):
    id: str
    lead_id: str
    tier: str
    channel: str
    subject: Optional[str] = None
    message_content: str
    status: str
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    score_before: Optional[float] = None
    score_after: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class OutreachEventRequest(BaseModel):
    event_type: str  # link_clicked | email_replied | webinar_registered | meeting_booked
    message_id: Optional[str] = None
    metadata: Optional[dict] = None


class ScoreEventSchema(BaseModel):
    id: str
    lead_id: str
    event_type: str
    score_delta: float
    score_before: Optional[float]
    score_after: Optional[float]
    event_metadata: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True

    class Config:
        from_attributes = True


class PipelineStats(BaseModel):
    cold_count: int
    warm_count: int
    hot_count: int
    total: int
    cold_pct: float
    warm_pct: float
    hot_pct: float


class AgentRecommendation(BaseModel):
    lead_id: str
    tier: str
    agent_name: str
    action: str
    channel: str
    subject: Optional[str]
    message_content: str
    rationale: str


# ── Export schemas ────────────────────────────────────────────────────────────

class AirtableExportRequest(BaseModel):
    lead_ids: list[str]
    api_key: str
    base_id: str
    table_name: str = "Leads"


class NotionExportRequest(BaseModel):
    lead_ids: list[str]
    token: str
    database_id: str


class ExportResult(BaseModel):
    exported: int
    errors: list[str] = []


class ImportResult(BaseModel):
    imported: int
    errors: list[str] = []


class AirtableImportRequest(BaseModel):
    api_key: str
    base_id: str
    table_name: str = "Leads"


class NotionImportRequest(BaseModel):
    token: str
    database_id: str
