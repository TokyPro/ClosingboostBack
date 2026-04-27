from sqlalchemy import Column, String, Float, ForeignKey, DateTime, JSON, Text, Uuid, Integer, Boolean
from sqlalchemy.orm import relationship
import uuid
import datetime
from ..database import Base

LEAD_STATUSES = ("new", "contacted", "qualified", "converted", "rejected")

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="executive")  # admin, executive
    status = Column(String, default="active")   # active, pending
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.timezone.utc))

    opportunities = relationship("Opportunity", back_populates="owner")

class Opportunity(Base):
    __tablename__ = "opportunities"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    company_name = Column(String, nullable=False)
    # creation, qualification, first_meeting, waiting_signature, signed, quote_needed, offer_sent
    stage = Column(String, default="creation")
    value = Column(Float, default=0.0)
    win_probability = Column(Float, default=0.0)
    priority = Column(String, default="medium")  # high, medium, low
    owner_id = Column(String, ForeignKey("users.id"))

    # Contact details
    contact_name = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    meeting_date = Column(DateTime, nullable=True)

    # Sync IDs
    notion_id = Column(String, nullable=True, index=True)
    airtable_id = Column(String, nullable=True, index=True)

    owner = relationship("User", back_populates="opportunities")
    briefing = relationship("Briefing", back_populates="opportunity", uselist=False)
    interactions = relationship("Interaction", back_populates="opportunity")
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.timezone.utc))

class Interaction(Base):
    __tablename__ = "interactions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    opportunity_id = Column(String, ForeignKey("opportunities.id"), nullable=False)
    type = Column(String, default="visit")  # visit, call, email, meeting
    summary = Column(Text, nullable=True)
    raw_transcript = Column(Text, nullable=True)
    requirements = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    opportunity = relationship("Opportunity", back_populates="interactions")

class Briefing(Base):
    __tablename__ = "briefings"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    opportunity_id = Column(String, ForeignKey("opportunities.id"), unique=True)
    ai_strategy = Column(Text)
    ai_risk_assessment = Column(Text)
    market_insights = Column(JSON)
    buyer_persona = Column(Text, nullable=True)
    value_prop_alignment = Column(Text, nullable=True)
    raw_notes = Column(Text)

    opportunity = relationship("Opportunity", back_populates="briefing")
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.timezone.utc))

class Lead(Base):
    __tablename__ = "leads"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Company
    company_name = Column(String, nullable=True)
    activity_sector = Column(String, nullable=True)
    website_url = Column(String, nullable=True)

    # Contact person
    contact_name = Column(String, nullable=True)
    contact_title = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)

    # Source
    linkedin_url = Column(String, nullable=True, index=True)
    source = Column(String, default="web")          # linkedin_profile | linkedin_company | web

    # Lead details
    location = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    relevance_score = Column(Float, default=0.0)

    # Management
    status = Column(String, default="new", index=True)  # new | contacted | qualified | converted | rejected
    notes = Column(Text, nullable=True)

    # Sync IDs
    notion_id = Column(String, nullable=True, index=True)
    airtable_id = Column(String, nullable=True, index=True)

    # Search context (kept for traceability)
    search_query = Column(String, nullable=True)
    search_location = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Link to opportunity once converted
    opportunity_id = Column(String, ForeignKey("opportunities.id"), nullable=True)
    opportunity = relationship("Opportunity", foreign_keys=[opportunity_id])

    # Scoring workflow fields
    score = Column(Float, default=0.0)
    tier = Column(String, default="cold", index=True)  # cold | warm | hot
    fit_score = Column(Float, default=0.0)
    intent_score = Column(Float, default=10.0)
    score_updated_at = Column(DateTime, nullable=True)
    outreach_attempts = Column(Integer, default=0)
    last_outreach_at = Column(DateTime, nullable=True)
    email_verified = Column(Boolean, default=False)
    email_status = Column(String, default="unknown")  # valid | invalid | unknown
    company_news = Column(JSON, nullable=True)
    enriched_at = Column(DateTime, nullable=True)

    score_events = relationship("ScoreEvent", back_populates="lead", cascade="all, delete-orphan")
    outreach_messages = relationship("OutreachMessage", back_populates="lead", cascade="all, delete-orphan")


class ScoringConfig(Base):
    __tablename__ = "scoring_configs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    warm_threshold = Column(Float, default=30.0)
    hot_threshold = Column(Float, default=70.0)
    fit_weight = Column(Float, default=0.4)
    intent_weight = Column(Float, default=0.6)
    click_score_boost = Column(Float, default=20.0)
    linkedin_boost = Column(Float, default=25.0)
    reply_score_boost = Column(Float, default=30.0)
    webinar_score_boost = Column(Float, default=40.0)
    meeting_score_boost = Column(Float, default=50.0)
    max_hot_attempts = Column(Integer, default=3)
    cooldown_score_penalty = Column(Float, default=30.0)
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))


class OutreachMessage(Base):
    __tablename__ = "outreach_messages"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    lead_id = Column(String, ForeignKey("leads.id"), nullable=False)
    tier = Column(String, nullable=False)
    channel = Column(String, default="email")
    subject = Column(String, nullable=True)
    message_content = Column(Text, nullable=False)
    status = Column(String, default="draft")  # draft | sent | opened | clicked | replied
    sent_at = Column(DateTime, nullable=True)
    opened_at = Column(DateTime, nullable=True)
    clicked_at = Column(DateTime, nullable=True)
    replied_at = Column(DateTime, nullable=True)
    score_before = Column(Float, nullable=True)
    score_after = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    lead = relationship("Lead", back_populates="outreach_messages")


class ScoreEvent(Base):
    __tablename__ = "score_events"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    lead_id = Column(String, ForeignKey("leads.id"), nullable=False)
    event_type = Column(String, nullable=False)
    score_delta = Column(Float, default=0.0)
    score_before = Column(Float, nullable=True)
    score_after = Column(Float, nullable=True)
    event_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    lead = relationship("Lead", back_populates="score_events")


class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    original_name = Column(String, nullable=False)
    category = Column(String, default="general")  # core_methodology | market_intelligence | sales_enablement | general
    status = Column(String, default="synced")      # pending | indexing | synced | error
    file_size = Column(Integer, nullable=True)
    local_path = Column(String, nullable=True)     # relative path under uploads/
    mime_type = Column(String, nullable=True)
    google_file_id = Column(String, nullable=True) # Google File API resource name
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
