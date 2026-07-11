"""根据配置创建带真实身份的 LLM 运行时。"""

from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel

from taichu.application.contracts.llm import LLMModelIdentity
from taichu.config import Settings
from taichu.infrastructure.llm.providers.deepseek import (
    create_deepseek,
    deepseek_model_family,
    deepseek_model_identity,
)
from taichu.infrastructure.llm.unavailable import UnavailableLLMChatModel


@dataclass(frozen=True, slots=True)
class LLMRuntime:
    """Concrete chat model plus the identity used to create it."""

    chat_model: BaseChatModel
    model_identity: LLMModelIdentity
    configured: bool


def create_llm(settings: Settings) -> LLMRuntime:
    """创建配置指定的聊天模型及其可审计身份。"""
    if settings.llm_provider == "deepseek":
        model_id = settings.deepseek_model.strip()
        if not _deepseek_configured(settings):
            return LLMRuntime(
                chat_model=UnavailableLLMChatModel(),
                model_identity=LLMModelIdentity.unknown(
                    "当前未配置可用模型。",
                    provider="deepseek",
                    model_id=model_id,
                    family=deepseek_model_family(model_id),
                    endpoint_kind="openai_compatible",
                ),
                configured=False,
            )
        return LLMRuntime(
            chat_model=create_deepseek(settings, model=model_id),
            model_identity=deepseek_model_identity(model_id),
            configured=True,
        )
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


def _deepseek_configured(settings: Settings) -> bool:
    return all(
        [
            settings.deepseek_api_key.strip(),
            settings.deepseek_api_base.strip(),
            settings.deepseek_model.strip(),
        ]
    )
