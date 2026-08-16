"""
Mocked tests for the Scoring Agent. The Anthropic client is faked; no real
API calls. Uses the real ICP config (loaded once, cheap) so the tests
exercise the actual rubric text being injected into the prompt, but the
"model" itself is fully controlled.
"""
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import anthropic
import httpx
import pytest

from src.agents.scoring_agent import score_lead
from src.core.icp import ICPConfig
from src.schemas.lead import ResearchOutput, Signal

REAL_ICP_PATH = Path(__file__).parents[2] / "configs" / "icp_ai_native_b2b.yaml"


@dataclass
class FakeBlock:
    type: str
    id: str = ""
    name: str = ""
    input: dict = None


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class FakeResponse:
    content: list
    usage: "FakeUsage | None" = None


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
        sources=["https://news.example.com/acme-series-a", "https://acme.ai"],
    )


def test_score_lead_happy_path(icp, sample_research):
    fake_response = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                id="tu_1",
                name="submit_score",
                input={
                    "score": 82,
                    "confidence": 0.85,
                    "reasoning": (
                        "Strong fit: recent Series A funding and explicit 'AI copilot' "
                        "product positioning."
                    ),
                },
            )
        ],
        usage=FakeUsage(input_tokens=500, output_tokens=80),
    )
    client = MagicMock()
    client.messages.create.return_value = fake_response

    result = score_lead(sample_research, icp, client=client)

    assert result.success is True
    assert result.output.score == 82

    # Token usage and cost should be captured from response.usage, not left
    # at the zero-default that test doubles without .usage fall back to.
    assert result.input_tokens == 500
    assert result.output_tokens == 80
    assert result.cost_usd == pytest.approx(500 / 1_000_000 * 1.00 + 80 / 1_000_000 * 5.00)
    assert 0.0 <= result.output.confidence <= 1.0

    # Verify tool_choice was forced, not left to "auto" — this is the core
    # design decision under test, not just the happy-path output.
    _, kwargs = client.messages.create.call_args
    assert kwargs["tool_choice"] == {"type": "tool", "name": "submit_score"}


def test_score_lead_handles_invalid_payload(icp, sample_research):
    fake_response = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                id="tu_1",
                name="submit_score",
                input={"score": 150, "confidence": 0.5, "reasoning": "out of range score"},
            )
        ]
    )
    client = MagicMock()
    client.messages.create.return_value = fake_response

    result = score_lead(sample_research, icp, client=client)

    assert result.success is False
    assert "invalid" in result.error.lower()


def test_score_lead_handles_missing_tool_use_block(icp, sample_research):
    fake_response = FakeResponse(content=[])
    client = MagicMock()
    client.messages.create.return_value = fake_response

    result = score_lead(sample_research, icp, client=client)

    assert result.success is False
    assert "did not call submit_score" in result.error


def test_score_lead_handles_api_error(icp, sample_research):
    client = MagicMock()
    client.messages.create.side_effect = anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )

    result = score_lead(sample_research, icp, client=client)

    assert result.success is False
    assert "LLM call failed" in result.error
