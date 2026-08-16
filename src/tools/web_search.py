"""
Web search tool — the Research Agent's primary source of leads/signal
discovery.

Why DuckDuckGo (`ddgs`) instead of a paid search API for now: it's free and
keyless, which matters for a CPU/budget-constrained solo build. It's
documented in architecture.md as a placeholder for a production upgrade
(Tavily/SerpAPI) — DDGS has no SLA and can rate-limit or change its HTML
contract without notice, which is not something you'd accept in a real
production system, only in a portfolio-stage one.
"""
import logging
from dataclasses import dataclass

from ddgs import DDGS
from ddgs.exceptions import DDGSException

logger = logging.getLogger("tools.web_search")


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearchError(Exception):
    """Raised when the search backend fails after retries are exhausted."""


def web_search(query: str, max_results: int = 5) -> list[SearchResult]:
    """
    Run a web search and return lightweight results (title/url/snippet).

    Deliberately does NOT fetch full page content here — that's a separate
    tool (`fetch_page`) so the agent can decide which results are worth the
    extra latency/token cost of a full fetch, instead of always paying for
    every result's full page text.
    """
    try:
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(query, max_results=max_results))
    except DDGSException as exc:
        logger.warning("web_search failed for query=%r: %s", query, exc)
        raise WebSearchError(f"search failed for query {query!r}: {exc}") from exc

    return [
        SearchResult(
            title=r.get("title", ""),
            url=r.get("href", ""),
            snippet=r.get("body", ""),
        )
        for r in raw_results
        if r.get("href")
    ]
