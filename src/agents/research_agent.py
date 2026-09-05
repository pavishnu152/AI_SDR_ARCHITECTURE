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

4. LLM client: # LLM client: `openai` SDK pointed at Google's Gemini OpenAI-compatible endpoint,
   its API mirrors OpenAI's Chat Completions shape closely enough
   (`tools`/`tool_calls`, forced `tool_choice`) that swapping providers
   again later (or back) is a client + response-parsing change, not a
   redesign. See src/core/config.py for the base_url/model settings.
"""
import json
import time
from dataclasses import dataclass

import openai

from src.core.config import settings
from src.core.logging import get_agent_logger
from src.core.pricing import estimate_cost_usd, extract_token_usage
from src.schemas.lead import ResearchOutput, Signal
from src.tools.page_fetch import PageFetchError, fetch_page
from src.tools.web_search import WebSearchError, web_search

logger = get_agent_logger("research")

# History: first raised from 6 to 12 to fix "Anthropic"/"Google" leads
# exhausting their turn budget without ever calling submit_research. That
# alone made things worse, not better — more turns just let the cumulative
# conversation (search results + fetched page text, all appended to message
# history and re-sent on every subsequent call) grow much larger before
# failing, which exposed provider/API rate-limit behavior during live testing
# a later run on "rubixe" used 42,956 and 48,500 input tokens
# across its two attempts (~5-6 minutes each, mostly spent in 429 backoff)
# and still failed. The actual fix is shrinking how much each turn adds to
# the conversation (see the tightened tool-call budget in SYSTEM_PROMPT
# below, plus the reduced max_results/MAX_CONTENT_CHARS in the tools
# themselves) — turns needed drops to roughly 5 (2 searches + 2 fetches +
# submit) with that budget enforced, so 8 leaves real margin without
# letting an unbudgeted model run the context back up again.
MAX_TURNS = 8
MAX_TOKENS = 1500

# A fetched page or search-result batch is only needed at full size for the
# one turn right after it's produced — the model reads it, decides what to
# do next, and from then on is just carrying it forward as dead weight.
# Before this fix, that full-size tool content stayed in `messages` and got
# RE-SENT on every subsequent turn (standard chat-completions behavior:
# each call resends the whole history), which meant token cost compounded
# # Keep research payloads bounded to reduce cumulative LLM token usage
# and avoid unnecessary latency across multi-step research calls # Keep the research prompt compact because this agent may make multiple
# LLM/tool calls during a single lead-processing run on 2026-08-21 — same limit for both
# openai/gpt-oss-20b and openai/gpt-oss-120b, no favorable model swap
# available since it's the only free tier that also supports custom tool
# calling), a single run's later turns could already sit close to that
# ceiling on their own. Shrinking old tool output after one turn's use
# directly reduces what gets resent, independent of which tier/model is
# configured.
TRIMMED_TOOL_CONTENT_CHARS = 300

SYSTEM_PROMPT = """You are a B2B sales research analyst. Your job is to research one company \
and determine whether it fits this Ideal Customer Profile (ICP): AI-native B2B companies — \
startups/scale-ups that are building AI products or adopting AI infrastructure (AI dev tools, \
agent platforms, MLOps, applied-AI SaaS).

You have two research tools: `web_search` and `fetch_page`. Use web_search to find candidate \
pages (company site, news, job postings), then use fetch_page on the most promising URLs to \
read their actual content.

STRICT BUDGET — you have at most 2 web_search calls and 2 fetch_page calls (4 tool calls total) \
before you MUST call submit_research. This is a hard limit, not a suggestion: call submit_research \
with whatever evidence you have as soon as you hit it, even if you would prefer more information. \
Running searches or fetches beyond this budget wastes time and money without improving the result.

Look specifically for evidence of:
- Recent funding or press mentioning AI
- Job postings for ML/AI engineer, applied scientist, or similar roles
- Product pages/marketing mentioning "AI", "agent", "LLM", "copilot", or similar
- Signs of an engineering-heavy team (GitHub presence, technical blog, eng job volume)

