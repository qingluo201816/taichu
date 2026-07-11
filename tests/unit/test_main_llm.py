"""应用组装层 LLM 注入测试。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from taichu.application.contracts.llm import LLMModelIdentity
from taichu.config import Settings
from taichu.infrastructure.llm.factory import LLMRuntime
from taichu.infrastructure.llm.mock import MVPNoRealLLMChatModel
from taichu.main import create_app


class MainLLMAssemblyTest(unittest.TestCase):
    """验证默认运行链路使用真实 LLM 工厂。"""

    def test_create_app_uses_configured_llm_factory_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            app_settings = Settings(project_assets_dir=Path(temporary_directory))
            mock_model = MVPNoRealLLMChatModel()
            identity = LLMModelIdentity(
                provider="test",
                model_id="test-model",
                family="test-model",
                endpoint_kind="test",
                known=True,
            )
            runtime = LLMRuntime(
                chat_model=mock_model,
                model_identity=identity,
                configured=True,
            )

            with patch("taichu.main.create_llm", return_value=runtime) as spy:
                app = create_app(app_settings=app_settings)

            spy.assert_called_once_with(app_settings)
            self.assertEqual(
                app.state.knowledge_extraction_service._llm.model_identity,
                identity,
            )

    def test_injected_llm_is_reserved_for_tests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            app_settings = Settings(project_assets_dir=Path(temporary_directory))
            mock_model = MVPNoRealLLMChatModel()

            with patch("taichu.main.create_llm") as spy:
                app = create_app(app_settings=app_settings, llm=mock_model)

            spy.assert_not_called()
            identity = app.state.knowledge_extraction_service._llm.model_identity
            self.assertFalse(identity.known)
            self.assertEqual(identity.unknown_reason, "注入模型未提供身份。")

    def test_injected_llm_uses_explicit_identity_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            app_settings = Settings(project_assets_dir=Path(temporary_directory))
            mock_model = MVPNoRealLLMChatModel()
            identity = LLMModelIdentity(
                provider="test",
                model_id="test-model",
                family="test-model",
                endpoint_kind="test",
                known=True,
            )

            app = create_app(
                app_settings=app_settings,
                llm=mock_model,
                llm_model_identity=identity,
            )

            self.assertEqual(
                app.state.knowledge_extraction_service._llm.model_identity,
                identity,
            )
