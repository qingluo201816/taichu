"""DeepSeek LLM 供应商实现。"""

import re

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from taichu.application.contracts.llm import LLMModelIdentity
from taichu.config import Settings


def create_deepseek(
    settings: Settings,
    *,
    model: str | None = None,
) -> ChatOpenAI:
    """根据配置创建 DeepSeek 聊天模型。"""
    actual_model = settings.deepseek_model.strip() if model is None else model
    return ChatOpenAI(
        api_key=(
            SecretStr(settings.deepseek_api_key)
            if settings.deepseek_api_key
            else None
        ),
        base_url=settings.deepseek_api_base,
        model=actual_model,
        temperature=0,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def deepseek_model_identity(model_id: str) -> LLMModelIdentity:
    """Describe the exact DeepSeek model parameter used by ChatOpenAI."""
    return LLMModelIdentity(
        provider="deepseek",
        model_id=model_id,
        family=deepseek_model_family(model_id),
        endpoint_kind="openai_compatible",
        known=True,
    )


def deepseek_model_family(model_id: str) -> str:
    """Return a conservative family label without changing the exact model ID."""
    match = re.match(
        r"^(deepseek-(?:v\d+(?:\.\d+)?|r\d+))",
        model_id,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else model_id
