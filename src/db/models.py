"""
SQLAlchemy 2.0 ORM models.

Design notes (why the schema looks like this):
- One row per pipeline stage (LeadProfile, ScoreResult, OutreachDraft) rather
  than one wide "leads" table with nullable columns for every stage's output.
  This mirrors the agent architecture 1:1 — each agent writes to its own
  table — and makes it trivial to query "how many leads made it past
  scoring but never got a draft" for debugging the pipeline.
- AgentLog is separate from the stage tables on purpose: it's an append-only
  audit trail (every attempt, including failures/retries), while the stage
  tables hold only the current/accepted result. Don't conflate logs with
  state.
- UUID columns use SQLAlchemy 2.0's generic `Uuid` type, not
  `sqlalchemy.dialects.postgresql.UUID`. The generic type compiles to a
  native UUID column on Postgres (prod) but degrades gracefully to a
  CHAR(32) column on SQLite — which is what makes the test suite able to
  run against an in-memory SQLite DB (see tests/conftest.py) instead of
  requiring a real Postgres instance just to run unit tests. Prefer
  dialect-generic types unless a Postgres-only feature is actually needed.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LeadStatus(str, enum.Enum):
    PENDING = "pending"
    RESEARCHED = "researched"
    SCORED = "scored"
    DRAFTED = "drafted"
    GUARDRAIL_FLAGGED = "guardrail_flagged"
    READY = "ready"
    REJECTED = "rejected"  # below score threshold, pipeline stops early — a normal business outcome
    FAILED = "failed"  # technical failure (LLM/tool error) after exhausting retries — needs ops attention


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[LeadStatus] = mapped_column(
        String(30), default=LeadStatus.PENDING, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    profile: Mapped["LeadProfile | None"] = relationship(
        back_populates="lead", uselist=False, cascade="all, delete-orphan"
    )
    score: Mapped["ScoreResult | None"] = relationship(
        back_populates="lead", uselist=False, cascade="all, delete-orphan"
    )
    draft: Mapped["OutreachDraft | None"] = relationship(
        back_populates="lead", uselist=False, cascade="all, delete-orphan"
    )


class LeadProfile(Base):
    """Output of the Research Agent."""
    __tablename__ = "lead_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), unique=True, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    signals_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON: funding, hiring, product signals
    sources_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON: list of URLs used
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    lead: Mapped["Lead"] = relationship(back_populates="profile")


class ScoreResult(Base):
    """Output of the Scoring Agent."""
    __tablename__ = "score_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), unique=True, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-100
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0-1.0
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    lead: Mapped["Lead"] = relationship(back_populates="score")


class OutreachDraft(Base):
    """Output of the Drafting Agent + verdict from the Guardrail Agent."""
    __tablename__ = "outreach_drafts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), unique=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(30), default="email")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    guardrail_approved: Mapped[bool] = mapped_column(default=False)
    guardrail_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    lead: Mapped["Lead"] = relationship(back_populates="draft")


class AgentLog(Base):
    """
    Append-only audit trail of every agent invocation — including retries
    and failures. This is what makes the pipeline explainable and
    debuggable: for any lead, you can reconstruct exactly what each agent
    saw, decided, and how long/much it cost.
    """
    __tablename__ = "agent_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"), nullable=True)
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    input_summary: Mapped[str] = mapped_column(Text, nullable=False)
    output_summary: Mapped[str] = mapped_column(Text, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    success: Mapped[bool] = mapped_column(default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
