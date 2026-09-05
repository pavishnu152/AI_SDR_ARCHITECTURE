"""
Mocked tests for the Research Agent's tool-calling loop.

We fake the Gemini(OpenAI-compatible) client entirely — no real API calls,
no API key needed, fully deterministic. This is the pattern the whole
agent test suite follows (see architecture.md's testing principle): agent
logic is tested by controlling exactly what the "model" says on each turn
and asserting how the agent reacts, the same way you'd unit test a state
machine.
"""
import json
from dataclasses import dataclass, field
from unittest.mock import MagicMock

import httpx
import openai

from src.agents.research_agent import _run_tool, research_company
from src.tools.page_fetch import PageFetchError
from src.tools.web_search import SearchResult, WebSearchError


@dataclass
class FakeFunction:
    name: str
    arguments: str  # JSON string, matching OpenAI's wire format


@dataclass
class FakeToolCall:
    id: str
    function: FakeFunction


@dataclass
class FakeMessage:
    """Mimics the shape of an OpenAI/Gemini chat completion message enough
    for the agent loop, including model_dump() which research_agent.py
    calls to append the assistant turn back onto the running messages list."""
    content: str | None = None
    tool_calls: list | None = None

    def model_dump(self, exclude_none: bool = False) -> dict:
        d: dict = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in self.tool_calls
            ]
        elif not exclude_none:
            d["tool_calls"] = None
        if exclude_none:
            d = {k: v for k, v in d.items() if v is not None}
        return d


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeResponse:
    choices: list = field(default_factory=list)


def _tool_call(call_id: str, name: str, payload: dict) -> FakeToolCall:
    return FakeToolCall(id=call_id, function=FakeFunction(name=name, arguments=json.dumps(payload)))


def _response(*tool_calls: FakeToolCall, text: str | None = None) -> FakeResponse:
    return FakeResponse(
        choices=[FakeChoice(message=FakeMessage(content=text, tool_calls=list(tool_calls) or None))]
    )


def _fake_client(responses: list[FakeResponse]) -> MagicMock:
    client = MagicMock()
    client.chat.completions.create.side_effect = responses
    return client


def test_research_agent_happy_path_calls_tools_then_submits():
    search_response = _response(_tool_call("tu_1", "web_search", {"query": "Acme AI funding"}))
    submit_response = _response(
        _tool_call(
            "tu_2",
            "submit_research",
            {
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
    stalling_response = _response(text="still thinking...")
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
    search_response = _response(_tool_call("tu_1", "web_search", {"query": "Acme AI"}))
    submit_response = _response(
        _tool_call(
            "tu_2",
            "submit_research",
            {"summary": "Limited information found.", "signals": [], "sources": []},
        )
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
    submit_response = _response(
        _tool_call("tu_1", "submit_research", {"summary": "ok", "signals": [], "sources": []})
    )
    client = _fake_client([submit_response])

    research_company(
        "Acme AI", domain="acme.ai", client=client,
        tool_impls={"web_search": MagicMock(), "fetch_page": MagicMock()},
    )

    sent_messages = client.chat.completions.create.call_args.kwargs["messages"]
    assert "acme.ai" in sent_messages[1]["content"]


def test_research_company_handles_llm_api_error():
    client = MagicMock()
    client.chat.completions.create.side_effect = openai.APIConnectionError(
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
    )

    result = research_company(
        "Acme AI", client=client,
        tool_impls={"web_search": MagicMock(), "fetch_page": MagicMock()},
    )

    assert result.success is False
    assert "LLM call failed" in result.error


def test_research_company_handles_client_side_error_not_just_api_error():
    # Regression test: a missing/invalid API key makes the real OpenAI SDK
    # raise a client-side error before any HTTP request is made in some
    # configurations — discovered for the original Anthropic integration
    # via a live smoke test, not by inspection, and still worth guarding
    # against the provider's OpenAI-compatible endpoint. Catching only
    # openai.APIError would
    # let this escape uncaught all the way to a raw 500, skipping the
    # AgentLog audit trail entirely. Any exception from the LLM call must
    # degrade to a failed result, not crash the pipeline.
    client = MagicMock()
    client.chat.completions.create.side_effect = TypeError(
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
    bad_submit_response = _response(
        _tool_call("tu_1", "submit_research", {"summary": "ok", "signals": []})
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
