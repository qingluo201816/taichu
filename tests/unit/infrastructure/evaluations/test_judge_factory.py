"""统一网关驱动的语义裁判组装测试。"""

from pathlib import Path
import unittest

from taichu.application.contracts.llm import LLMModelIdentity
from taichu.config import Settings
from taichu.infrastructure.evaluations.judge_factory import create_evaluation_judge
from taichu.infrastructure.llm.adapter import LangChainLLMAdapter
from taichu.infrastructure.llm.mock import MVPNoRealLLMChatModel


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
        gateway = LangChainLLMAdapter(MVPNoRealLLMChatModel(), identity)
        judge = create_evaluation_judge(
            Settings(), gateway, configured=True
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
        gateway = LangChainLLMAdapter(MVPNoRealLLMChatModel(), identity)
        judge = create_evaluation_judge(
            Settings(evaluation_judge_model="unknown"),
            gateway,
            configured=True,
        )
        self.assertFalse(judge.available)
