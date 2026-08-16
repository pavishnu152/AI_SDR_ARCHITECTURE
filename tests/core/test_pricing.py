from src.core.pricing import estimate_cost_usd, extract_token_usage


def test_estimate_cost_usd_known_model():
    cost = estimate_cost_usd("claude-haiku-4-5-20251001", input_tokens=1_000_000, output_tokens=0)
    assert cost == 1.00  # $1.00 / Mtok input, per MODEL_PRICING


def test_estimate_cost_usd_combines_input_and_output():
    cost = estimate_cost_usd(
        "claude-sonnet-5", input_tokens=500_000, output_tokens=100_000
    )
    # 0.5 * $2.00 + 0.1 * $10.00 = 1.00 + 1.00 = 2.00
    assert cost == 2.00


def test_estimate_cost_usd_unknown_model_returns_none():
    assert estimate_cost_usd("some-future-model", 1000, 1000) is None


class _FakeUsage:
    def __init__(self, input_tokens, output_tokens):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeResponseWithUsage:
    def __init__(self, input_tokens, output_tokens):
        self.usage = _FakeUsage(input_tokens, output_tokens)


class _FakeResponseWithoutUsage:
    pass


def test_extract_token_usage_reads_real_usage_object():
    response = _FakeResponseWithUsage(input_tokens=123, output_tokens=45)
    assert extract_token_usage(response) == (123, 45)


def test_extract_token_usage_defaults_to_zero_when_missing():
    response = _FakeResponseWithoutUsage()
    assert extract_token_usage(response) == (0, 0)
