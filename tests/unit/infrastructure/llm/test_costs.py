from decimal import Decimal

from taichu.application.contracts.llm import LLMModelProfile, LLMUsage
from taichu.infrastructure.llm.costs import calculate_cost


def _profile(wire_protocol: str) -> LLMModelProfile:
    return LLMModelProfile(
        id="model-under-test",
        display_name="测试模型",
        provider="rightcode",
        upstream_model="model-under-test",
        wire_protocol=wire_protocol,  # type: ignore[arg-type]
        base_url_key="MODEL_BASE_URL",
        enabled=True,
        is_default=False,
        supports_streaming=True,
        input_price_per_million=Decimal("10"),
        cached_input_price_per_million=Decimal("1"),
        output_price_per_million=Decimal("20"),
    )


def test_anthropic_cost_keeps_uncached_input_separate_from_cache_reads() -> None:
    cost = calculate_cost(
        _profile("anthropic_messages"),
        LLMUsage(
            input_tokens=100,
            cached_input_tokens=400,
            output_tokens=50,
            total_tokens=550,
        ),
        actual_amount=None,
    )

    assert cost.amount == Decimal("0.0024")


def test_openai_cost_treats_cached_tokens_as_input_subset() -> None:
    cost = calculate_cost(
        _profile("openai_responses"),
        LLMUsage(
            input_tokens=100,
            cached_input_tokens=40,
            output_tokens=50,
            total_tokens=150,
        ),
        actual_amount=None,
    )

    assert cost.amount == Decimal("0.00164")
