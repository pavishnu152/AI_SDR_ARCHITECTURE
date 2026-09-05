"""
FROZEN REFERENCE IMPLEMENTATION — this file's `run_pipeline()` (the
hand-rolled state machine logic itself) is not imported or called by any
live code path, not maintained going forward, and not covered by the
active test suite (tests/agents/test_orchestrator.py now tests
orchestrator.py's LangGraph implementation instead).

Note: `AgentInvocationRecord`, `PipelineResult`, and the retry helper are
imported from orchestrator_types.py rather than redefined here — those are
pure data shapes/utilities that didn't change in the refactor (see
orchestrator.py's docstring for why), so duplicating them here would just
create two copies to keep in sync for no benefit. What's frozen is the
*orchestration logic* below, which is the actual thing that got rewritten.

This is the exact hand-rolled state machine from Milestone 6, preserved
here specifically so the LangGraph refactor in Milestone 10 has a real,
runnable "before" to diff against — see
docs/milestone10-langgraph-refactor.md for the full before/after writeup.
Deleting working code the moment you refactor it is normal in a real repo
(that's what git history is for); it's kept as a live file here, not just
a commit, because this project's whole point is to be read and explained,
not just to work.

Provider note: this file was frozen at Milestone 10, when the pipeline
still ran on Anthropic Claude. Milestone "LLM provider migration" swapped every
live agent (research/scoring/drafting/guardrail) plus this file's own
client wiring from `anthropic.Anthropic` to `openai.OpenAI` pointed at
Gemini's OpenAI-compatible endpoint, purely so this dead file doesn't import a package that's
no longer a project dependency and doesn't silently break if anyone ever
does import it. The actual orchestration logic below — retries, the
reject-early gate, the guardrail self-correction loop — is unchanged from
Milestone 10; only the LLM client construction moved with the rest of the
codebase.

Original module docstring follows unchanged below.
---

Orchestrator — the hand-rolled state machine that chains all four agents
into one pipeline: Research -> Score -> (reject-early gate) -> Draft ->
Guardrail -> (one self-correction loop) -> final status.

Why hand-rolled instead of LangGraph right now: per architecture.md, we
build this by hand first so the tool-calling loop, retries, and state
transitions are fully understood at a low level before adopting a
framework that would otherwise hide all of it. Milestone 10 refactors this
exact file to LangGraph with a documented before/after comparison.

Key design decisions:

1. A single shared LLM client is created once and passed into every agent
   call, instead of each agent creating its own. Client objects hold an
   HTTP connection pool — creating a fresh one per call wastes a TCP/TLS
   handshake on every single agent invocation across a 4-agent pipeline.
   This is a real production cost, not just tidiness.

2. Reject-early gate: if the Scoring Agent returns a score at or below
   icp.score_thresholds.reject, the pipeline stops BEFORE drafting. The
   drafting + guardrail calls run on the stronger tiered model and are the
   most expensive part of this pipeline — there's no reason to pay for a
   personalized draft for a lead that already failed fit scoring. This is
   a direct cost-optimization decision, and a good one to be able to
   defend in interviews.

3. Per-stage retries (transient failure recovery) are a SEPARATE concept
   from the guardrail self-correction loop (a business-logic response to a
   legitimate rejection, not a technical failure). Conflating "the API
   call failed" with "the draft was rejected for making things up" would
   be a design mistake — they need different handling and different
   status outcomes (FAILED vs. GUARDRAIL_FLAGGED).

4. Guardrail failures fail closed: if the Guardrail Agent itself can't run
   (LLM error) after retries, the pipeline status is FAILED, never READY.
   An unverified draft must never reach "ready to send" by default.
"""
import time

import openai

from src.agents.drafting_agent import DraftingAgentResult, draft_outreach
from src.agents.guardrail_agent import GuardrailAgentResult, check_draft
from src.agents.orchestrator_types import AgentInvocationRecord, PipelineResult, call_with_retry
from src.agents.research_agent import ResearchAgentResult, research_company
from src.agents.scoring_agent import ScoringAgentResult, score_lead
from src.core.config import settings
from src.core.icp import ICPConfig, get_icp_config
from src.core.logging import get_agent_logger
from src.db.models import LeadStatus

logger = get_agent_logger("orchestrator_legacy")

DEFAULT_MAX_RETRIES = 1  # 1 retry = 2 attempts total per stage

# Alias kept so the function bodies below read identically to how they did
# before this file was frozen — this IS the historical artifact, so its
# internals shouldn't be rewritten to look different from what actually ran.
_call_with_retry = call_with_retry


