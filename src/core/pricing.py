"""
Approximate Google Gemini API pricing for cost estimation in AgentLog/eval
reports only — NOT a source of truth for billing.

IMPORTANT:
These constants must be verified against Google's current Gemini API pricing
before being used for any real budget or finance decision. Provider pricing,
model availability, and billing rules can change over time.

Official pricing:
https://ai.google.dev/gemini-api/docs/pricing

This module exists so the eval harness and AgentLog can report estimated
order-of-magnitude cost per lead. It is NOT intended for finance-grade
accounting.

If pricing for the configured Gemini model is not explicitly recorded here,
estimate_cost_usd() returns None rather than incorrectly reporting $0.
"""

from dataclasses import dataclass
from typing import Any

# Update this whenever the pricing values below are verified against Google's
# official pricing documentation.
PRICING_LAST_VERIFIED = "NOT_YET_VERIFIED"


@dataclass(frozen=True)
class ModelPricing:
    input_per_mtok_usd: float
    output_per_mtok_usd: float


# Per-million-token USD pricing.
#
# IMPORTANT:
# Do not insert unverified pricing values here.
#
# Once the exact Gemini model(s) and current Google pricing are verified,
# add them using:
#
# "gemini-model-name": ModelPricing(
#     input_per_mtok_usd=<verified_input_price>,
#     output_per_mtok_usd=<verified_output_price>,
# ),
#
# Keeping an unverified model out of this table makes the cost report
# fail-safe instead of producing misleading numbers.
MODEL_PRICING: dict[str, ModelPricing] = {}


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float | None:
    """
    Estimate USD cost for a Gemini model.

    Returns None when pricing for the requested model is not configured.
    This is intentional: silently reporting $0 for an unknown model would
    produce misleading cost reports.
    """
    pricing = MODEL_PRICING.get(model)

    if pricing is None:
        return None

    return (
        input_tokens / 1_000_000 * pricing.input_per_mtok_usd
        + output_tokens / 1_000_000 * pricing.output_per_mtok_usd
    )


def extract_token_usage(response: Any) -> tuple[int, int]:
    """
    Extract (input_tokens, output_tokens) from an OpenAI-compatible response.

    Gemini's OpenAI-compatible endpoint exposes usage information using the
    OpenAI-shaped response object expected by the existing application.

    The getattr chain is intentionally tolerant of mocked responses that do
    not define usage information, returning (0, 0) instead of raising.

    This helper is shared by all four agents.
    """
    usage = getattr(response, "usage", None)

    return (
        getattr(usage, "prompt_tokens", 0) or 0,
        getattr(usage, "completion_tokens", 0) or 0,
    )