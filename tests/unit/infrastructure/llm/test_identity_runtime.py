"""LLM runtime identity and adapter tests."""

import unittest
from unittest.mock import patch

from taichu.application.contracts.llm import LLMModelIdentity
from taichu.config import Settings
from taichu.infrastructure.llm.adapter import LangChainLLMAdapter
from taichu.infrastructure.llm.factory import create_llm
from taichu.infrastructure.llm.mock import MVPNoRealLLMChatModel
from taichu.infrastructure.llm.providers.deepseek import deepseek_model_identity


class LLMRuntimeIdentityTest(unittest.IsolatedAsyncioTestCase):
    """Verify model identity comes from runtime assembly, not request labels."""

    def test_configured_runtime_reports_actual_deepseek_model_parameter(self) -> None:
        chat_model = MVPNoRealLLMChatModel()
        settings = Settings(
            deepseek_api_key="test-key",
            deepseek_api_base="https://example.invalid/v1",
            deepseek_model=" deepseek-chat ",
        )

        with patch(
            "taichu.infrastructure.llm.factory.create_deepseek",
            return_value=chat_model,
        ) as create_deepseek_spy:
            runtime = create_llm(settings)

        create_deepseek_spy.assert_called_once_with(
            settings,
            model="deepseek-chat",
        )
        self.assertIs(runtime.chat_model, chat_model)
        self.assertTrue(runtime.configured)
        self.assertEqual(runtime.model_identity.provider, "deepseek")
        self.assertEqual(runtime.model_identity.model_id, "deepseek-chat")
        self.assertEqual(runtime.model_identity.family, "deepseek-chat")
        self.assertTrue(runtime.model_identity.known)

    def test_unconfigured_runtime_keeps_target_identity_unknown(self) -> None:
        runtime = create_llm(
            Settings(deepseek_api_key="", deepseek_model="deepseek-chat")
        )

        self.assertFalse(runtime.configured)
        self.assertFalse(runtime.model_identity.known)
        self.assertEqual(runtime.model_identity.provider, "deepseek")
        self.assertEqual(runtime.model_identity.model_id, "deepseek-chat")
        self.assertEqual(
            runtime.model_identity.unknown_reason,
            "当前未配置可用模型。",
        )

    def test_versioned_deepseek_model_uses_stable_family(self) -> None:
        identity = deepseek_model_identity("deepseek-v4-pro")

        self.assertEqual(identity.model_id, "deepseek-v4-pro")
        self.assertEqual(identity.family, "deepseek-v4")

    async def test_adapter_exposes_identity_from_its_runtime(self) -> None:
        identity = LLMModelIdentity(
            provider="test",
            model_id="identity-model",
            family="identity-model",
            endpoint_kind="test",
            known=True,
        )
        adapter = LangChainLLMAdapter(
            MVPNoRealLLMChatModel(response_text="模型响应"),
            identity,
        )

        self.assertEqual(adapter.model_identity, identity)
        self.assertEqual(await adapter.complete("输入"), "模型响应")