def run_pipeline(
    company_name: str,
    domain: str | None = None,
    *,
    icp: ICPConfig | None = None,
    client: "openai.OpenAI | None" = None,
    research_tool_impls: dict | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> PipelineResult:
    config = settings()
    icp = icp or get_icp_config()
    client = client or openai.OpenAI(
    base_url=config.gemini_base_url,
    api_key=config.gemini_api_key,
)
    invocation_log: list[AgentInvocationRecord] = []
    pipeline_start = time.perf_counter()

    logger.info("pipeline started", extra={"company_name": company_name, "domain": domain})

    # --- Stage 1: Research ---
    research_result: ResearchAgentResult = _call_with_retry(
        "research",
        lambda: research_company(
            company_name, domain, client=client, tool_impls=research_tool_impls
        ),
        invocation_log,
        max_retries,
    )
    if not research_result.success:
        return PipelineResult(
            company_name=company_name,
            domain=domain,
            status=LeadStatus.FAILED,
            invocation_log=invocation_log,
            total_latency_ms=int((time.perf_counter() - pipeline_start) * 1000),
            failure_reason=f"research failed: {research_result.error}",
        )
    research_output = research_result.output

    # --- Stage 2: Scoring ---
    score_result: ScoringAgentResult = _call_with_retry(
        "scoring",
        lambda: score_lead(research_output, icp, client=client),
        invocation_log,
        max_retries,
    )
    if not score_result.success:
        return PipelineResult(
            company_name=company_name,
            domain=domain,
            status=LeadStatus.FAILED,
            research_output=research_output,
            invocation_log=invocation_log,
            total_latency_ms=int((time.perf_counter() - pipeline_start) * 1000),
            failure_reason=f"scoring failed: {score_result.error}",
        )
    score_output = score_result.output

    # --- Reject-early gate: don't spend drafting/guardrail calls on a bad-fit lead ---
    if score_output.score <= icp.score_thresholds.reject:
        logger.info(
            "lead rejected by score gate, skipping drafting",
            extra={"score": score_output.score, "reject_threshold": icp.score_thresholds.reject},
        )
        return PipelineResult(
            company_name=company_name,
            domain=domain,
            status=LeadStatus.REJECTED,
            research_output=research_output,
            score_output=score_output,
            invocation_log=invocation_log,
            total_latency_ms=int((time.perf_counter() - pipeline_start) * 1000),
        )

    # --- Stage 3: Drafting ---
    draft_result: DraftingAgentResult = _call_with_retry(
        "drafting",
        lambda: draft_outreach(company_name, research_output, score_output, client=client),
        invocation_log,
        max_retries,
    )
    if not draft_result.success:
        return PipelineResult(
            company_name=company_name,
            domain=domain,
            status=LeadStatus.FAILED,
            research_output=research_output,
            score_output=score_output,
            invocation_log=invocation_log,
            total_latency_ms=int((time.perf_counter() - pipeline_start) * 1000),
            failure_reason=f"drafting failed: {draft_result.error}",
        )
    draft_output = draft_result.output

    # --- Stage 4: Guardrail (with one self-correction loop on rejection) ---
    guardrail_result: GuardrailAgentResult = _call_with_retry(
        "guardrail",
        lambda: check_draft(research_output, draft_output, client=client),
        invocation_log,
        max_retries,
    )
    if not guardrail_result.success:
        return PipelineResult(
            company_name=company_name,
            domain=domain,
            status=LeadStatus.FAILED,
            research_output=research_output,
            score_output=score_output,
            draft_output=draft_output,
            invocation_log=invocation_log,
            total_latency_ms=int((time.perf_counter() - pipeline_start) * 1000),
            failure_reason=f"guardrail check failed: {guardrail_result.error}",
        )

    guardrail_output = guardrail_result.output

    if not guardrail_output.approved:
        logger.info(
            "guardrail rejected draft, attempting one self-correction",
            extra={"unsupported_claims": guardrail_output.unsupported_claims},
        )
        revision_result: DraftingAgentResult = _call_with_retry(
            "drafting_revision",
            lambda: draft_outreach(
                company_name,
                research_output,
                score_output,
                client=client,
                guardrail_feedback=guardrail_output.unsupported_claims,
            ),
            invocation_log,
            max_retries=0,
        )

        if revision_result.success:
            draft_output = revision_result.output
            second_guardrail_result: GuardrailAgentResult = _call_with_retry(
                "guardrail_recheck",
                lambda: check_draft(research_output, draft_output, client=client),
                invocation_log,
                max_retries=0,
            )
            if second_guardrail_result.success and second_guardrail_result.output.approved:
                status = LeadStatus.READY
                guardrail_output = second_guardrail_result.output
            else:
                status = LeadStatus.GUARDRAIL_FLAGGED
                if second_guardrail_result.success:
                    guardrail_output = second_guardrail_result.output
        else:
            status = LeadStatus.GUARDRAIL_FLAGGED
    else:
        status = LeadStatus.READY

    return PipelineResult(
        company_name=company_name,
        domain=domain,
        status=status,
        research_output=research_output,
        score_output=score_output,
        draft_output=draft_output,
        guardrail_output=guardrail_output,
        invocation_log=invocation_log,
        total_latency_ms=int((time.perf_counter() - pipeline_start) * 1000),
    )