When you have enough evidence (or have made a genuine effort and found little, or you have hit \
the tool-call budget above), call `submit_research` exactly once with your findings. Every signal \
you report MUST cite a source_url you actually fetched or saw in search results — never invent a \
signal you didn't find evidence for. If you found no strong signals, say so honestly in the \
summary rather than fabricating some."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web and get back a list of results (title, url, snippet).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_page",
            "description": "Fetch a URL and return its cleaned page text (truncated to ~2500 chars).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL to fetch."},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_research",
            "description": (
                "Submit your final research findings. Call this exactly once, when you are done "
                "researching, to end the task."
            ),
            "parameters": {
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

def _mock_research_result(company_name: str, domain: str | None) -> ResearchAgentResult:
    output = ResearchOutput(
        summary=(
            f"[MOCK] {company_name} appears to be an AI-native B2B company "
            "based on canned test data (Gemini call skipped)."
        ),
        signals=[
            Signal(
                label="product_ai_mention",
                detail="[MOCK] Company site mentions AI/agent features.",
                source_url=f"https://{domain or 'example.com'}",
            ),
            Signal(
                label="ai_job_postings",
                detail="[MOCK] Careers page shows ML engineer openings.",
                source_url=f"https://{domain or 'example.com'}/careers",
            ),
        ],
        sources=[f"https://{domain or 'example.com'}"],
    )
    return ResearchAgentResult(
        success=True,
        output=output,
        model="mock",
        latency_ms=10,
        turns_used=1,
        raw_input_summary=f"Research this company: {company_name}",
        raw_output_summary=output.summary,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
    )
def research_company(
    company_name: str,
    domain: str | None = None,
    *,
    client: "openai.OpenAI | None" = None,
    tool_impls: dict | None = None,
    max_turns: int = MAX_TURNS,
) -> ResearchAgentResult:
    config = settings()
    model = config.research_scoring_model
    if config.mock_llm:
        logger.info(
            "mock_llm enabled — returning canned research result",
            extra={"company_name": company_name},
        )
        return _mock_research_result(company_name, domain)

    client = client or openai.OpenAI(
    base_url=config.gemini_base_url,
    api_key=config.gemini_api_key,
)    
    tool_impls = tool_impls or _default_tool_impls()

    user_prompt = f"Research this company: {company_name}"
    if domain:
        user_prompt += f" (domain: {domain})"

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    start = time.perf_counter()
    total_input_tokens = 0
    total_output_tokens = 0

    logger.info(
        "research started",
        extra={"company_name": company_name, "domain": domain, "model": model},
    )

    # Maps turn number -> indices into `messages` of the tool-result
    # messages produced on that turn, so we know which ones are now "old"
    # (produced two or more turns ago) and safe to shrink before resending.
    tool_msg_indices_by_turn: dict[int, list[int]] = {}

    for turn in range(1, max_turns + 1):
        # Shrink tool output from turn-2 and earlier — it's already been
        # seen once at full size (last turn) and acted on; carrying it
        # forward at full size on every later turn is what was pushing
        # individual requests toward the 8K TPM free-tier ceiling. See
        # TRIMMED_TOOL_CONTENT_CHARS comment above for the full story.
        if turn >= 3:
            for idx in tool_msg_indices_by_turn.get(turn - 2, []):
                msg = messages[idx]
                content = msg.get("content") or ""
                if len(content) > TRIMMED_TOOL_CONTENT_CHARS:
                    msg["content"] = (
                        content[:TRIMMED_TOOL_CONTENT_CHARS]
                        + " …[trimmed from history after being read — already used]"
                    )

        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=MAX_TOKENS,
                tools=TOOLS,
                messages=messages,
            )
        except Exception as exc:  # noqa: BLE001
            #  Broad on purpose, not just openai.APIError: a missing/invalid
            # GEMINI_API_KEY can raise a client-side error before any HTTP
            # request is made, which isn't necessarily an APIError subclass.
            # That gap was invisible to every existing test (they all mock
            # the client) and only surfaced via a live smoke test against a
            # real, unconfigured client during the original Anthropic
            # integration — kept broad here for the same reason: an
            # unhandled exception must never escape to a raw 500 and skip
            # the AgentLog audit trail.
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

        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        tool_calls = message.tool_calls or []

        submit_call = next((tc for tc in tool_calls if tc.function.name == "submit_research"), None)
        if submit_call is not None:
            latency_ms = int((time.perf_counter() - start) * 1000)
            try:
                submit_input = json.loads(submit_call.function.arguments)
                output = ResearchOutput(
                    summary=submit_input["summary"],
                    signals=[Signal(**s) for s in submit_input["signals"]],
                    sources=submit_input["sources"],
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

        if not tool_calls:
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

        tool_msg_indices_by_turn[turn] = []
        for tc in tool_calls:
            tool_args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            content_str, is_error = _run_tool(tc.function.name, tool_args, tool_impls)
            if is_error:
                content_str = f"ERROR: {content_str}"
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content_str,
                }
            )
            tool_msg_indices_by_turn[turn].append(len(messages) - 1)

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