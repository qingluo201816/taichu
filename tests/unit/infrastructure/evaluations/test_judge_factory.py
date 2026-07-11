"""Tests for semantic evaluation judge assembly."""

from pathlib import Path
from typing import Any
import unittest

from taichu.application.contracts.llm import LLMModelIdentity
from taichu.config import Settings
from taichu.infrastructure.evaluations.judge_factory import (
    create_evaluation_judge,
)
from taichu.infrastructure.llm.factory import LLMRuntime
from taichu.infrastructure.llm.unavailable import UnavailableLLMChatModel


class EvaluationJudgeFactoryTest(unittest.TestCase):
    """Ensure requested and fallback runtimes retain their true identities."""

    def test_settings_have_safe_evaluation_defaults(self) -> None:
        settings = _settings()

        self.assertEqual(
            settings.evaluation_datasets_dir,
            Path("tests/fixtures/evaluations"),
        )
        self.assertEqual(settings.evaluation_judge_model, "")

    def test_empty_judge_model_reuses_fallback_runtime(self) -> None:
        identity = LLMModelIdentity(
            provider="test",
            model_id="fallback-model",
            family="fallback",
            endpoint_kind="test",
            known=True,
        )
        runtime = LLMRuntime(
            chat_model=UnavailableLLMChatModel(),
            model_identity=identity,
            configured=True,
        )

        judge = create_evaluation_judge(
            _settings(evaluation_judge_model=""),
            runtime,
        )

        self.assertTrue(judge.available)
        self.assertEqual(judge.model_identity, identity)

    def test_explicit_judge_model_uses_requested_runtime_identity(self) -> None:
        judge = create_evaluation_judge(
            _settings(
                deepseek_api_key="test-key",
                deepseek_api_base="https://example.invalid/v1",
                deepseek_model="generation-model",
                evaluation_judge_model="judge-model",
            )
        )

        self.assertTrue(judge.available)
        self.assertEqual(judge.model_identity.provider, "deepseek")
        self.assertEqual(judge.model_identity.model_id, "judge-model")
        self.assertEqual(judge.model_identity.family, "judge-model")

    def test_explicit_model_never_falls_back_when_credentials_are_missing(self) -> None:
        fallback_identity = LLMModelIdentity(
            provider="test",
            model_id="configured-fallback",
            family="fallback",
            endpoint_kind="test",
            known=True,
        )
        fallback = LLMRuntime(
            chat_model=UnavailableLLMChatModel(),
            model_identity=fallback_identity,
            configured=True,
        )

        judge = create_evaluation_judge(
            _settings(
                deepseek_api_key="",
                evaluation_judge_model="requested-judge",
            ),
            fallback,
        )

        self.assertFalse(judge.available)
        self.assertFalse(judge.model_identity.known)
        self.assertEqual(judge.model_identity.model_id, "requested-judge")
        self.assertIn("缺少", judge.model_identity.unknown_reason or "")


def _settings(**values: Any) -> Settings:
    return Settings(**{"_env_file": None, **values})


if __name__ == "__main__":
    unittest.main()
