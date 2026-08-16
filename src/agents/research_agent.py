"""
Research Agent.

Given a company name (and optional domain), autonomously searches the web,
reads promising pages, and produces a structured ResearchOutput: a summary
plus a list of evidence-backed Signals scoped to our ICP (AI-native B2B
companies) — funding, AI-related hiring, product/AI positioning.

Design decisions worth understanding:

1. Structured final output via a "submit_research" tool, not free-text
   parsing. The model can call web_search/fetch_page freely, but the ONLY
   way to end the run successfully is to call submit_research with a
   schema-validated payload. This is the standard production pattern for
   forcing structured output while still allowing multi-step tool use —
   far more reliable than asking the model to "reply in JSON" and hoping
   it doesn't wrap it in prose or markdown fences.

2. Dependency injection for the LLM client and tool implementations
   (`client`, `tool_impls` params). Production agent code must be testable
   without hitting a real API or the real internet on every test run — see
   tests/test_research_agent.py, which injects fakes and never makes a
   network call.

3. Every run returns a ResearchAgentResult with success/error/latency
   metadata regardless of outcome. The caller (service layer, built later)
   decides what to persist to AgentLog — the agent itself doesn't touch
   the database. Keeping agents DB-agnostic keeps them unit-testable and
   reusable outside the API (e.g. from a CLI or batch script).
"""
import json
import time
from dataclasses import dataclass

import anthropic

from src.core.config import get_settings
from src.core.logging import get_agent_logger
from src.core.pricing import estimate_cost_usd, extract_token_usage
from src.schemas.lead import ResearchOutput, Signal
from src.tools.page_fetch import PageFetchError, fetch_page
from src.tools.web_search import WebSearchError, web_search

logger = get_agent_logger("research")

MAX_TURNS = 6
MAX_TOKENS = 1500

SYSTEM_PROMPT = """You are a B2B sales research analyst. Your job is to research one company \
and determine whether it fits this Ideal Customer Profile (ICP): AI-native B2B companies — \
startups/scale-ups that are building AI products or adopting AI infrastructure (AI dev tools, \
agent platforms, MLOps, applied-AI SaaS).

You have two research tools: `web_search` and `fetch_page`. Use web_search to find candidate \
pages (company site, news, job postings), then use fetch_page on the most promising 1-3 URLs to \
read their actual content. Do not fetch more than 4 pages total — be efficient.

Look specifically for evidence of:
- Recent funding or press mentioning AI
- Job postings for ML/AI engineer, applied scientist, or similar roles
- Product pages/marketing mentioning "AI", "agent", "LLM", "copilot", or similar
- Signs of an engineering-heavy team (GitHub presence, technical blog, eng job volume)

When you have enough evidence (or have made a genuine effort and found little), call \
`submit_research` exactly once with your findings. Every signal you report MUST cite a \
source_url you actually fetched or saw in search results — never invent a signal you didn't \
find evidence for. If you found no strong signals, say so honestly in the summary rather than \
fabricating some."""

TOOLS = [
    {
        "name": "web_search",
        "description": "Search the web and get back a list of results (title, url, snippet).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_page",
        "description": "Fetch a URL and return its cleaned page text (truncated to ~6000 chars).",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL to fetch."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "submit_research",
        "description": (
            "Submit your final research findings. Call this exactly once, when you are done "
            "researching, to end the task."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "2-4 sentence summary of the company and its ICP fit.",
                },
                "signals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": (
                                    "One of: recent_funding, ai_job_postings, "
                                    "product_ai_mention, engineering_team_signal, other"
                                ),
                            },
                            "detail": {"type": "string"},
                            "source_url": {"type": "string"},
                        },
                        "required": ["label", "detail", "source_url"],
                    },
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "All URLs consulted during research.",
                },
            },
            "required": ["summary", "signals", "sources"],
        },
    },
]


@dataclass
class ResearchAgentResult:
    success: bool
    output: ResearchOutput | None
    model: str
    latency_ms: int
    turns_used: int
    error: str | None = None
    raw_input_summary: str = ""
    raw_output_summary: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None


def _default_tool_impls() -> dict:
    return {"web_search": web_search, "fetch_page": fetch_page}


def _run_tool(name: str, tool_input: dict, tool_impls: dict) -> tuple[str, bool]:
    """Returns (content_str, is_error)."""
    try:
        if name == "web_search":
            results = tool_impls["web_search"](tool_input["query"])
            return json.dumps([r.__dict__ for r in results]), False
        if name == "fetch_page":
            text = tool_impls["fetch_page"](tool_input["url"])
            return text, False
        return f"unknown tool: {name}", True
    except (WebSearchError, PageFetchError) as exc:
        return str(exc), True
    except Exception as exc:  # noqa: BLE001 — tool failures must not crash the agent loop
        logger.warning("unexpected tool error", extra={"tool": name, "error": str(exc)})
        return f"unexpected error running {name}: {exc}", True


