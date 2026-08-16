"""
Orchestrator — LangGraph implementation.

Milestone 6 built this pipeline as a hand-rolled state machine (preserved,
frozen, at src/agents/orchestrator_legacy.py) specifically so the
tool-calling loop, retries, and state transitions were fully understood
before adopting a framework that abstracts them away. This file is the
Milestone 10 refactor to LangGraph — see
docs/milestone10-langgraph-refactor.md for the full before/after writeup,
including what LangGraph buys us, what it costs, and one deliberate
divergence (retries) explained below.

PUBLIC API IS UNCHANGED: `run_pipeline()`, `PipelineResult`, and
`AgentInvocationRecord` have the identical signature and shape as the
hand-rolled version. This is the point of the exercise — every existing
test in tests/agents/test_orchestrator.py, tests/services/, and
tests/api/test_leads.py passes UNMODIFIED against this new implementation,
which is the real proof the refactor didn't change behavior, not just a
claim in a docstring.

Graph structure (mirrors the hand-rolled version's control flow exactly):

    START -> research -[failed]-> END
                      -[ok]-> scoring -[failed]-> END
                                      -[score <= reject]-> reject_lead -> END
                                      -[ok]-> drafting -[failed]-> END
                                                        -[ok]-> guardrail -[failed]-> END (fail closed)
                                                                          -[approved]-> mark_ready -> END
                                                                          -[rejected]-> drafting_revision
                                                                                          -[failed]-> mark_flagged -> END
                                                                                          -[ok]-> guardrail_recheck
                                                                                                    -[approved]-> mark_ready -> END
                                                                                                    -[else]-> mark_flagged -> END

Key design decision — retries stay manual, NOT LangGraph's native
RetryPolicy: LangGraph's `add_node(..., retry_policy=...)` only retries a
node when it *raises an exception*. Our agent functions (research_company,
score_lead, etc.) deliberately never raise on failure — they return a
Result object with success/error, specifically so every attempt (including
failed ones) can be logged to AgentInvocationRecord for the AgentLog audit
trail (see architecture.md's explainability requirement). Switching to
exception-based retries would mean losing that per-attempt log unless we
also added exception handling back around it — more code, not less, for
strictly worse observability. So each node still calls the shared
`call_with_retry` helper (orchestrator_types.py, used by both this file
and the frozen legacy one) internally; only the *graph structure and
routing* is LangGraph's job here, not retry mechanics. This is a real,
defensible tradeoff, not an oversight — see the docs file for the full
comparison including when native RetryPolicy WOULD be the better choice.

Simplification worth naming: runtime dependencies (the Anthropic client,
ICPConfig, tool_impls) are carried directly in the graph's state dict
rather than routed through LangGraph's separate context/config mechanism.
That's fine here because this graph runs in-memory with no checkpointer —
nothing ever needs to serialize this state to disk or across a process
boundary. If persistence/checkpointing were added later, these would need
to move to context instead, since checkpointed state must be serializable
and a live client object isn't.
"""
import operator
import time
from typing import Annotated, TypedDict

import anthropic
from langgraph.graph import END, START, StateGraph

from src.agents.drafting_agent import DraftingAgentResult, draft_outreach
from src.agents.guardrail_agent import GuardrailAgentResult, check_draft
from src.agents.orchestrator_types import AgentInvocationRecord, PipelineResult, call_with_retry
from src.agents.research_agent import ResearchAgentResult, research_company
from src.agents.scoring_agent import ScoringAgentResult, score_lead
from src.core.config import get_settings
from src.core.icp import ICPConfig, get_icp_config
from src.core.logging import get_agent_logger
from src.db.models import LeadStatus
from src.schemas.lead import DraftOutput, GuardrailVerdict, ResearchOutput, ScoreOutput

logger = get_agent_logger("orchestrator")

DEFAULT_MAX_RETRIES = 1  # 1 retry = 2 attempts total per stage

# Re-exported so callers (lead_service.py, tests) can keep importing these
# from src.agents.orchestrator exactly as before — only the execution
# engine underneath changed, not the public data shapes.
__all__ = ["DEFAULT_MAX_RETRIES", "AgentInvocationRecord", "PipelineResult", "run_pipeline"]


