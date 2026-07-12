"""应用组合根的统一 LLM 网关测试。"""

import tempfile
import unittest
from pathlib import Path
from pydantic import SecretStr

from taichu.application.contracts.llm import LLMModelIdentity
from taichu.config import Settings
from taichu.infrastructure.llm.mock import MVPNoRealLLMChatModel
from taichu.main import create_app
from tests.fakes import InMemoryKnowledgeRepository


class MainLLMAssemblyTest(unittest.TestCase):
    def test_default_runtime_uses_rightcode_catalog_without_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_app(
                Settings(
                    project_assets_dir=Path(temporary_directory),
                    rightcode_api_key=SecretStr(""),
                ),
                knowledge_repository=InMemoryKnowledgeRepository(),
            )

        self.assertEqual(len(app.state.llm_gateway.list_models()), 10)
        self.assertFalse(app.state.llm_gateway.configured)

    def test_injected_llm_is_reserved_for_tests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_app(
                Settings(
                    project_assets_dir=Path(temporary_directory),
                ),
                llm=MVPNoRealLLMChatModel(),
                knowledge_repository=InMemoryKnowledgeRepository(),
            )

        identity = app.state.knowledge_extraction_service._llm.model_identity
        self.assertFalse(identity.known)
        self.assertEqual(identity.unknown_reason, "注入模型未提供身份。")

    def test_injected_llm_uses_explicit_identity_when_provided(self) -> None:
        identity = LLMModelIdentity(
            provider="test",
            model_id="test-model",
            family="test-model",
            endpoint_kind="test",
            known=True,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            app = create_app(
                Settings(
                    project_assets_dir=Path(temporary_directory),
                ),
                llm=MVPNoRealLLMChatModel(),
                llm_model_identity=identity,
                knowledge_repository=InMemoryKnowledgeRepository(),
            )

        self.assertEqual(
            app.state.knowledge_extraction_service._llm.model_identity,
            identity,
        )
