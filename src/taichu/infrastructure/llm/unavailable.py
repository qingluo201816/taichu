"""Failure-only chat model used when no real LLM is configured."""

from typing import Any

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult

LLM_NOT_CONFIGURED_MESSAGE = "当前未配置可用模型，无法调用真实 LLM。"


class UnavailableLLMChatModel(BaseChatModel):
    """A chat model placeholder that never generates synthetic content."""

    @property
    def _llm_type(self) -> str:
        return "taichu-unavailable-llm"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise RuntimeError(LLM_NOT_CONFIGURED_MESSAGE)
