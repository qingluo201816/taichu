"""模型目录和测试注入适配器测试。"""

import unittest

from taichu.application.contracts.llm import (
    LLMMessage,
    LLMModelIdentity,
    LLMRequest,
)
from taichu.config import Settings
from taichu.infrastructure.llm.adapter import LangChainLLMAdapter
from taichu.infrastructure.llm.catalog import LLMModelCatalog
from taichu.infrastructure.llm.mock import MVPNoRealLLMChatModel


class LLMRuntimeIdentityTest(unittest.IsolatedAsyncioTestCase):
    def test_catalog_uses_deepseek_v4_pro_as_only_default(self) -> None:
        catalog = LLMModelCatalog(Settings())
        defaults = [item for item in catalog.list_models() if item.is_default]
        self.assertEqual([item.id for item in defaults], ["deepseek-v4-pro"])

    async def test_adapter_preserves_messages_and_identity(self) -> None:
        identity = LLMModelIdentity(
            provider="test",
            model_id="identity-model",
            family="identity-model",
            endpoint_kind="test",
            known=True,
        )
        adapter = LangChainLLMAdapter(
            MVPNoRealLLMChatModel(response_text="模型响应"), identity
        )
        response = await adapter.complete(
            LLMRequest(
                model_id="identity-model",
                messages=(LLMMessage(role="user", content="输入"),),
                task_type="test",
                task_name="测试",
            )
        )

        self.assertEqual(adapter.model_identity, identity)
        self.assertEqual(response.text, "模型响应")
