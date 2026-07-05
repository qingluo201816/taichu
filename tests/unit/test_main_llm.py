"""应用组装层 LLM 注入测试。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from taichu.config import Settings
from taichu.infrastructure.llm.mock import MVPNoRealLLMChatModel
from taichu.main import create_app


class MainLLMAssemblyTest(unittest.TestCase):
    """验证默认运行链路使用真实 LLM 工厂。"""

    def test_create_app_uses_configured_llm_factory_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            app_settings = Settings(project_assets_dir=Path(temporary_directory))
            mock_model = MVPNoRealLLMChatModel()

            with patch("taichu.main.create_llm", return_value=mock_model) as spy:
                create_app(app_settings=app_settings)

            spy.assert_called_once_with(app_settings)

    def test_injected_llm_is_reserved_for_tests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            app_settings = Settings(project_assets_dir=Path(temporary_directory))
            mock_model = MVPNoRealLLMChatModel()

            with patch("taichu.main.create_llm") as spy:
                create_app(app_settings=app_settings, llm=mock_model)

            spy.assert_not_called()
