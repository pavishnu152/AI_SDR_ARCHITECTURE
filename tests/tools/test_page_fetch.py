"""
Mocked tests for the fetch_page tool. httpx is patched — no real network
calls, deterministic output regardless of what any live website returns.
"""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.tools.page_fetch import PageFetchError, fetch_page


def _fake_response(status_code=200, content_type="text/html", text=""):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.headers = {"content-type": content_type}
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


@patch("src.tools.page_fetch.httpx.get")
def test_fetch_page_strips_html_to_clean_text(mock_get):
    html = "<html><body><script>bad()</script><nav>skip</nav><p>Hello World</p></body></html>"
    mock_get.return_value = _fake_response(text=html)

    result = fetch_page("https://example.com")

    assert "Hello World" in result
    assert "bad()" not in result
    assert "skip" not in result


@patch("src.tools.page_fetch.httpx.get")
def test_fetch_page_truncates_long_content(mock_get):
    long_text = "word " * 10000
    html = f"<html><body><p>{long_text}</p></body></html>"
    mock_get.return_value = _fake_response(text=html)

    result = fetch_page("https://example.com")

    assert len(result) <= 6000


@patch("src.tools.page_fetch.httpx.get")
def test_fetch_page_raises_on_non_html_content_type(mock_get):
    mock_get.return_value = _fake_response(content_type="application/pdf", text="binary-ish")

    with pytest.raises(PageFetchError):
        fetch_page("https://example.com/file.pdf")


@patch("src.tools.page_fetch.httpx.get")
def test_fetch_page_raises_on_http_error(mock_get):
    mock_get.return_value = _fake_response(status_code=404)

    with pytest.raises(PageFetchError):
        fetch_page("https://example.com/missing")


@patch("src.tools.page_fetch.httpx.get")
def test_fetch_page_raises_when_no_extractable_text(mock_get):
    # Valid HTML, correct content-type, but nothing left after stripping
    # script/style/nav/etc. — e.g. a page that's pure JS-rendered shell.
    html = "<html><body><script>renderApp()</script><nav>menu only</nav></body></html>"
    mock_get.return_value = _fake_response(text=html)

    with pytest.raises(PageFetchError, match="no extractable text"):
        fetch_page("https://example.com/empty-shell")
