"""
Shared types between the current LangGraph orchestrator (orchestrator.py)
and the frozen hand-rolled reference implementation (orchestrator_legacy.py).

These were originally defined once in the hand-rolled orchestrator. When
Milestone 10 refactored the *execution engine* to LangGraph, the *data
shapes* (what a pipeline run returns, what one agent invocation attempt
looks like) didn't need to change at all — that's the whole point of the
refactor (see orchestrator.py's module docstring). Extracting them here,
rather than having orchestrator.py import from orchestrator_legacy.py,
keeps the legacy file genuinely frozen and self-contained as a historical
reference, with no live code depending on it.
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.core.logging import get_agent_logger
from src.db.models import LeadStatus
from src.schemas.lead import DraftOutput, GuardrailVerdict, ResearchOutput, ScoreOutput

logger = get_agent_logger("orchestrator")


@dataclass
class AgentInvocationRecord:
    """One entry per agent call attempt — this is what the service layer
    persists into the AgentLog table for full traceability."""
    agent_name: str
    model: str
    latency_ms: int
    success: bool
    error: str | None
    attempt: int
    input_summary: str = ""
    output_summary: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None


@dataclass
class PipelineResult:
    company_name: str
    domain: str | None
    status: LeadStatus
    research_output: ResearchOutput | None = None
    score_output: ScoreOutput | None = None
    draft_output: DraftOutput | None = None
    guardrail_output: GuardrailVerdict | None = None
    invocation_log: list[AgentInvocationRecord] = field(default_factory=list)
    total_latency_ms: int = 0
    failure_reason: str | None = None

    @property
    def total_cost_usd(self) -> float | None:
        """
        Sums cost across every agent call in this pipeline run (including
        failed/retried attempts — they still cost tokens). Returns None if
        ANY call's cost is unknown (e.g. an unrecognized model), rather
        than silently under-reporting total spend as a partial sum.
        """
        costs = [r.cost_usd for r in self.invocation_log]
        if any(c is None for c in costs):
            return None
        return sum(costs)


def call_with_retry(
    agent_name: str,
    call: Callable[[], Any],
    invocation_log: list[AgentInvocationRecord],
    max_retries: int,
) -> Any:
    """
    Runs `call()` up to (max_retries + 1) times, logging every attempt.
    Returns the last result regardless of success — the caller decides
    what a final failure means for pipeline status.
    """
    result = None
    for attempt in range(1, max_retries + 2):
        result = call()
        invocation_log.append(
            AgentInvocationRecord(
                agent_name=agent_name,
                model=getattr(result, "model", "n/a"),
                latency_ms=getattr(result, "latency_ms", 0),
                success=result.success,
                error=result.error,
                attempt=attempt,
                input_summary=getattr(result, "raw_input_summary", ""),
                output_summary=getattr(result, "raw_output_summary", ""),
                input_tokens=getattr(result, "input_tokens", 0),
                output_tokens=getattr(result, "output_tokens", 0),
                cost_usd=getattr(result, "cost_usd", None),
            )
        )
        if result.success:
            return result
        logger.warning(
            "agent attempt failed",
            extra={"agent_name": agent_name, "attempt": attempt, "error": result.error},
        )
    return result
