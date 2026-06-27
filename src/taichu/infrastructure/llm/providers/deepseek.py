"""DeepSeek LLM 供应商实现。"""

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from taichu.config import Settings


def create_deepseek(settings: Settings) -> ChatOpenAI:
    """根据配置创建 DeepSeek 聊天模型。"""
    return ChatOpenAI(
        api_key=(
            SecretStr(settings.deepseek_api_key)
            if settings.deepseek_api_key
            else None
        ),
        base_url=settings.deepseek_api_base,
        model=settings.deepseek_model,
    )
