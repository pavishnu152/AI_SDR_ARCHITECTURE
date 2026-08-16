"""
Mocked tests for the Guardrail Agent. No real API calls.

The most important test here isn't the happy path — it's proving the
fail-closed behavior: if the LLM call itself fails, the agent must NOT
report success, because a caller that doesn't check `.success` and just
reads `.output.approved` would otherwise crash instead of silently
approving a draft. This is exactly the kind of thing to actually assert,
not just claim in a docstring.
"""
from dataclasses import dataclass
from unittest.mock import MagicMock

import anthropic
import httpx
import pytest

from src.agents.guardrail_agent import check_draft
from src.schemas.lead import DraftOutput, ResearchOutput, Signal


@dataclass
class FakeBlock:
    type: str
    id: str = ""
    name: str = ""
    input: dict = None


@dataclass
class FakeResponse:
    content: list


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


def test_check_draft_approves_when_claims_are_supported(sample_research):
    draft = DraftOutput(
        channel="email",
        message="Congrats on the $12M Series A — curious if you're exploring AI SDR tools?",
    )
    fake_response = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                id="tu_1",
                name="submit_verdict",
                input={
                    "approved": True,
                    "unsupported_claims": [],
                    "notes": "The $12M Series A claim matches the research signal directly.",
                },
            )
        ]
    )
    client = MagicMock()
    client.messages.create.return_value = fake_response

    result = check_draft(sample_research, draft, client=client)

    assert result.success is True
    assert result.output.approved is True
    assert result.output.unsupported_claims == []


def test_check_draft_flags_unsupported_claims(sample_research):
    draft = DraftOutput(
        channel="email",
        message="Congrats on your $50M Series C and your 200-person engineering team!",
    )
    fake_response = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                id="tu_1",
                name="submit_verdict",
                input={
                    "approved": False,
                    "unsupported_claims": [
                        "$50M Series C",
                        "200-person engineering team",
                    ],
                    "notes": "Research only supports a $12M Series A; no headcount data exists.",
                },
            )
        ]
    )
    client = MagicMock()
    client.messages.create.return_value = fake_response

    result = check_draft(sample_research, draft, client=client)

    assert result.success is True
    assert result.output.approved is False
    assert len(result.output.unsupported_claims) == 2


def test_check_draft_fails_closed_on_api_error(sample_research):
    draft = DraftOutput(channel="email", message="Hello there.")
    client = MagicMock()
    client.messages.create.side_effect = anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )

    result = check_draft(sample_research, draft, client=client)

    # success=False here is the fail-closed signal: the caller must treat
    # this as "cannot confirm approval", never fall back to a default of
    # approved=True.
    assert result.success is False
    assert result.output is None


def test_check_draft_handles_missing_tool_use_block(sample_research):
    draft = DraftOutput(channel="email", message="Hello there.")
    client = MagicMock()
    client.messages.create.return_value = FakeResponse(content=[])

    result = check_draft(sample_research, draft, client=client)

    assert result.success is False
    assert "did not call submit_verdict" in result.error


def test_check_draft_handles_invalid_payload(sample_research):
    # Missing the required "notes" key — GuardrailVerdict validation must fail.
    draft = DraftOutput(channel="email", message="Hello there.")
    client = MagicMock()
    client.messages.create.return_value = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use", id="tu_1", name="submit_verdict",
                input={"approved": True, "unsupported_claims": []},
            )
        ]
    )

    result = check_draft(sample_research, draft, client=client)

    assert result.success is False
    assert "invalid submit_verdict payload" in result.error
