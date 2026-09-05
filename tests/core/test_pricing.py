from src.core.pricing import estimate_cost_usd


def test_estimate_cost_usd_unknown_model():
    cost = estimate_cost_usd(
        "gemini-2.5-flash",
        input_tokens=1_000_000,
        output_tokens=0,
    )
    assert cost is None


def test_estimate_cost_usd_returns_none_for_unverified_model():
    cost = estimate_cost_usd(
        "some-unverified-model",
        input_tokens=500_000,
        output_tokens=100_000,
    )
    assert cost is None


def test_estimate_cost_usd_zero_tokens_for_unknown_model():
    cost = estimate_cost_usd(
        "gemini-2.5-flash",
        input_tokens=0,
        output_tokens=0,
    )
    assert cost is None