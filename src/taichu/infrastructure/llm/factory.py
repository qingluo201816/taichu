"""根据配置创建 LLM 实例。"""

from langchain_core.language_models.chat_models import BaseChatModel

from taichu.config import Settings
from taichu.infrastructure.llm.providers.deepseek import create_deepseek
from taichu.infrastructure.llm.unavailable import UnavailableLLMChatModel


def create_llm(settings: Settings) -> BaseChatModel:
    """创建配置指定的聊天模型。"""
    if settings.llm_provider == "deepseek":
        if not _deepseek_configured(settings):
            return UnavailableLLMChatModel()
        return create_deepseek(settings)
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


def _deepseek_configured(settings: Settings) -> bool:
    return all(
        [
            settings.deepseek_api_key.strip(),
            settings.deepseek_api_base.strip(),
            settings.deepseek_model.strip(),
        ]
    )
