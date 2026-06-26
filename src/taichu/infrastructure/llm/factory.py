"""根据配置创建 LLM 实例。"""

from langchain_core.language_models.chat_models import BaseChatModel

from taichu.config import Settings
from taichu.infrastructure.llm.providers.deepseek import create_deepseek


def create_llm(settings: Settings) -> BaseChatModel:
    """创建配置指定的聊天模型。"""
    if settings.llm_provider == "deepseek":
        return create_deepseek(settings)
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")
