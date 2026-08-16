"""
Mocked tests for the web_search tool. Never hits the real network — DDGS is
patched. This matters because live search results are non-deterministic
and this sandbox's egress is restricted anyway; a real integration check
against the live internet belongs in a separate, explicitly-marked smoke
test, not the default test suite.
"""
from unittest.mock import MagicMock, patch

import pytest
from ddgs.exceptions import DDGSException

from src.tools.web_search import WebSearchError, web_search


@patch("src.tools.web_search.DDGS")
def test_web_search_returns_parsed_results(mock_ddgs_cls):
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = [
        {"title": "Acme AI raises $10M", "href": "https://news.example.com/acme", "body": "..."},
        {"title": "", "href": "", "body": "no href, should be filtered"},
    ]
    mock_ddgs_cls.return_value.__enter__.return_value = mock_ddgs_instance

    results = web_search("Acme AI funding")

    assert len(results) == 1
    assert results[0].title == "Acme AI raises $10M"
    assert results[0].url == "https://news.example.com/acme"


@patch("src.tools.web_search.DDGS")
def test_web_search_raises_websearcherror_on_backend_failure(mock_ddgs_cls):
    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.side_effect = DDGSException("rate limited")
    mock_ddgs_cls.return_value.__enter__.return_value = mock_ddgs_instance

    with pytest.raises(WebSearchError):
        web_search("Acme AI funding")
