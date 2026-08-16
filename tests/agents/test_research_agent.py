"""
Mocked tests for the Research Agent's tool-calling loop.

We fake the Anthropic client entirely — no real API calls, no API key
needed, fully deterministic. This is the pattern the whole agent test
suite follows (see architecture.md's testing principle): agent logic is
tested by controlling exactly what the "model" says on each turn and
asserting how the agent reacts, the same way you'd unit test a state
machine.
"""
from dataclasses import dataclass
from unittest.mock import MagicMock

import anthropic
import httpx

from src.agents.research_agent import _run_tool, research_company
from src.tools.page_fetch import PageFetchError
from src.tools.web_search import SearchResult, WebSearchError


@dataclass
class FakeBlock:
    """Mimics the shape of an Anthropic content block enough for our loop."""
    type: str
    id: str = ""
    name: str = ""
    input: dict = None
    text: str = ""

    def model_dump(self) -> dict:
        if self.type == "tool_use":
            return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.input}
        return {"type": "text", "text": self.text}


@dataclass
class FakeResponse:
    content: list
    stop_reason: str = "tool_use"


def _fake_client(responses: list[FakeResponse]) -> MagicMock:
    client = MagicMock()
    client.messages.create.side_effect = responses
    return client


def test_research_agent_happy_path_calls_tools_then_submits():
    search_response = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                id="tu_1",
                name="web_search",
                input={"query": "Acme AI funding"},
            )
        ]
    )
    submit_response = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                id="tu_2",
                name="submit_research",
                input={
                    "summary": "Acme AI is an AI-native startup with recent funding.",
                    "signals": [
                        {
                            "label": "recent_funding",
                            "detail": "Raised $10M seed round",
                            "source_url": "https://news.example.com/acme",
                        }
                    ],
                    "sources": ["https://news.example.com/acme"],
                },
            )
        ]
    )
    client = _fake_client([search_response, submit_response])

    fake_web_search = MagicMock(
        return_value=[
            SearchResult(
                title="Acme AI raises $10M",
                url="https://news.example.com/acme",
                snippet="...",
            )
        ]
    )
    tool_impls = {"web_search": fake_web_search, "fetch_page": MagicMock()}

    result = research_company(
        "Acme AI", client=client, tool_impls=tool_impls, max_turns=4
    )

    assert result.success is True
    assert result.output is not None
    assert result.output.signals[0].label == "recent_funding"
    assert result.turns_used == 2
    fake_web_search.assert_called_once_with("Acme AI funding")


def test_research_agent_fails_gracefully_when_max_turns_exceeded():
    # Model just keeps talking, never calls submit_research.
    stalling_response = FakeResponse(content=[FakeBlock(type="text", text="still thinking...")])
    client = _fake_client([stalling_response] * 3)

    result = research_company(
        "Acme AI",
        client=client,
        tool_impls={"web_search": MagicMock(), "fetch_page": MagicMock()},
        max_turns=3,
    )

    assert result.success is False
    assert "max_turns" in result.error


def test_research_agent_handles_tool_failure_without_crashing():
    search_response = FakeResponse(
        content=[
            FakeBlock(type="tool_use", id="tu_1", name="web_search", input={"query": "Acme AI"})
        ]
    )
    submit_response = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                id="tu_2",
                name="submit_research",
                input={
                    "summary": "Limited information found.",
                    "signals": [],
                    "sources": [],
                },
            )
        ]
    )
    client = _fake_client([search_response, submit_response])

    from src.tools.web_search import WebSearchError

    failing_web_search = MagicMock(side_effect=WebSearchError("search backend down"))
    tool_impls = {"web_search": failing_web_search, "fetch_page": MagicMock()}

    result = research_company("Acme AI", client=client, tool_impls=tool_impls, max_turns=4)

    # The agent should recover from the tool error (fed back as an error
    # tool_result) and still complete successfully with a thin result,
    # rather than raising.
    assert result.success is True
    assert result.output.signals == []


def test_research_company_includes_domain_in_prompt_when_given():
    submit_response = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use", id="tu_1", name="submit_research",
                input={"summary": "ok", "signals": [], "sources": []},
            )
        ]
    )
    client = _fake_client([submit_response])

    research_company(
        "Acme AI", domain="acme.ai", client=client,
        tool_impls={"web_search": MagicMock(), "fetch_page": MagicMock()},
    )

    sent_messages = client.messages.create.call_args.kwargs["messages"]
    assert "acme.ai" in sent_messages[0]["content"]


def test_research_company_handles_llm_api_error():
    client = MagicMock()
    client.messages.create.side_effect = anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )

    result = research_company(
        "Acme AI", client=client,
        tool_impls={"web_search": MagicMock(), "fetch_page": MagicMock()},
    )

    assert result.success is False
    assert "LLM call failed" in result.error


def test_research_company_handles_client_side_error_not_just_api_error():
    # Regression test: a missing/invalid API key makes the real Anthropic
    # SDK raise a client-side TypeError from _validate_headers, BEFORE any
    # HTTP request — discovered via a live smoke test, not by inspection.
    # anthropic.APIError only covers errors the API itself returns, so a
    # bare `except anthropic.APIError` let this escape uncaught all the way
    # to a raw 500, skipping the AgentLog audit trail entirely. Any
    # exception from the LLM call must degrade to a failed result, not
    # crash the pipeline.
    client = MagicMock()
    client.messages.create.side_effect = TypeError(
        "Could not resolve authentication method."
    )

    result = research_company(
        "Acme AI", client=client,
        tool_impls={"web_search": MagicMock(), "fetch_page": MagicMock()},
    )

    assert result.success is False
    assert "LLM call failed" in result.error


def test_research_company_handles_invalid_submit_payload():
    # Missing required "sources" key — ResearchOutput validation must fail.
    bad_submit_response = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use", id="tu_1", name="submit_research",
                input={"summary": "ok", "signals": []},
            )
        ]
    )
    client = _fake_client([bad_submit_response])

    result = research_company(
        "Acme AI", client=client,
        tool_impls={"web_search": MagicMock(), "fetch_page": MagicMock()},
    )

    assert result.success is False
    assert "invalid submit_research payload" in result.error


class TestRunTool:
    """
    _run_tool is a pure function (name, input, tool_impls) -> (str, bool) —
    testing it directly is simpler and more precise than only exercising it
    indirectly through the full research_company loop.
    """

    def test_unknown_tool_name_returns_error(self):
        content, is_error = _run_tool("not_a_real_tool", {}, {})

        assert is_error is True
        assert "unknown tool" in content

    def test_known_tool_error_is_caught_and_returned(self):
        tool_impls = {"web_search": MagicMock(side_effect=WebSearchError("backend down"))}

        content, is_error = _run_tool("web_search", {"query": "x"}, tool_impls)

        assert is_error is True
        assert "backend down" in content

    def test_page_fetch_error_is_caught_and_returned(self):
        tool_impls = {"fetch_page": MagicMock(side_effect=PageFetchError("404"))}

        content, is_error = _run_tool("fetch_page", {"url": "https://x"}, tool_impls)

        assert is_error is True
        assert "404" in content

    def test_unexpected_exception_does_not_propagate(self):
        tool_impls = {"web_search": MagicMock(side_effect=RuntimeError("totally unexpected"))}

        content, is_error = _run_tool("web_search", {"query": "x"}, tool_impls)

        assert is_error is True
        assert "unexpected error" in content
