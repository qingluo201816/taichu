"""仅用于测试注入的 LangChain 模型网关适配器。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from taichu.application.contracts.llm import (
    LLMCost,
    LLMGatewayContract,
    LLMModelIdentity,
    LLMModelProfile,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    LLMUsage,
)


class LangChainLLMAdapter(LLMGatewayContract):
    """让既有测试替身通过新契约注入；生产组合根不使用此适配器。"""

    def __init__(
        self,
        chat_model: BaseChatModel,
        model_identity: LLMModelIdentity,
        *,
        default_model_id: str = "deepseek-v4-pro",
    ) -> None:
        self._chat_model = chat_model
        self._model_identity = model_identity
        actual_id = model_identity.model_id or default_model_id
        self._profile = LLMModelProfile(
            id=actual_id,
            display_name=actual_id,
            provider="rightcode",
            upstream_model=actual_id,
            wire_protocol="openai_responses",
            base_url_key="RIGHTCODE_RESPONSES_BASE_URL",
            enabled=True,
            is_default=True,
            supports_streaming=True,
            upstream_verified=model_identity.known,
        )

    @property
    def model_identity(self) -> LLMModelIdentity:
        return self._model_identity

    def list_models(self) -> list[LLMModelProfile]:
        return [self._profile]

    async def complete(self, request: LLMRequest) -> LLMResponse:
        message = await self._chat_model.ainvoke(_messages(request))
        text = _stringify_content(message.content)
        return LLMResponse(
            text=text,
            model_id=self._profile.id,
            upstream_model=self._profile.upstream_model,
            usage=LLMUsage(),
            cost=LLMCost(),
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        yield LLMStreamEvent(event_type="started")
        response = await self.complete(request)
        if response.text:
            yield LLMStreamEvent(event_type="text_delta", delta=response.text)
        yield LLMStreamEvent(event_type="completed", response=response)


def _messages(request: LLMRequest) -> list[Any]:
    result: list[Any] = []
    for item in request.messages:
        if item.role == "system":
            result.append(SystemMessage(content=item.content))
        elif item.role == "assistant":
            result.append(AIMessage(content=item.content))
        else:
            result.append(HumanMessage(content=item.content))
    return result


def _stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if isinstance(value, str):
                    parts.append(value)
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content)
