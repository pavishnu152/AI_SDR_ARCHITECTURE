"""
Tests for the Orchestrator's state machine logic.

Note the testing strategy: we mock the AGENT FUNCTIONS (research_company,
score_lead, draft_outreach, check_draft), not the Anthropic client. Each
agent already has its own unit tests covering its internal LLM-calling
logic (test_research_agent.py, test_scoring_agent.py, etc.) — re-mocking
the LLM here would just duplicate that coverage while making these tests
harder to read. The orchestrator's job is sequencing and state transitions,
so that's exactly what these tests exercise, at the layer directly below it.
"""
from unittest.mock import MagicMock, patch

import pytest

from src.agents.drafting_agent import DraftingAgentResult
from src.agents.guardrail_agent import GuardrailAgentResult
from src.agents.orchestrator import run_pipeline
from src.agents.research_agent import ResearchAgentResult
from src.agents.scoring_agent import ScoringAgentResult
from src.core.icp import get_icp_config
from src.db.models import LeadStatus
from src.schemas.lead import DraftOutput, GuardrailVerdict, ResearchOutput, ScoreOutput, Signal

ICP = get_icp_config()  # loads the real configs/icp_ai_native_b2b.yaml


def _research_ok(**kwargs):
    output = ResearchOutput(
        summary="Acme AI raised a Series A and markets an AI copilot.",
        signals=[Signal(label="recent_funding", detail="$12M Series A", source_url="https://x")],
        sources=["https://x"],
    )
    return ResearchAgentResult(
        success=True, output=output, model="claude-haiku-4-5-20251001",
        latency_ms=100, turns_used=2, input_tokens=1000, output_tokens=200, cost_usd=0.002,
    )


def _research_fail(error="search backend down"):
    return ResearchAgentResult(
        success=False, output=None, model="claude-haiku-4-5-20251001",
        latency_ms=50, turns_used=1, error=error,
    )


def _score(value: int):
    output = ScoreOutput(score=value, confidence=0.8, reasoning="Based on funding signal.")
    return ScoringAgentResult(
        success=True, output=output, model="claude-haiku-4-5-20251001", latency_ms=80,
        input_tokens=400, output_tokens=60, cost_usd=0.0007,
    )


def _draft_ok():
    output = DraftOutput(channel="email", message="Congrats on your $12M Series A!")
    return DraftingAgentResult(
        success=True, output=output, model="claude-sonnet-5", latency_ms=200,
        input_tokens=300, output_tokens=100, cost_usd=0.0016,
    )


def _guardrail(approved: bool, claims=None):
    output = GuardrailVerdict(
        approved=approved, unsupported_claims=claims or [], notes="checked against research"
    )
    return GuardrailAgentResult(
        success=True, output=output, model="claude-sonnet-5", latency_ms=150,
        input_tokens=350, output_tokens=90, cost_usd=0.0016,
    )


@patch("src.agents.orchestrator.check_draft")
@patch("src.agents.orchestrator.draft_outreach")
@patch("src.agents.orchestrator.score_lead")
@patch("src.agents.orchestrator.research_company")
def test_pipeline_happy_path_reaches_ready(mock_research, mock_score, mock_draft, mock_guardrail):
    mock_research.return_value = _research_ok()
    mock_score.return_value = _score(85)
    mock_draft.return_value = _draft_ok()
    mock_guardrail.return_value = _guardrail(approved=True)

    result = run_pipeline("Acme AI", icp=ICP, client=MagicMock())

    assert result.status == LeadStatus.READY
    assert [r.agent_name for r in result.invocation_log] == [
        "research", "scoring", "drafting", "guardrail",
    ]
    assert all(r.attempt == 1 for r in result.invocation_log)

    # total_cost_usd sums every stage's cost — this is what the eval
    # harness and AgentLog rely on to report $/lead.
    assert result.total_cost_usd == pytest.approx(0.002 + 0.0007 + 0.0016 + 0.0016)


@patch("src.agents.orchestrator.check_draft")
@patch("src.agents.orchestrator.draft_outreach")
@patch("src.agents.orchestrator.score_lead")
@patch("src.agents.orchestrator.research_company")
def test_pipeline_total_cost_is_none_if_any_stage_cost_unknown(
    mock_research, mock_score, mock_draft, mock_guardrail
):
    unknown_cost_research = _research_ok()
    unknown_cost_research.cost_usd = None  # e.g. an unrecognized model
    mock_research.return_value = unknown_cost_research
    mock_score.return_value = _score(85)
    mock_draft.return_value = _draft_ok()
    mock_guardrail.return_value = _guardrail(approved=True)

    result = run_pipeline("Acme AI", icp=ICP, client=MagicMock())

    assert result.total_cost_usd is None


