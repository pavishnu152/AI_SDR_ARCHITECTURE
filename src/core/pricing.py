"""
Approximate Anthropic API pricing, for cost estimation in AgentLog/eval
reports only — NOT a source of truth for billing.

IMPORTANT: these constants are a snapshot (checked August 2026) and WILL
go stale — Anthropic changes pricing over time, and Sonnet 5's current
rate below is itself a limited-time promotional rate. Before relying on
this for any real budget decision, verify current pricing at
https://www.anthropic.com/pricing. This module exists so the eval harness
and logs can report an order-of-magnitude cost per lead ("~$0.02", not
"$4.87") for engineering decisions like the Haiku/Sonnet tiering choice in
architecture.md — not for finance-grade accounting.
"""
from dataclasses import dataclass
from typing import Any

PRICING_LAST_VERIFIED = "2026-08-07"


@dataclass(frozen=True)
class ModelPricing:
    input_per_mtok_usd: float
    output_per_mtok_usd: float


# Per-million-token USD pricing. Update PRICING_LAST_VERIFIED when changed.
MODEL_PRICING: dict[str, ModelPricing] = {
    "claude-haiku-4-5-20251001": ModelPricing(input_per_mtok_usd=1.00, output_per_mtok_usd=5.00),
    "claude-sonnet-5": ModelPricing(input_per_mtok_usd=2.00, output_per_mtok_usd=10.00),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """
    Returns None (not 0.0) for an unrecognized model — silently reporting
    $0 cost for a model we don't have pricing for would be misleading in a
    cost report, whereas None makes "we don't know" explicit and easy to
    filter out of an average.
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
    Pulls (input_tokens, output_tokens) off an Anthropic response, tolerant
    of test doubles that don't set `.usage` at all — getattr chain returns
    (0, 0) rather than raising, which is what keeps every existing mocked
    agent test passing without needing a `.usage` attribute bolted onto
    every fake response object. Shared by all four agents rather than
    duplicated per file.
    """
    usage = getattr(response, "usage", None)
    return getattr(usage, "input_tokens", 0) or 0, getattr(usage, "output_tokens", 0) or 0
