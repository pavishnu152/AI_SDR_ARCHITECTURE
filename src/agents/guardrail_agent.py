"""
Guardrail Agent.

Independently fact-checks a DraftOutput against the ResearchOutput it was
supposedly based on. This is the production-safety step: hallucination is
the #1 risk in agentic systems that produce customer-facing text, and
"the model that wrote it also checked it" is not a real safety check.

Design decisions worth understanding:

1. This agent sees ONLY the research and the draft — not the Scoring
   Agent's reasoning, not the Drafting Agent's chain of thought (it doesn't
   have one, since drafting is a single forced tool call, but even if it
   did, this agent shouldn't see it). It re-derives claims from the draft
   text itself and checks each one cold. Sharing context between the
   generator and the checker is how guardrails quietly become rubber
   stamps.

2. The prompt forces the model to enumerate claims before judging
   (chain-of-verification pattern), not just output a yes/no. Asking
   "is this draft accurate, yes or no" invites a lazy top-level judgment;
   asking "list every factual claim, then check each one" forces the model
   to actually do the comparison work, which measurably improves LLM-judge
   reliability.

3. approved=False is the SAFE default embedded in the tool schema/prompt:
   if the model is unsure, it must not approve. A guardrail that defaults
   to "probably fine" is not a guardrail.
"""
import time
from dataclasses import dataclass

import anthropic

from src.core.config import get_settings
from src.core.logging import get_agent_logger
from src.core.pricing import estimate_cost_usd, extract_token_usage
from src.schemas.lead import DraftOutput, GuardrailVerdict, ResearchOutput

logger = get_agent_logger("guardrail")

MAX_TOKENS = 700

SYSTEM_PROMPT = """You are a strict fact-checking reviewer for an automated sales outreach \
system. You did NOT write the draft below and have no stake in it being approved — your only \
job is to catch unsupported claims before this message is sent to a real person.

Process:
1. Read the draft message and identify every specific factual claim it makes about the company \
   (e.g. "you recently raised funding", "your AI copilot", any named fact).
2. For each claim, check whether it is explicitly supported by the research summary or signals \
   provided. Generic pleasantries or the call-to-action are not "claims" and don't need checking.
3. A claim is supported ONLY if the research explicitly states it. Do not give the draft the \
   benefit of the doubt — if it's not clearly in the research, it is unsupported.

If ANY claim is unsupported, set approved=false and list each unsupported claim exactly as \
written in the draft. If you are uncertain whether the draft is fully supported, default to \
approved=false — an over-cautious guardrail is far cheaper than a false claim reaching a real \
prospect.

Call submit_verdict exactly once."""

SUBMIT_VERDICT_TOOL = {
    "name": "submit_verdict",
    "description": "Submit the final fact-check verdict for this draft.",
    "input_schema": {
        "type": "object",
        "properties": {
            "approved": {"type": "boolean"},
            "unsupported_claims": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Claims from the draft that are NOT supported by the research.",
            },
            "notes": {
                "type": "string",
                "description": "Brief explanation of the verdict, for the audit log.",
            },
        },
        "required": ["approved", "unsupported_claims", "notes"],
    },
}


@dataclass
class GuardrailAgentResult:
    success: bool
    output: GuardrailVerdict | None
    model: str
    latency_ms: int
    error: str | None = None
    raw_input_summary: str = ""
    raw_output_summary: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None


def _format_prompt(research: ResearchOutput, draft: DraftOutput) -> str:
    signal_lines = "\n".join(f"- [{s.label}] {s.detail}" for s in research.signals) or "(none)"
    return (
        f"Research summary: {research.summary}\n\n"
        f"Research signals:\n{signal_lines}\n\n"
        f"--- Draft message to review ---\n{draft.message}"
    )


def check_draft(
    research: ResearchOutput,
    draft: DraftOutput,
    *,
    client: "anthropic.Anthropic | None" = None,
) -> GuardrailAgentResult:
    settings = get_settings()
    model = settings.drafting_guardrail_model
    client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    user_prompt = _format_prompt(research, draft)
    start = time.perf_counter()
    logger.info("guardrail check started", extra={"model": model})

    try:
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=[SUBMIT_VERDICT_TOOL],
            tool_choice={"type": "tool", "name": "submit_verdict"},
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc:  # noqa: BLE001 — see research_agent.py's matching except clause
        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.error("guardrail LLM call failed", extra={"error": str(exc)})
        # Fail closed: an LLM outage must NOT be silently treated as approval.
        return GuardrailAgentResult(
            success=False, output=None, model=model, latency_ms=latency_ms,
            error=f"LLM call failed: {exc}",
        )

    latency_ms = int((time.perf_counter() - start) * 1000)
    input_tokens, output_tokens = extract_token_usage(response)
    cost_usd = estimate_cost_usd(model, input_tokens, output_tokens)

    tool_use_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use_block is None:
        logger.error("guardrail response had no tool_use block despite forced tool_choice")
        return GuardrailAgentResult(
            success=False, output=None, model=model, latency_ms=latency_ms,
            error="model did not call submit_verdict despite forced tool_choice",
            input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost_usd,
        )

    try:
        output = GuardrailVerdict(**tool_use_block.input)
    except Exception as exc:  # noqa: BLE001
        logger.error("submit_verdict payload invalid", extra={"error": str(exc)})
        return GuardrailAgentResult(
            success=False, output=None, model=model, latency_ms=latency_ms,
            error=f"invalid submit_verdict payload: {exc}",
            input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost_usd,
        )

    logger.info(
        "guardrail check completed",
        extra={
            "approved": output.approved,
            "unsupported_claim_count": len(output.unsupported_claims),
            "latency_ms": latency_ms,
            "cost_usd": cost_usd,
        },
    )
    return GuardrailAgentResult(
        success=True,
        output=output,
        model=model,
        latency_ms=latency_ms,
        raw_input_summary=user_prompt,
        raw_output_summary=output.notes,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
    )
