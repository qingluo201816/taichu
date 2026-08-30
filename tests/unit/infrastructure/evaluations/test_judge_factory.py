"""统一网关驱动的语义裁判组装测试。"""

import asyncio
from decimal import Decimal
from pathlib import Path
import unittest

from taichu.application.contracts.llm import LLMModelIdentity, LLMModelProfile
from taichu.infrastructure.llm.contracts import (
    LLMCost,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMUsage,
)
from taichu.application.evaluations.knowledge_extraction.difference_explainer import (
    DifferenceExplanationBatchOutput,
)
from taichu.config import Settings
from taichu.infrastructure.evaluations.judge_factory import create_evaluation_judge
from taichu.infrastructure.evaluations.llm_judge_adapter import (
    LLMEvaluationJudgeAdapter,
)
from taichu.infrastructure.llm.adapter import GatewayChatModel
from tests.fakes import (
    MVPNoRealLLMChatModel,
    make_test_llm_gateway,
)


class EvaluationJudgeFactoryTest(unittest.TestCase):
    def test_settings_have_safe_evaluation_defaults(self) -> None:
        settings = Settings()
        self.assertEqual(
            settings.evaluation_datasets_dir, Path("tests/fixtures/evaluations")
        )
        self.assertEqual(settings.evaluation_judge_model, "")

    def test_default_judge_reuses_unified_gateway(self) -> None:
        identity = LLMModelIdentity(
            provider="rightcode",
            model_id="deepseek-v4-pro",
            family="deepseek-v4",
            endpoint_kind="openai_responses",
            known=True,
        )
        gateway = make_test_llm_gateway(MVPNoRealLLMChatModel(), identity)
        judge = create_evaluation_judge(
            Settings(),
            GatewayChatModel(gateway, model_id="deepseek-v4-pro"),
            gateway,
            configured=True,
        )
        self.assertTrue(judge.available)
        self.assertEqual(judge.model_identity.model_id, "deepseek-v4-pro")

    def test_unknown_explicit_judge_model_is_unavailable(self) -> None:
        identity = LLMModelIdentity(
            provider="rightcode",
            model_id="deepseek-v4-pro",
            family="deepseek-v4",
            endpoint_kind="openai_responses",
            known=True,
        )
        gateway = make_test_llm_gateway(MVPNoRealLLMChatModel(), identity)
        judge = create_evaluation_judge(
            Settings(evaluation_judge_model="unknown"),
            GatewayChatModel(gateway, model_id="deepseek-v4-pro"),
            gateway,
            configured=True,
        )
        self.assertFalse(judge.available)

    def test_judge_sends_output_contract_as_forced_native_tool(self) -> None:
        class GatewayFake:
            request: LLMRequest | None = None

            async def complete(self, request: LLMRequest) -> LLMResponse:
                self.request = request
                tool_name = request.tools[0].name
                return LLMResponse(
                    text="",
                    model_id="judge",
                    upstream_model="judge",
                    usage=LLMUsage(input_tokens=10, output_tokens=5),
                    cost=LLMCost(amount=Decimal("0")),
                    tool_calls=(
                        LLMToolCall(
                            call_id="call-judge",
                            name=tool_name,
                            arguments_json=(
                                '{"items":[{"explanation_id":"diff-1",'
                                '"summary":"差异说明。"}]}'
                            ),
                        ),
                    ),
                )

            def list_models(self) -> list[LLMModelProfile]:
                return [
                    LLMModelProfile(
                        id="judge",
                        display_name="裁判模型",
                        provider="rightcode",
                        upstream_model="judge",
                        wire_protocol="openai_responses",
                        enabled=True,
                        is_default=True,
                        supports_streaming=True,
                        upstream_verified=True,
                    )
                ]

        gateway = GatewayFake()
        judge = LLMEvaluationJudgeAdapter(  # type: ignore[arg-type]
            GatewayChatModel(gateway, model_id="judge"),
            gateway,
            model_id="judge",
            configured=True,
        )

        result = asyncio.run(
            judge.complete(
                "解释差异。",
                output_schema=DifferenceExplanationBatchOutput,
            )
        )

        self.assertIsNotNone(gateway.request)
        assert gateway.request is not None
        self.assertEqual(
            gateway.request.tool_choice,
            "required",
        )
        self.assertEqual(len(gateway.request.tools), 1)
        self.assertTrue(gateway.request.tools[0].strict)
        self.assertIn("items", gateway.request.tools[0].parameters["properties"])
        self.assertNotIn("JSON", gateway.request.messages[0].content)
        self.assertEqual(
            result.token_usage,
            {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )
        self.assertIsInstance(result.output, DifferenceExplanationBatchOutput)
        self.assertEqual(result.output.items[0].explanation_id, "diff-1")
