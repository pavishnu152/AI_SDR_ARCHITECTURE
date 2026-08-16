"""
Page fetch tool — retrieves and cleans a single URL's text content for the
Research Agent to read.

Why we strip HTML down to plain text and truncate: raw HTML wastes a huge
number of LLM input tokens on markup the model doesn't need, which directly
costs money and latency on every research call. Truncating to
MAX_CONTENT_CHARS is a deliberate, documented tradeoff — long pages get cut,
which is a real limitation worth stating plainly rather than hiding.
"""
import logging

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("tools.page_fetch")

MAX_CONTENT_CHARS = 6000
REQUEST_TIMEOUT_SECONDS = 10
USER_AGENT = "ai-sdr-research-agent/0.1 (portfolio project; contact: pavishnu15btechit@gmail.com)"


class PageFetchError(Exception):
    """Raised when a page can't be fetched or isn't usable text content."""


def fetch_page(url: str) -> str:
    """
    Fetch a URL and return cleaned, truncated plain text.

    We identify ourselves via a real User-Agent (not a bare requests
    default) — scraping anonymously is bad practice and some sites block
    default UAs outright; a good-citizen crawler identifies itself.
    """
    try:
        response = httpx.get(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("fetch_page failed for url=%r: %s", url, exc)
        raise PageFetchError(f"failed to fetch {url!r}: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type:
        raise PageFetchError(f"url {url!r} is not HTML content (content-type={content_type!r})")

    soup = BeautifulSoup(response.text, "lxml")

    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    text = " ".join(soup.get_text(separator=" ").split())

    if not text:
        raise PageFetchError(f"url {url!r} returned no extractable text")

    return text[:MAX_CONTENT_CHARS]
