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


class ResearchOutput(BaseModel):
    """
    Raw structured output of the Research Agent, before it's tied to a
    persisted Lead row. Kept separate from LeadProfileOut (below) because
    the agent produces this in-memory, mid-pipeline — it doesn't have a
    lead_id or created_at until the service layer persists it.
    """
    summary: str
    signals: list[Signal]
    sources: list[str]


class LeadProfileOut(ResearchOutput):
    """Persisted form of ResearchOutput — what the API returns."""
    lead_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class ScoreOutput(BaseModel):
    """
    Raw structured output of the Scoring Agent, before persistence — mirrors
    the ResearchOutput/LeadProfileOut split above and for the same reason.
    """
    score: int = Field(..., ge=0, le=100)
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str


class ScoreResultOut(ScoreOutput):
    """Persisted form of ScoreOutput — what the API returns."""
    lead_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class DraftOutput(BaseModel):
    """Raw structured output of the Drafting Agent, before persistence."""
    channel: str
    message: str


class GuardrailVerdict(BaseModel):
    """
    Raw structured output of the Guardrail Agent: an independent fact-check
    of a DraftOutput against the ResearchOutput it was based on.
    """
    approved: bool
    unsupported_claims: list[str] = Field(
        default_factory=list,
        description="Specific claims in the draft that could NOT be traced to a research signal.",
    )
    notes: str


class OutreachDraftOut(DraftOutput):
    """Persisted form of DraftOutput + the Guardrail Agent's verdict."""
    lead_id: uuid.UUID
    guardrail_approved: bool
    guardrail_notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentLogOut(BaseModel):
    """
    One row of the append-only agent invocation audit trail (AgentLog in
    db/models.py) — every attempt, including retries and failures, not just
    the final accepted result per stage. This is what the frontend's agent
    trace viewer renders: for any lead, exactly what each agent saw,
    decided, how long it took, and what it cost.
    """
    agent_name: str
    model_used: str
    input_summary: str
    output_summary: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    success: bool
    error: str | None
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
