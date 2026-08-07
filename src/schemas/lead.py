"""
Pydantic schemas — the structured I/O contracts between agents, and between
the API and the outside world.

Why these are separate from the SQLAlchemy models in db/models.py: coupling
your API/agent contracts directly to your ORM models is a common mistake —
it means a DB migration can silently change your API response shape, and it
makes it awkward to have fields that exist only in-flight (e.g. an agent's
raw LLM output before it's been validated/persisted). Two layers, one clear
translation point (the service layer, built in a later milestone).
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LeadCreate(BaseModel):
    """Input: what a user submits to kick off the pipeline for one lead."""
    company_name: str = Field(..., min_length=1, max_length=255)
    domain: str | None = None


class Signal(BaseModel):
    """One piece of evidence the Research Agent found, with its source."""
    label: str  # e.g. "recent_funding", "ai_job_postings", "product_ai_mention"
    detail: str
    source_url: str | None = None


class LeadProfileOut(BaseModel):
    """Structured output of the Research Agent."""
    lead_id: uuid.UUID
    summary: str
    signals: list[Signal]
    sources: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ScoreResultOut(BaseModel):
    """Structured output of the Scoring Agent."""
    lead_id: uuid.UUID
    score: int = Field(..., ge=0, le=100)
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OutreachDraftOut(BaseModel):
    """Structured output of the Drafting Agent + Guardrail Agent verdict."""
    lead_id: uuid.UUID
    channel: str
    message: str
    guardrail_approved: bool
    guardrail_notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LeadOut(BaseModel):
    """Full pipeline state for a lead, as returned by the API."""
    id: uuid.UUID
    company_name: str
    domain: str | None
    status: str
    created_at: datetime
    profile: LeadProfileOut | None = None
    score: ScoreResultOut | None = None
    draft: OutreachDraftOut | None = None

    model_config = {"from_attributes": True}