def research_company(
    company_name: str,
    domain: str | None = None,
    *,
    client: "anthropic.Anthropic | None" = None,
    tool_impls: dict | None = None,
    max_turns: int = MAX_TURNS,
) -> ResearchAgentResult:
    settings = get_settings()
    model = settings.research_scoring_model
    client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)
    tool_impls = tool_impls or _default_tool_impls()

    user_prompt = f"Research this company: {company_name}"
    if domain:
        user_prompt += f" (domain: {domain})"

    messages: list[dict] = [{"role": "user", "content": user_prompt}]
    start = time.perf_counter()
    total_input_tokens = 0
    total_output_tokens = 0

    logger.info(
        "research started",
        extra={"company_name": company_name, "domain": domain, "model": model},
    )

    for turn in range(1, max_turns + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
        except Exception as exc:  # noqa: BLE001
            # Was `except anthropic.APIError` — too narrow. APIError only
            # covers errors the API itself returns; a missing/invalid
            # ANTHROPIC_API_KEY raises a client-side TypeError before any
            # HTTP request is made, which isn't an APIError subclass. That
            # gap was invisible to every existing test (they all mock the
            # client, so this code path never actually ran) and only
            # surfaced via a live smoke test against a real, unconfigured
            # client — it let an unhandled exception escape all the way to
            # a raw 500, skip the AgentLog audit trail entirely, and leave
            # the Lead stuck in "pending" forever with no failure record.
            # Catching Exception here is strictly broader than before (all
            # api Errors are already Exceptions), not a behavior change for
            # the case that already worked.
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.error("research LLM call failed", extra={"error": str(exc), "turn": turn})
            return ResearchAgentResult(
                success=False,
                output=None,
                model=model,
                latency_ms=latency_ms,
                turns_used=turn,
                error=f"LLM call failed: {exc}",
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                cost_usd=estimate_cost_usd(model, total_input_tokens, total_output_tokens),
            )

        turn_input, turn_output = extract_token_usage(response)
        total_input_tokens += turn_input
        total_output_tokens += turn_output

        assistant_content = [block.model_dump() for block in response.content]
        messages.append({"role": "assistant", "content": assistant_content})

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        submit_block = next((b for b in tool_use_blocks if b.name == "submit_research"), None)
        if submit_block is not None:
            latency_ms = int((time.perf_counter() - start) * 1000)
            try:
                output = ResearchOutput(
                    summary=submit_block.input["summary"],
                    signals=[Signal(**s) for s in submit_block.input["signals"]],
                    sources=submit_block.input["sources"],
                )
            except Exception as exc:  # noqa: BLE001 — malformed structured output is a real failure mode
                logger.error("submit_research payload invalid", extra={"error": str(exc)})
                return ResearchAgentResult(
                    success=False,
                    output=None,
                    model=model,
                    latency_ms=latency_ms,
                    turns_used=turn,
                    error=f"invalid submit_research payload: {exc}",
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    cost_usd=estimate_cost_usd(model, total_input_tokens, total_output_tokens),
                )

            logger.info(
                "research completed",
                extra={
                    "company_name": company_name,
                    "signals_found": len(output.signals),
                    "turns_used": turn,
                    "latency_ms": latency_ms,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                },
            )
            return ResearchAgentResult(
                success=True,
                output=output,
                model=model,
                latency_ms=latency_ms,
                turns_used=turn,
                raw_input_summary=user_prompt,
                raw_output_summary=output.summary,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                cost_usd=estimate_cost_usd(model, total_input_tokens, total_output_tokens),
            )

        if not tool_use_blocks:
            # Model stopped without calling any tool and without submitting —
            # nudge it once instead of silently failing.
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "You have not called submit_research yet. If you have enough "
                        "information, call it now. Otherwise continue researching."
                    ),
                }
            )
            continue

        tool_results = []
        for block in tool_use_blocks:
            content_str, is_error = _run_tool(block.name, block.input, tool_impls)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content_str,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    latency_ms = int((time.perf_counter() - start) * 1000)
    logger.warning(
        "research exhausted max_turns without submission",
        extra={"company_name": company_name, "max_turns": max_turns},
    )
    return ResearchAgentResult(
        success=False,
        output=None,
        model=model,
        latency_ms=latency_ms,
        turns_used=max_turns,
        error=f"exceeded max_turns ({max_turns}) without a submit_research call",
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        cost_usd=estimate_cost_usd(model, total_input_tokens, total_output_tokens),
    )
