"""
Scoring Agent.

Given a ResearchOutput (from the Research Agent) and an ICPConfig, produces
a ScoreOutput: a 0-100 fit score, a confidence value, and reasoning that
must cite specific signals — not vague generalities.

Design decisions worth understanding:

1. Forced tool_choice, not "auto". The Research Agent uses tool_choice=
   "auto" because it genuinely needs to decide, turn by turn, whether to
   search, fetch, or submit. The Scoring Agent has no such decision to
   make — it always receives research and always must produce a score in
   one shot. Forcing tool_choice={"type": "tool", "name": "submit_score"}
   means the model has no path to reply with a bare text answer, no risk of
   "let me think about this..." prose leaking into what should be a single
   structured call. Use "auto" when the model needs to choose an action;
   force a specific tool when there is exactly one valid response shape.

2. No web/search tools available here at all — deliberately. The Scoring
   Agent should reason ONLY over what the Research Agent already found, not
   go re-research on its own. This keeps responsibilities cleanly separated
   (see architecture.md) and makes scoring fast/cheap (a single Haiku call,
   no multi-turn tool loop, no extra latency or cost).

3. The ICP is injected as data (ICPConfig.as_prompt_block()), not
   hardcoded into this file's prompt string. Change the YAML, the scoring
   rubric changes — no code edit, no redeploy.
"""
import time
from dataclasses import dataclass

import anthropic

from src.core.config import get_settings
from src.core.icp import ICPConfig, get_icp_config
from src.core.logging import get_agent_logger
from src.core.pricing import estimate_cost_usd, extract_token_usage
from src.schemas.lead import ResearchOutput, ScoreOutput

logger = get_agent_logger("scoring")

MAX_TOKENS = 600

SYSTEM_PROMPT_TEMPLATE = """You are a B2B lead scoring analyst. Score the company described \
below against the following Ideal Customer Profile.

{icp_block}

Your reasoning MUST cite specific signals from the research provided below — never invent or \
assume evidence that isn't there. If the research signals are thin, contradictory, or ambiguous, \
reflect that with a LOWER confidence score, not by inflating the fit score to compensate. A \
company with zero real signals should score low with low confidence, not a moderate score out \
of politeness.

Call submit_score exactly once with your score (0-100), confidence (0.0-1.0), and reasoning."""

SUBMIT_SCORE_TOOL = {
    "name": "submit_score",
    "description": "Submit the final ICP fit score for this lead.",
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "reasoning": {
                "type": "string",
                "description": "Must reference specific signals from the research provided.",
            },
        },
        "required": ["score", "confidence", "reasoning"],
    },
}


@dataclass
class ScoringAgentResult:
    success: bool
    output: ScoreOutput | None
    model: str
    latency_ms: int
    error: str | None = None
    raw_input_summary: str = ""
    raw_output_summary: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None


def _format_research_for_prompt(research: ResearchOutput) -> str:
    signal_lines = "\n".join(
        f"- [{s.label}] {s.detail} (source: {s.source_url or 'n/a'})" for s in research.signals
    ) or "(no signals found)"
    return (
        f"Research summary:\n{research.summary}\n\n"
        f"Signals found:\n{signal_lines}\n\n"
        f"Sources consulted: {', '.join(research.sources) or '(none)'}"
    )


def score_lead(
    research: ResearchOutput,
    icp: ICPConfig | None = None,
    *,
    client: "anthropic.Anthropic | None" = None,
) -> ScoringAgentResult:
    settings = get_settings()
    icp = icp or get_icp_config()
    model = settings.research_scoring_model
    client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(icp_block=icp.as_prompt_block())
    user_prompt = _format_research_for_prompt(research)

    start = time.perf_counter()
    logger.info("scoring started", extra={"icp_name": icp.name, "model": model})

    try:
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            tools=[SUBMIT_SCORE_TOOL],
            tool_choice={"type": "tool", "name": "submit_score"},
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc:  # noqa: BLE001 — see research_agent.py's matching except clause
        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.error("scoring LLM call failed", extra={"error": str(exc)})
        return ScoringAgentResult(
            success=False,
            output=None,
            model=model,
            latency_ms=latency_ms,
            error=f"LLM call failed: {exc}",
        )

    latency_ms = int((time.perf_counter() - start) * 1000)
    input_tokens, output_tokens = extract_token_usage(response)
    cost_usd = estimate_cost_usd(model, input_tokens, output_tokens)

    tool_use_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use_block is None:
        logger.error("scoring response had no tool_use block despite forced tool_choice")
        return ScoringAgentResult(
            success=False,
            output=None,
            model=model,
            latency_ms=latency_ms,
            error="model did not call submit_score despite forced tool_choice",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

    try:
        output = ScoreOutput(**tool_use_block.input)
    except Exception as exc:  # noqa: BLE001 — malformed structured output is a real failure mode
        logger.error("submit_score payload invalid", extra={"error": str(exc)})
        return ScoringAgentResult(
            success=False,
            output=None,
            model=model,
            latency_ms=latency_ms,
            error=f"invalid submit_score payload: {exc}",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

    logger.info(
        "scoring completed",
        extra={
            "score": output.score,
            "confidence": output.confidence,
            "latency_ms": latency_ms,
            "cost_usd": cost_usd,
        },
    )
    return ScoringAgentResult(
        success=True,
        output=output,
        model=model,
        latency_ms=latency_ms,
        raw_input_summary=user_prompt,
        raw_output_summary=output.reasoning,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
    )
