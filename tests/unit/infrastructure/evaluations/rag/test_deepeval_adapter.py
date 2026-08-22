import asyncio
from decimal import Decimal

from pydantic import BaseModel

from taichu.application.contracts.llm import (
    LLMCost,
    LLMModelProfile,
    LLMRequest,
    LLMResponse,
    LLMUsage,
)
from taichu.infrastructure.evaluations.rag.deepeval_adapter import TaichuDeepEvalLLM


class _Verdict(BaseModel):
    verdict: str


def test_deepeval_adapter_uses_unified_gateway_and_structured_output() -> None:
    class GatewayFake:
        request: LLMRequest | None = None

        async def complete(self, request: LLMRequest) -> LLMResponse:
            self.request = request
            return LLMResponse(
                text='{"verdict":"yes"}',
                model_id="judge",
                upstream_model="judge",
                usage=LLMUsage(),
                cost=LLMCost(amount=Decimal("0")),
            )

        def list_models(self) -> list[LLMModelProfile]:
            return []

    gateway = GatewayFake()
    adapter = TaichuDeepEvalLLM(gateway, "judge")  # type: ignore[arg-type]

    result = asyncio.run(adapter.a_generate("判断", schema=_Verdict))

    assert result == _Verdict(verdict="yes")
    assert gateway.request is not None
    assert gateway.request.task_type == "rag_evaluation_judge"
    assert gateway.request.response_mode == "json"
