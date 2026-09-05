"""Mocked tests for the Drafting Agent. No real API calls."""
import json
from dataclasses import dataclass
from unittest.mock import MagicMock

import httpx
import openai
import pytest

from src.agents.drafting_agent import draft_outreach
from src.schemas.lead import ResearchOutput, ScoreOutput, Signal


@dataclass
class FakeFunction:
    name: str
    arguments: str


@dataclass
class FakeToolCall:
    id: str
    function: FakeFunction


@dataclass
class FakeMessage:
    content: str | None = None
    tool_calls: list | None = None


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeResponse:
    choices: list


def _tool_call(call_id: str, name: str, payload: dict) -> FakeToolCall:
    return FakeToolCall(id=call_id, function=FakeFunction(name=name, arguments=json.dumps(payload)))


@pytest.fixture
def sample_research():
    return ResearchOutput(
        summary="Acme AI is a Series A startup building an AI copilot for support teams.",
        signals=[
            Signal(
                label="recent_funding",
                detail="Raised $12M Series A led by ExampleVC",
                source_url="https://news.example.com/acme-series-a",
            ),
        ],
        sources=["https://news.example.com/acme-series-a"],
    )


@pytest.fixture
def sample_score():
    return ScoreOutput(score=82, confidence=0.85, reasoning="Strong fit: funding + AI product.")


def test_draft_outreach_happy_path(sample_research, sample_score):
    fake_response = FakeResponse(
        choices=[
            FakeChoice(
                message=FakeMessage(
                    tool_calls=[
                        _tool_call(
                            "tu_1",
                            "submit_draft",
                            {
                                "channel": "email",
                                "message": (
                                    "Hi Acme AI team, congrats on the $12M Series A. Curious if "
                                    "you're exploring AI-native tools for outbound — worth a "
                                    "quick chat? — The AI SDR team"
                                ),
                            },
                        )
                    ]
                )
            )
        ]
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_response

    result = draft_outreach("Acme AI", sample_research, sample_score, client=client)

    assert result.success is True
    assert result.output.channel == "email"
    assert len(result.output.message) > 0

    _, kwargs = client.chat.completions.create.call_args
    assert kwargs["tool_choice"] == {"type": "function", "function": {"name": "submit_draft"}}


def test_draft_outreach_handles_missing_tool_use_block(sample_research, sample_score):
    client = MagicMock()
    client.chat.completions.create.return_value = FakeResponse(
        choices=[FakeChoice(message=FakeMessage(tool_calls=[]))]
    )

    result = draft_outreach("Acme AI", sample_research, sample_score, client=client)

    assert result.success is False
    assert "did not call submit_draft" in result.error


def test_draft_outreach_handles_api_error(sample_research, sample_score):
    client = MagicMock()
    client.chat.completions.create.side_effect = openai.APIConnectionError(
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
    )

    result = draft_outreach("Acme AI", sample_research, sample_score, client=client)

    assert result.success is False
    assert "LLM call failed" in result.error


def test_draft_outreach_handles_invalid_payload(sample_research, sample_score):
    # Missing the required "message" key — DraftOutput validation must fail.
    client = MagicMock()
    client.chat.completions.create.return_value = FakeResponse(
        choices=[
            FakeChoice(
                message=FakeMessage(
                    tool_calls=[_tool_call("tu_1", "submit_draft", {"channel": "email"})]
                )
            )
        ]
    )

    result = draft_outreach("Acme AI", sample_research, sample_score, client=client)

    assert result.success is False
    assert "invalid submit_draft payload" in result.error


def test_draft_outreach_includes_guardrail_feedback_in_revision_prompt(
    sample_research, sample_score
):
    """
    Exercises the self-correction revision path directly at the agent
    level — the orchestrator tests mock draft_outreach entirely, so they
    never actually execute the guardrail_feedback branch of _format_prompt.
    """
    client = MagicMock()
    client.chat.completions.create.return_value = FakeResponse(
        choices=[
            FakeChoice(
                message=FakeMessage(
                    tool_calls=[
                        _tool_call(
                            "tu_1", "submit_draft",
                            {"channel": "email", "message": "revised message"},
                        )
                    ]
                )
            )
        ]
    )

    draft_outreach(
        "Acme AI", sample_research, sample_score, client=client,
        guardrail_feedback=["$50M Series C (unsupported)"],
    )

    sent_prompt = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "$50M Series C (unsupported)" in sent_prompt
    assert "previous draft was rejected" in sent_prompt.lower()