@patch("src.agents.orchestrator.check_draft")
@patch("src.agents.orchestrator.draft_outreach")
@patch("src.agents.orchestrator.score_lead")
@patch("src.agents.orchestrator.research_company")
def test_pipeline_rejects_low_score_without_drafting(
    mock_research, mock_score, mock_draft, mock_guardrail
):
    mock_research.return_value = _research_ok()
    mock_score.return_value = _score(20)  # below reject threshold (40)

    result = run_pipeline("Acme AI", icp=ICP, client=MagicMock())

    assert result.status == LeadStatus.REJECTED
    mock_draft.assert_not_called()
    mock_guardrail.assert_not_called()


@patch("src.agents.orchestrator.check_draft")
@patch("src.agents.orchestrator.draft_outreach")
@patch("src.agents.orchestrator.score_lead")
@patch("src.agents.orchestrator.research_company")
def test_pipeline_self_corrects_after_guardrail_rejection(
    mock_research, mock_score, mock_draft, mock_guardrail
):
    mock_research.return_value = _research_ok()
    mock_score.return_value = _score(85)
    mock_draft.return_value = _draft_ok()
    mock_guardrail.side_effect = [
        _guardrail(approved=False, claims=["$50M Series C"]),
        _guardrail(approved=True),
    ]

    result = run_pipeline("Acme AI", icp=ICP, client=MagicMock())

    assert result.status == LeadStatus.READY
    assert mock_draft.call_count == 2
    assert mock_guardrail.call_count == 2
    agent_names = [r.agent_name for r in result.invocation_log]
    assert "drafting_revision" in agent_names
    assert "guardrail_recheck" in agent_names

    # The revision call must include the feedback from the rejected attempt.
    _, revision_kwargs = mock_draft.call_args_list[1]
    assert revision_kwargs["guardrail_feedback"] == ["$50M Series C"]


@patch("src.agents.orchestrator.check_draft")
@patch("src.agents.orchestrator.draft_outreach")
@patch("src.agents.orchestrator.score_lead")
@patch("src.agents.orchestrator.research_company")
def test_pipeline_flags_when_revision_still_rejected(
    mock_research, mock_score, mock_draft, mock_guardrail
):
    mock_research.return_value = _research_ok()
    mock_score.return_value = _score(85)
    mock_draft.return_value = _draft_ok()
    mock_guardrail.side_effect = [
        _guardrail(approved=False, claims=["claim A"]),
        _guardrail(approved=False, claims=["claim A still there"]),
    ]

    result = run_pipeline("Acme AI", icp=ICP, client=MagicMock())

    assert result.status == LeadStatus.GUARDRAIL_FLAGGED


@patch("src.agents.orchestrator.check_draft")
@patch("src.agents.orchestrator.draft_outreach")
@patch("src.agents.orchestrator.score_lead")
@patch("src.agents.orchestrator.research_company")
def test_pipeline_flags_when_recheck_itself_technically_fails(
    mock_research, mock_score, mock_draft, mock_guardrail
):
    """
    Distinct from both other GUARDRAIL_FLAGGED tests: here the revision
    draft succeeds, but the guardrail_recheck LLM call itself fails (e.g.
    a transient API error), not just "still not approved". The recheck
    node must not touch guardrail_output in this case — it should keep the
    original rejected verdict so routing still correctly falls through to
    mark_flagged, rather than crashing on a missing guardrail_output.
    """
    mock_research.return_value = _research_ok()
    mock_score.return_value = _score(85)
    mock_draft.return_value = _draft_ok()
    mock_guardrail.side_effect = [
        _guardrail(approved=False, claims=["claim A"]),
        GuardrailAgentResult(
            success=False, output=None, model="claude-sonnet-5", latency_ms=50,
            error="LLM call failed: connection reset",
        ),
    ]

    result = run_pipeline("Acme AI", icp=ICP, client=MagicMock(), max_retries=0)

    assert result.status == LeadStatus.GUARDRAIL_FLAGGED
    assert mock_guardrail.call_count == 2


@patch("src.agents.orchestrator.check_draft")
@patch("src.agents.orchestrator.draft_outreach")
@patch("src.agents.orchestrator.score_lead")
@patch("src.agents.orchestrator.research_company")
def test_pipeline_fails_after_research_exhausts_retries(
    mock_research, mock_score, mock_draft, mock_guardrail
):
    mock_research.side_effect = [_research_fail(), _research_fail()]

    result = run_pipeline("Acme AI", icp=ICP, client=MagicMock(), max_retries=1)

    assert result.status == LeadStatus.FAILED
    assert "research failed" in result.failure_reason
    assert mock_research.call_count == 2
    mock_score.assert_not_called()


