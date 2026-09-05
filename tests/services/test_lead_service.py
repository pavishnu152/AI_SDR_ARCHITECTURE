"""
Direct DB-level tests for lead_service.py — the one place that translates
an in-memory PipelineResult into persisted rows. tests/api/test_leads.py
already exercises this indirectly through the API, but only for the happy
(READY) path; here we test the persistence logic itself, including the
REJECTED case where no draft/guardrail output exists — a real edge case
lead_to_out must handle without crashing (a lead can legitimately have no
draft row at all).
"""
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.agents.orchestrator import AgentInvocationRecord, PipelineResult
from src.db.models import AgentLog, Base, LeadProfile, LeadStatus, OutreachDraft, ScoreResult
from src.schemas.lead import DraftOutput, GuardrailVerdict, ResearchOutput, ScoreOutput, Signal
from src.services.lead_service import create_and_run_lead, lead_to_out


def _session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _ready_result() -> PipelineResult:
    return PipelineResult(
        company_name="Acme AI",
        domain="acme.ai",
        status=LeadStatus.READY,
        research_output=ResearchOutput(
            summary="Acme AI raised a Series A and markets an AI copilot.",
            signals=[
                Signal(label="recent_funding", detail="$12M Series A", source_url="https://x"),
                Signal(label="product_ai_mention", detail="AI copilot", source_url="https://y"),
            ],
            sources=["https://x", "https://y"],
        ),
        score_output=ScoreOutput(score=85, confidence=0.8, reasoning="Strong fit."),
        draft_output=DraftOutput(channel="email", message="Congrats on your Series A!"),
        guardrail_output=GuardrailVerdict(approved=True, unsupported_claims=[], notes="ok"),
        invocation_log=[
            AgentInvocationRecord(
                agent_name="research", model="openai/gpt-oss-20b", latency_ms=100,
                success=True, error=None, attempt=1, input_tokens=500, output_tokens=100,
                cost_usd=0.001,
            ),
            AgentInvocationRecord(
                agent_name="scoring", model="openai/gpt-oss-20b", latency_ms=80,
                success=True, error=None, attempt=1, input_tokens=300, output_tokens=50,
                cost_usd=0.0005,
            ),
        ],
        total_latency_ms=500,
    )


def _rejected_result() -> PipelineResult:
    return PipelineResult(
        company_name="Oakridge Furniture Co",
        domain=None,
        status=LeadStatus.REJECTED,
        research_output=ResearchOutput(
            summary="A furniture retailer with no AI signals.", signals=[], sources=[],
        ),
        score_output=ScoreOutput(score=15, confidence=0.9, reasoning="No AI signals found."),
        draft_output=None,
        guardrail_output=None,
        invocation_log=[
            AgentInvocationRecord(
                agent_name="research", model="openai/gpt-oss-20b", latency_ms=90,
                success=True, error=None, attempt=1, cost_usd=0.001,
            ),
        ],
        total_latency_ms=200,
    )


@patch("src.services.lead_service.run_pipeline")
def test_create_and_run_lead_persists_all_stages(mock_run_pipeline):
    mock_run_pipeline.return_value = _ready_result()
    db = _session()

    lead = create_and_run_lead(db, "Acme AI", "acme.ai")

    assert lead.status == LeadStatus.READY.value or lead.status == LeadStatus.READY

    profile = db.query(LeadProfile).filter(LeadProfile.lead_id == lead.id).one()
    assert "Series A" in profile.summary

    score = db.query(ScoreResult).filter(ScoreResult.lead_id == lead.id).one()
    assert score.score == 85

    draft = db.query(OutreachDraft).filter(OutreachDraft.lead_id == lead.id).one()
    assert draft.guardrail_approved is True

    logs = db.query(AgentLog).filter(AgentLog.lead_id == lead.id).all()
    assert len(logs) == 2
    assert {log.agent_name for log in logs} == {"research", "scoring"}
    research_log = next(log for log in logs if log.agent_name == "research")
    assert research_log.input_tokens == 500
    assert research_log.cost_usd == 0.001


@patch("src.services.lead_service.run_pipeline")
def test_lead_to_out_correctly_parses_signals_json(mock_run_pipeline):
    mock_run_pipeline.return_value = _ready_result()
    db = _session()
    lead = create_and_run_lead(db, "Acme AI", "acme.ai")

    out = lead_to_out(lead)

    assert out.profile is not None
    assert len(out.profile.signals) == 2
    assert out.profile.signals[0].label == "recent_funding"
    assert out.profile.sources == ["https://x", "https://y"]


@patch("src.services.lead_service.run_pipeline")
def test_rejected_lead_has_no_draft_row_and_lead_to_out_handles_it(mock_run_pipeline):
    mock_run_pipeline.return_value = _rejected_result()
    db = _session()

    lead = create_and_run_lead(db, "Oakridge Furniture Co")

    assert db.query(OutreachDraft).filter(OutreachDraft.lead_id == lead.id).first() is None

    # This is the important assertion: lead_to_out must not crash when
    # draft/score exist in different combinations — a REJECTED lead has a
    # score but never reaches drafting.
    out = lead_to_out(lead)
    assert out.draft is None
    assert out.score is not None
    assert out.score.score == 15


@patch("src.services.lead_service.run_pipeline")
def test_agent_log_persists_even_for_rejected_lead(mock_run_pipeline):
    mock_run_pipeline.return_value = _rejected_result()
    db = _session()

    lead = create_and_run_lead(db, "Oakridge Furniture Co")

    logs = db.query(AgentLog).filter(AgentLog.lead_id == lead.id).all()
    assert len(logs) == 1
    assert logs[0].agent_name == "research"
