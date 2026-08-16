"""统一 LLM 费用规范化。"""

from decimal import Decimal

from taichu.application.contracts.llm import (
    LLMCost,
    LLMModelProfile,
    LLMUsage,
)


_MILLION = Decimal("1000000")


def calculate_cost(
    profile: LLMModelProfile,
    usage: LLMUsage,
    actual_amount: Decimal | None,
    actual_currency: str | None = None,
) -> LLMCost:
    """实际费用优先，否则仅在所需价格齐全时进行 Decimal 预估。"""
    if actual_amount is not None:
        return LLMCost(
            amount=actual_amount,
            currency=actual_currency or profile.currency,
            kind="actual",
        )

    regular_input = usage.input_tokens
    if (
        profile.wire_protocol != "anthropic_messages"
        and regular_input is not None
        and usage.cached_input_tokens is not None
    ):
        regular_input = max(0, regular_input - usage.cached_input_tokens)
    regular_output = usage.output_tokens
    if regular_output is not None and usage.reasoning_tokens is not None:
        regular_output = max(0, regular_output - usage.reasoning_tokens)
    components = (
        (regular_input, profile.input_price_per_million),
        (usage.cached_input_tokens, profile.cached_input_price_per_million),
        (regular_output, profile.output_price_per_million),
        (usage.reasoning_tokens, profile.reasoning_output_price_per_million),
    )
    present = [(tokens, price) for tokens, price in components if tokens is not None]
    if not present or any(price is None for _, price in present):
        return LLMCost(currency=profile.currency)
    amount = sum(
        (Decimal(tokens) * price / _MILLION for tokens, price in present if price),
        Decimal("0"),
    )
    return LLMCost(amount=amount, currency=profile.currency, kind="estimated")
