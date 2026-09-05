"""
Mocked tests for the Scoring Agent. The Gemini (OpenAI-compatible) client is
faked; no real API calls. Uses the real ICP config (loaded once, cheap) so
the tests exercise the actual rubric text being injected into the prompt,
but the "model" itself is fully controlled.
"""
import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import openai
import pytest

from src.agents.scoring_agent import score_lead
from src.core.icp import ICPConfig
from src.schemas.lead import ResearchOutput, Signal

REAL_ICP_PATH = Path(__file__).parents[2] / "configs" / "icp_ai_native_b2b.yaml"


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
    content: str | None = None
    tool_calls: list | None = None


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeUsage:
    prompt_tokens: int
    completion_tokens: int


@dataclass
class FakeResponse:
    choices: list
    usage: "FakeUsage | None" = None


def _tool_call(call_id: str, name: str, payload: dict) -> FakeToolCall:
    return FakeToolCall(
        id=call_id,
        function=FakeFunction(
            name=name,
            arguments=json.dumps(payload),
        ),
    )


@pytest.fixture
def icp():
    return ICPConfig.from_yaml(REAL_ICP_PATH)


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
            Signal(
                label="product_ai_mention",
                detail="Homepage describes product as an 'AI copilot'",
                source_url="https://acme.ai",
            ),
        ],
        sources=[
            "https://news.example.com/acme-series-a",
            "https://acme.ai",
        ],
    )


def test_score_lead_happy_path(icp, sample_research):
    fake_response = FakeResponse(
        choices=[
            FakeChoice(
                message=FakeMessage(
                    tool_calls=[
                        _tool_call(
                            "tu_1",
                            "submit_score",
                            {
                                "score": 82,
                                "confidence": 0.85,
                                "reasoning": (
                                    "Strong fit: recent Series A funding and explicit "
                                    "'AI copilot' product positioning."
                                ),
                            },
                        )
                    ]
                )
            )
        ],
        usage=FakeUsage(
            prompt_tokens=500,
            completion_tokens=80,
        ),
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_response

    result = score_lead(
        sample_research,
        icp,
        client=client,
    )

    assert result.success is True
    assert result.output.score == 82

    # Token usage should be captured from response.usage.
    # Gemini pricing has not yet been verified/configured, so cost is None.
    assert result.input_tokens == 500
    assert result.output_tokens == 80
    assert result.cost_usd is None
    assert 0.0 <= result.output.confidence <= 1.0

    # Verify tool_choice was forced, not left to "auto" — this is the core
    # design decision under test, not just the happy-path output.
    _, kwargs = client.chat.completions.create.call_args
    assert kwargs["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_score"},
    }


def test_score_lead_handles_invalid_payload(icp, sample_research):
    fake_response = FakeResponse(
        choices=[
            FakeChoice(
                message=FakeMessage(
                    tool_calls=[
                        _tool_call(
                            "tu_1",
                            "submit_score",
                            {
                                "score": 150,
                                "confidence": 0.5,
                                "reasoning": "out of range score",
                            },
                        )
                    ]
                )
            )
        ]
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_response

    result = score_lead(
        sample_research,
        icp,
        client=client,
    )

    assert result.success is False
    assert "invalid" in result.error.lower()


def test_score_lead_handles_missing_tool_use_block(icp, sample_research):
    fake_response = FakeResponse(
        choices=[
            FakeChoice(
                message=FakeMessage(tool_calls=[])
            )
        ]
    )
    client = MagicMock()
    client.chat.completions.create.return_value = fake_response

    result = score_lead(
        sample_research,
        icp,
        client=client,
    )

    assert result.success is False
    assert "did not call submit_score" in result.error


def test_score_lead_handles_api_error(icp, sample_research):
    client = MagicMock()
    client.chat.completions.create.side_effect = openai.APIConnectionError(
        request=httpx.Request(
            "POST",
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        )
    )

    result = score_lead(
        sample_research,
        icp,
        client=client,
    )

    assert result.success is False
    assert "LLM call failed" in result.error