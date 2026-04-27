from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class EmailTemplateCreate(BaseModel):
    name: str
    tier: str = "all"
    subject: str
    body: str
    variables: Optional[list[str]] = None


class EmailTemplateUpdate(BaseModel):
    name: Optional[str] = None
    tier: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    variables: Optional[list[str]] = None


class EmailTemplateSchema(BaseModel):
    id: str
    name: str
    tier: str
    subject: str
    body: str
    variables: Optional[list[str]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
