"""
Drafting Agent.

Given a company's ResearchOutput and ScoreOutput, writes a short, personalized
first-touch outreach message. Uses Claude Sonnet 5 (not Haiku) — see
architecture.md's tiering rationale: this is the highest-stakes, most
quality-sensitive step in the pipeline (it's the thing a human might
actually send), so it gets the stronger model.

Same forced-tool_choice pattern as the Scoring Agent, for the same reason:
one input, one required output shape, no benefit to letting the model
choose whether to respond with a tool call or free text.

Deliberately NOT responsible for fact-checking itself — that's the
Guardrail Agent's job, run as a separate, independent LLM call afterward.
Asking one call to "write persuasively AND self-police for accuracy" pulls
the model in two directions at once; splitting the roles produces a better
check than one agent grading its own homework mid-generation.
"""
import time
from dataclasses import dataclass

import anthropic

from src.core.config import get_settings
from src.core.logging import get_agent_logger
from src.core.pricing import estimate_cost_usd, extract_token_usage
from src.schemas.lead import DraftOutput, ResearchOutput, ScoreOutput

logger = get_agent_logger("drafting")

MAX_TOKENS = 500

SYSTEM_PROMPT = """You are an SDR writing a short, personalized first-touch outreach email to a \
prospective lead.

Rules:
- Reference 1-2 SPECIFIC signals from the research naturally (e.g. their recent funding, a \
  product detail) — do not list every signal like a report, and do not use generic filler like \
  "I noticed your company is doing great things in AI."
- Never state a fact that is not explicitly present in the research provided. If you are unsure \
  whether something is true, do not include it.
- Keep it under 130 words. Professional, warm, no hype/superlatives ("revolutionary", \
  "game-changing", etc.) — those read as spam and hurt reply rates.
- End with a low-friction call to action (e.g. asking for a short call), not a hard sell.
- Sign off as "— The AI SDR team" (this is a demo product; do not invent a fake human name).

Call submit_draft exactly once with the channel ("email") and the message."""

SUBMIT_DRAFT_TOOL = {
    "name": "submit_draft",
    "description": "Submit the final outreach draft.",
    "input_schema": {
        "type": "object",
        "properties": {
            "channel": {"type": "string", "enum": ["email", "linkedin"]},
            "message": {"type": "string"},
        },
        "required": ["channel", "message"],
    },
}


@dataclass
class DraftingAgentResult:
    success: bool
    output: DraftOutput | None
    model: str
    latency_ms: int
    error: str | None = None
    raw_input_summary: str = ""
    raw_output_summary: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None


def _format_prompt(
    company_name: str,
    research: ResearchOutput,
    score: ScoreOutput,
    guardrail_feedback: list[str] | None = None,
) -> str:
    signal_lines = "\n".join(f"- [{s.label}] {s.detail}" for s in research.signals) or "(none)"
    prompt = (
        f"Company: {company_name}\n\n"
        f"Research summary: {research.summary}\n\n"
        f"Signals:\n{signal_lines}\n\n"
        f"ICP fit score: {score.score}/100 (confidence {score.confidence})\n"
        f"Scoring reasoning: {score.reasoning}"
    )
    if guardrail_feedback:
        claims = "\n".join(f"- {c}" for c in guardrail_feedback)
        prompt += (
            "\n\nIMPORTANT: A previous draft was rejected by fact-checking for making these "
            f"unsupported claims:\n{claims}\n\n"
            "Write a new draft that avoids these specific claims. Only state facts explicitly "
            "present in the research above — when in doubt, leave it out."
        )
    return prompt


def draft_outreach(
    company_name: str,
    research: ResearchOutput,
    score: ScoreOutput,
    *,
    client: "anthropic.Anthropic | None" = None,
    guardrail_feedback: list[str] | None = None,
) -> DraftingAgentResult:
    """
    guardrail_feedback: when set, this is a revision attempt after the
    Guardrail Agent rejected a previous draft — see orchestrator.py's
    one-shot self-correction loop. Kept as an optional param (not a
    separate function) since the drafting logic itself is identical; only
    the prompt changes.
    """
    settings = get_settings()
    model = settings.drafting_guardrail_model
    client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    user_prompt = _format_prompt(company_name, research, score, guardrail_feedback)
    start = time.perf_counter()
    logger.info("drafting started", extra={"company_name": company_name, "model": model})

    try:
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=[SUBMIT_DRAFT_TOOL],
            tool_choice={"type": "tool", "name": "submit_draft"},
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc:  # noqa: BLE001 — see research_agent.py's matching except clause
        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.error("drafting LLM call failed", extra={"error": str(exc)})
        return DraftingAgentResult(
            success=False, output=None, model=model, latency_ms=latency_ms,
            error=f"LLM call failed: {exc}",
        )

    latency_ms = int((time.perf_counter() - start) * 1000)
    input_tokens, output_tokens = extract_token_usage(response)
    cost_usd = estimate_cost_usd(model, input_tokens, output_tokens)

    tool_use_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use_block is None:
        logger.error("drafting response had no tool_use block despite forced tool_choice")
        return DraftingAgentResult(
            success=False, output=None, model=model, latency_ms=latency_ms,
            error="model did not call submit_draft despite forced tool_choice",
            input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost_usd,
        )

    try:
        output = DraftOutput(**tool_use_block.input)
    except Exception as exc:  # noqa: BLE001
        logger.error("submit_draft payload invalid", extra={"error": str(exc)})
        return DraftingAgentResult(
            success=False, output=None, model=model, latency_ms=latency_ms,
            error=f"invalid submit_draft payload: {exc}",
            input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost_usd,
        )

    logger.info(
        "drafting completed",
        extra={"channel": output.channel, "latency_ms": latency_ms, "cost_usd": cost_usd},
    )
    return DraftingAgentResult(
        success=True,
        output=output,
        model=model,
        latency_ms=latency_ms,
        raw_input_summary=user_prompt,
        raw_output_summary=output.message,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
    )