class PipelineState(TypedDict, total=False):
    # --- Inputs / runtime deps, constant for the life of one run ---
    company_name: str
    domain: str | None
    icp: ICPConfig
    client: "anthropic.Anthropic"
    research_tool_impls: dict | None
    max_retries: int

    # --- Accumulated across every node via the operator.add reducer ---
    invocation_log: Annotated[list[AgentInvocationRecord], operator.add]

    # --- Set once by their respective stage ---
    research_output: ResearchOutput | None
    score_output: ScoreOutput | None
    draft_output: DraftOutput | None
    guardrail_output: GuardrailVerdict | None

    # --- Final outcome ---
    status: LeadStatus | None
    failure_reason: str | None
    revision_draft_failed: bool


def _research_node(state: PipelineState) -> dict:
    log: list[AgentInvocationRecord] = []
    result: ResearchAgentResult = call_with_retry(
        "research",
        lambda: research_company(
            state["company_name"],
            state["domain"],
            client=state["client"],
            tool_impls=state["research_tool_impls"],
        ),
        log,
        state["max_retries"],
    )
    if not result.success:
        return {
            "invocation_log": log,
            "status": LeadStatus.FAILED,
            "failure_reason": f"research failed: {result.error}",
        }
    return {"invocation_log": log, "research_output": result.output}


def _route_after_research(state: PipelineState) -> str:
    return END if state.get("status") == LeadStatus.FAILED else "scoring"


def _scoring_node(state: PipelineState) -> dict:
    log: list[AgentInvocationRecord] = []
    result: ScoringAgentResult = call_with_retry(
        "scoring",
        lambda: score_lead(state["research_output"], state["icp"], client=state["client"]),
        log,
        state["max_retries"],
    )
    if not result.success:
        return {
            "invocation_log": log,
            "status": LeadStatus.FAILED,
            "failure_reason": f"scoring failed: {result.error}",
        }
    return {"invocation_log": log, "score_output": result.output}


def _route_after_scoring(state: PipelineState) -> str:
    if state.get("status") == LeadStatus.FAILED:
        return END
    icp = state["icp"]
    if state["score_output"].score <= icp.score_thresholds.reject:
        return "reject_lead"
    return "drafting"


def _reject_lead_node(state: PipelineState) -> dict:
    logger.info(
        "lead rejected by score gate, skipping drafting",
        extra={
            "score": state["score_output"].score,
            "reject_threshold": state["icp"].score_thresholds.reject,
        },
    )
    return {"status": LeadStatus.REJECTED}


def _drafting_node(state: PipelineState) -> dict:
    log: list[AgentInvocationRecord] = []
    result: DraftingAgentResult = call_with_retry(
        "drafting",
        lambda: draft_outreach(
            state["company_name"], state["research_output"], state["score_output"],
            client=state["client"],
        ),
        log,
        state["max_retries"],
    )
    if not result.success:
        return {
            "invocation_log": log,
            "status": LeadStatus.FAILED,
            "failure_reason": f"drafting failed: {result.error}",
        }
    return {"invocation_log": log, "draft_output": result.output}


def _route_after_drafting(state: PipelineState) -> str:
    return END if state.get("status") == LeadStatus.FAILED else "guardrail"


def _guardrail_node(state: PipelineState) -> dict:
    log: list[AgentInvocationRecord] = []
    result: GuardrailAgentResult = call_with_retry(
        "guardrail",
        lambda: check_draft(state["research_output"], state["draft_output"], client=state["client"]),
        log,
        state["max_retries"],
    )
    if not result.success:
        # Fail closed: the guardrail itself couldn't run, so we can't
        # confirm the draft is safe. Never default to READY here.
        return {
            "invocation_log": log,
            "status": LeadStatus.FAILED,
            "failure_reason": f"guardrail check failed: {result.error}",
        }
    return {"invocation_log": log, "guardrail_output": result.output}


def _route_after_guardrail(state: PipelineState) -> str:
    if state.get("status") == LeadStatus.FAILED:
        return END
    if state["guardrail_output"].approved:
        return "mark_ready"
    logger.info(
        "guardrail rejected draft, attempting one self-correction",
        extra={"unsupported_claims": state["guardrail_output"].unsupported_claims},
    )
    return "drafting_revision"


def _mark_ready_node(state: PipelineState) -> dict:
    return {"status": LeadStatus.READY}