@patch("src.agents.orchestrator.check_draft")
@patch("src.agents.orchestrator.draft_outreach")
@patch("src.agents.orchestrator.score_lead")
@patch("src.agents.orchestrator.research_company")
def test_pipeline_recovers_when_retry_succeeds(
    mock_research, mock_score, mock_draft, mock_guardrail
):
    mock_research.side_effect = [_research_fail(), _research_ok()]
    mock_score.return_value = _score(85)
    mock_draft.return_value = _draft_ok()
    mock_guardrail.return_value = _guardrail(approved=True)

    result = run_pipeline("Acme AI", icp=ICP, client=MagicMock(), max_retries=1)

    assert result.status == LeadStatus.READY
    research_records = [r for r in result.invocation_log if r.agent_name == "research"]
    assert len(research_records) == 2
    assert research_records[0].success is False
    assert research_records[1].success is True


@patch("src.agents.orchestrator.check_draft")
@patch("src.agents.orchestrator.draft_outreach")
@patch("src.agents.orchestrator.score_lead")
@patch("src.agents.orchestrator.research_company")
def test_pipeline_fails_closed_when_guardrail_itself_errors(
    mock_research, mock_score, mock_draft, mock_guardrail
):
    mock_research.return_value = _research_ok()
    mock_score.return_value = _score(85)
    mock_draft.return_value = _draft_ok()
    mock_guardrail.return_value = GuardrailAgentResult(
        success=False, output=None, model="claude-sonnet-5", latency_ms=50,
        error="LLM call failed: connection reset",
    )

    result = run_pipeline("Acme AI", icp=ICP, client=MagicMock(), max_retries=0)

    assert result.status == LeadStatus.FAILED
    assert "guardrail check failed" in result.failure_reason


@patch("src.agents.orchestrator.check_draft")
@patch("src.agents.orchestrator.draft_outreach")
@patch("src.agents.orchestrator.score_lead")
@patch("src.agents.orchestrator.research_company")
def test_pipeline_fails_when_scoring_exhausts_retries(
    mock_research, mock_score, mock_draft, mock_guardrail
):
    mock_research.return_value = _research_ok()
    mock_score.return_value = ScoringAgentResult(
        success=False, output=None, model="claude-haiku-4-5-20251001", latency_ms=50,
        error="LLM call failed: rate limited",
    )

    result = run_pipeline("Acme AI", icp=ICP, client=MagicMock(), max_retries=0)

    assert result.status == LeadStatus.FAILED
    assert "scoring failed" in result.failure_reason
    mock_draft.assert_not_called()
    mock_guardrail.assert_not_called()


@patch("src.agents.orchestrator.check_draft")
@patch("src.agents.orchestrator.draft_outreach")
@patch("src.agents.orchestrator.score_lead")
@patch("src.agents.orchestrator.research_company")
def test_pipeline_fails_when_drafting_exhausts_retries(
    mock_research, mock_score, mock_draft, mock_guardrail
):
    mock_research.return_value = _research_ok()
    mock_score.return_value = _score(85)
    mock_draft.return_value = DraftingAgentResult(
        success=False, output=None, model="claude-sonnet-5", latency_ms=50,
        error="LLM call failed: timeout",
    )

    result = run_pipeline("Acme AI", icp=ICP, client=MagicMock(), max_retries=0)

    assert result.status == LeadStatus.FAILED
    assert "drafting failed" in result.failure_reason
    mock_guardrail.assert_not_called()


@patch("src.agents.orchestrator.check_draft")
@patch("src.agents.orchestrator.draft_outreach")
@patch("src.agents.orchestrator.score_lead")
@patch("src.agents.orchestrator.research_company")
def test_pipeline_flags_when_revision_draft_itself_fails(
    mock_research, mock_score, mock_draft, mock_guardrail
):
    """
    Distinct from test_pipeline_flags_when_revision_still_rejected: here the
    revision draft call fails technically (API error), not just gets
    rejected again by the guardrail. Same GUARDRAIL_FLAGGED outcome either
    way — a failed self-correction attempt is still not safe to auto-send —
    but this exercises a different branch in orchestrator.py (the `else`
    after `if revision_result.success`).
    """
    mock_research.return_value = _research_ok()
    mock_score.return_value = _score(85)
    mock_draft.side_effect = [
        _draft_ok(),  # initial draft
        DraftingAgentResult(  # revision attempt fails technically
            success=False, output=None, model="claude-sonnet-5", latency_ms=50,
            error="LLM call failed: timeout",
        ),
    ]
    mock_guardrail.return_value = _guardrail(approved=False, claims=["unsupported claim"])

    result = run_pipeline("Acme AI", icp=ICP, client=MagicMock(), max_retries=0)

    assert result.status == LeadStatus.GUARDRAIL_FLAGGED
    assert mock_draft.call_count == 2
    mock_guardrail.assert_called_once()  # recheck never happens if revision itself failed
