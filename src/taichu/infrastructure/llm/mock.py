"""Local mock chat model used by the MVP instead of a real LLM."""

from typing import Any

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class MVPNoRealLLMChatModel(BaseChatModel):
    """A deterministic chat model that never calls an external service."""

    response_text: str = (
        '{"card_type":"suggestion","content":{"body":"这是本地模拟输出，仅用于检查链路。"}}'
    )

    @property
    def _llm_type(self) -> str:
        return "taichu-mvp-mock"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=self.response_text))]
        )