def _drafting_revision_node(state: PipelineState) -> dict:
    log: list[AgentInvocationRecord] = []
    result: DraftingAgentResult = call_with_retry(
        "drafting_revision",
        lambda: draft_outreach(
            state["company_name"], state["research_output"], state["score_output"],
            client=state["client"],
            guardrail_feedback=state["guardrail_output"].unsupported_claims,
        ),
        log,
        max_retries=0,  # bounded — a self-correction attempt, not a retry budget
    )
    if not result.success:
        return {"invocation_log": log, "revision_draft_failed": True}
    return {"invocation_log": log, "draft_output": result.output, "revision_draft_failed": False}


def _route_after_revision(state: PipelineState) -> str:
    return "mark_flagged" if state.get("revision_draft_failed") else "guardrail_recheck"


def _guardrail_recheck_node(state: PipelineState) -> dict:
    log: list[AgentInvocationRecord] = []
    result: GuardrailAgentResult = call_with_retry(
        "guardrail_recheck",
        lambda: check_draft(state["research_output"], state["draft_output"], client=state["client"]),
        log,
        max_retries=0,
    )
    if not result.success:
        # Recheck itself failed technically — deliberately do NOT touch
        # guardrail_output here. It still holds the original rejected
        # verdict, which is exactly what _route_after_recheck needs to
        # correctly fall through to mark_flagged below.
        return {"invocation_log": log}
    return {"invocation_log": log, "guardrail_output": result.output}


def _route_after_recheck(state: PipelineState) -> str:
    verdict = state.get("guardrail_output")
    if verdict is not None and verdict.approved:
        return "mark_ready"
    # Either the recheck itself failed, or the revised draft was STILL
    # rejected — either way, this needs a human, not an auto-send.
    return "mark_flagged"


def _mark_flagged_node(state: PipelineState) -> dict:
    return {"status": LeadStatus.GUARDRAIL_FLAGGED}


def _build_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("research", _research_node)
    graph.add_node("scoring", _scoring_node)
    graph.add_node("reject_lead", _reject_lead_node)
    graph.add_node("drafting", _drafting_node)
    graph.add_node("guardrail", _guardrail_node)
    graph.add_node("mark_ready", _mark_ready_node)
    graph.add_node("drafting_revision", _drafting_revision_node)
    graph.add_node("guardrail_recheck", _guardrail_recheck_node)
    graph.add_node("mark_flagged", _mark_flagged_node)

    graph.add_edge(START, "research")
    graph.add_conditional_edges("research", _route_after_research)
    graph.add_conditional_edges("scoring", _route_after_scoring)
    graph.add_edge("reject_lead", END)
    graph.add_conditional_edges("drafting", _route_after_drafting)
    graph.add_conditional_edges("guardrail", _route_after_guardrail)
    graph.add_edge("mark_ready", END)
    graph.add_conditional_edges("drafting_revision", _route_after_revision)
    graph.add_conditional_edges("guardrail_recheck", _route_after_recheck)
    graph.add_edge("mark_flagged", END)

    return graph.compile()


# Compiled once at import time, not per-call. This is safe with respect to
# test mocking: unittest.mock.patch("src.agents.orchestrator.research_company", ...)
# replaces the name on this MODULE, and every node function above looks up
# `research_company` (etc.) from its enclosing module's global namespace at
# CALL time, not at graph-build time — so patched functions are picked up
# correctly no matter when the graph was compiled.
_compiled_graph = _build_graph()


def run_pipeline(
    company_name: str,
    domain: str | None = None,
    *,
    icp: ICPConfig | None = None,
    client: "anthropic.Anthropic | None" = None,
    research_tool_impls: dict | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> PipelineResult:
    settings = get_settings()
    icp = icp or get_icp_config()
    client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    pipeline_start = time.perf_counter()
    logger.info("pipeline started", extra={"company_name": company_name, "domain": domain})

    initial_state: PipelineState = {
        "company_name": company_name,
        "domain": domain,
        "icp": icp,
        "client": client,
        "research_tool_impls": research_tool_impls,
        "max_retries": max_retries,
        "invocation_log": [],
    }

    final_state = _compiled_graph.invoke(initial_state)
    total_latency_ms = int((time.perf_counter() - pipeline_start) * 1000)

    return PipelineResult(
        company_name=company_name,
        domain=domain,
        status=final_state["status"],
        research_output=final_state.get("research_output"),
        score_output=final_state.get("score_output"),
        draft_output=final_state.get("draft_output"),
        guardrail_output=final_state.get("guardrail_output"),
        invocation_log=final_state.get("invocation_log", []),
        total_latency_ms=total_latency_ms,
        failure_reason=final_state.get("failure_reason"),
    )
