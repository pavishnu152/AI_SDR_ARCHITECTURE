"""
Lead service — the ONLY place that translates the orchestrator's in-memory
PipelineResult into persisted DB rows.

Why this boundary exists (see also schemas/lead.py's module docstring):
agents and the orchestrator are deliberately DB-agnostic — they're plain
functions that take and return Pydantic models, which is what makes them
unit-testable without a database and reusable outside the API (a CLI, a
batch script, a scheduled job). This service module is the translation
layer where "pipeline result" becomes "rows in Lead/LeadProfile/
ScoreResult/OutreachDraft/AgentLog". If we ever swap Postgres for
something else, only this file and db/models.py should need to change.
"""
import json

from sqlalchemy.orm import Session

from src.agents.orchestrator import PipelineResult, run_pipeline
from src.core.logging import get_agent_logger
from src.db.models import AgentLog, Lead, LeadProfile, LeadStatus, OutreachDraft, ScoreResult
from src.schemas.lead import LeadOut, LeadProfileOut, OutreachDraftOut, ScoreResultOut, Signal

logger = get_agent_logger("lead_service")


def create_and_run_lead(db: Session, company_name: str, domain: str | None = None) -> Lead:
    """
    Creates a Lead row, runs the full agent pipeline synchronously, and
    persists every stage's output plus the full agent invocation log.

    Synchronous on purpose for now: see the docstring on POST /leads in
    api/leads.py for why a background task queue is a deliberate, deferred
    decision rather than an oversight.
    """
    lead = Lead(company_name=company_name, domain=domain, status=LeadStatus.PENDING)
    db.add(lead)
    db.commit()
    db.refresh(lead)

    result: PipelineResult = run_pipeline(company_name, domain)
    _persist_pipeline_result(db, lead, result)
    return lead


def _persist_pipeline_result(db: Session, lead: Lead, result: PipelineResult) -> None:
    if result.research_output:
        db.add(
            LeadProfile(
                lead_id=lead.id,
                summary=result.research_output.summary,
                signals_json=json.dumps(
                    [s.model_dump() for s in result.research_output.signals]
                ),
                sources_json=json.dumps(result.research_output.sources),
            )
        )

    if result.score_output:
        db.add(
            ScoreResult(
                lead_id=lead.id,
                score=result.score_output.score,
                confidence=result.score_output.confidence,
                reasoning=result.score_output.reasoning,
            )
        )

    if result.draft_output:
        db.add(
            OutreachDraft(
                lead_id=lead.id,
                channel=result.draft_output.channel,
                message=result.draft_output.message,
                guardrail_approved=bool(
                    result.guardrail_output and result.guardrail_output.approved
                ),
                guardrail_notes=result.guardrail_output.notes if result.guardrail_output else None,
            )
        )

    # Append-only audit trail — every attempt, not just the final outcome.
    # This is what makes the pipeline explainable after the fact: for any
    # lead, you can reconstruct exactly what each agent saw and decided.
    for record in result.invocation_log:
        db.add(
            AgentLog(
                lead_id=lead.id,
                agent_name=record.agent_name,
                model_used=record.model,
                input_summary=record.input_summary or "(not captured)",
                output_summary=record.output_summary or "(not captured)",
                latency_ms=record.latency_ms,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                cost_usd=record.cost_usd,
                success=record.success,
                error=record.error,
            )
        )

    lead.status = result.status
    db.commit()
    db.refresh(lead)

    logger.info(
        "lead pipeline persisted",
        extra={
            "lead_id": str(lead.id),
            "status": lead.status,
            "total_latency_ms": result.total_latency_ms,
            "total_cost_usd": result.total_cost_usd,
            "failure_reason": result.failure_reason,
        },
    )


def lead_to_out(lead: Lead) -> LeadOut:
    """
    Manual ORM -> API schema mapping, not `LeadOut.model_validate(lead,
    from_attributes=True)`. The automatic path breaks here because
    LeadProfile stores `signals_json`/`sources_json` as serialized JSON
    strings (see db/models.py's docstring on why), while LeadProfileOut
    expects real `signals: list[Signal]` — that JSON needs to be parsed by
    hand somewhere, and this function is that one place, kept out of the
    route handlers in api/leads.py to keep them thin.
    """
    profile_out = None
    if lead.profile:
        profile_out = LeadProfileOut(
            lead_id=lead.id,
            summary=lead.profile.summary,
            signals=[Signal(**s) for s in json.loads(lead.profile.signals_json)],
            sources=json.loads(lead.profile.sources_json),
            created_at=lead.profile.created_at,
        )

    score_out = None
    if lead.score:
        score_out = ScoreResultOut(
            lead_id=lead.id,
            score=lead.score.score,
            confidence=lead.score.confidence,
            reasoning=lead.score.reasoning,
            created_at=lead.score.created_at,
        )

    draft_out = None
    if lead.draft:
        draft_out = OutreachDraftOut(
            lead_id=lead.id,
            channel=lead.draft.channel,
            message=lead.draft.message,
            guardrail_approved=lead.draft.guardrail_approved,
            guardrail_notes=lead.draft.guardrail_notes,
            created_at=lead.draft.created_at,
        )

    return LeadOut(
        id=lead.id,
        company_name=lead.company_name,
        domain=lead.domain,
        status=lead.status,
        created_at=lead.created_at,
        profile=profile_out,
        score=score_out,
        draft=draft_out,
    )
