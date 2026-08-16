"""技术无关的 LLM 请求、响应与网关契约。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, Protocol, Self, runtime_checkable

from pydantic import BaseModel, ConfigDict, model_validator


LLMRole = Literal["system", "developer", "user", "assistant", "tool"]
LLMResponseMode = Literal["text", "json"]
LLMWireProtocol = Literal["openai_responses", "anthropic_messages"]
LLMToolChoice = Literal["auto", "none", "required"]
LLMCostKind = Literal["actual", "estimated", "unavailable"]
LLMStreamEventType = Literal[
    "started", "text_delta", "usage", "completed", "failed"
]


@dataclass(frozen=True, slots=True)
class LLMToolDefinition:
    """一个由应用注册并通过模型 API 暴露的函数工具。"""

    name: str
    description: str
    parameters: dict[str, Any]
    strict: bool = True


@dataclass(frozen=True, slots=True)
class LLMToolCall:
    """模型发起的一次函数工具调用。"""

    call_id: str
    name: str
    arguments_json: str


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """一条保留角色边界的应用层消息。"""

    role: LLMRole
    content: str = ""
    tool_calls: tuple[LLMToolCall, ...] = ()
    tool_call_id: str | None = None
    tool_name: str | None = None
    is_error: bool = False

    def __post_init__(self) -> None:
        if self.role == "assistant" and self.tool_call_id is not None:
            raise ValueError("assistant 消息不能声明工具结果关联标识。")
        if self.role != "assistant" and self.tool_calls:
            raise ValueError("只有 assistant 消息可以包含工具调用请求。")
        if self.role == "tool":
            if not (self.tool_call_id or "").strip():
                raise ValueError("tool 消息必须声明工具调用关联标识。")
        elif self.tool_call_id is not None or self.tool_name is not None or self.is_error:
            raise ValueError("只有 tool 消息可以声明工具结果元数据。")


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """一次不可变的模型调用快照。"""

    model_id: str
    messages: tuple[LLMMessage, ...]
    task_type: str
    task_name: str
    run_id: str | None = None
    context_snapshot_id: str | None = None
    chapter_ids: tuple[str, ...] = ()
    response_mode: LLMResponseMode = "text"
    temperature: float | None = None
    max_output_tokens: int | None = None
    feature: str = ""
    tools: tuple[LLMToolDefinition, ...] = ()
    tool_choice: LLMToolChoice = "auto"

    def __str__(self) -> str:
        """提供便于测试和审计的文本视图，传输层仍保留消息角色。"""
        parts: list[str] = []
        for message in self.messages:
            parts.append(message.content)
            parts.extend(call.arguments_json for call in message.tool_calls)
        return "\n\n".join(parts)

    def __contains__(self, value: str) -> bool:
        """让旧测试替身可以继续按提示词片段选择固定响应。"""
        return value in str(self)


@dataclass(frozen=True, slots=True)
class LLMUsage:
    """上游返回的可空 Token 明细。"""

    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class LLMCost:
    """实际、预估或不可计算的费用。"""

    amount: Decimal | None = None
    currency: str = "CNY"
    kind: LLMCostKind = "unavailable"


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """协议无关的完整模型响应。"""

    text: str
    model_id: str
    upstream_model: str
    usage: LLMUsage
    cost: LLMCost
    finish_reason: str | None = None
    provider_request_id: str | None = None
    call_id: str | None = None
    tool_calls: tuple[LLMToolCall, ...] = ()


@dataclass(frozen=True, slots=True)
class LLMStreamEvent:
    """流式调用的规范化事件。"""

    event_type: LLMStreamEventType
    delta: str = ""
    usage: LLMUsage | None = None
    response: LLMResponse | None = None
    error: str | None = None
    call_id: str | None = None


@dataclass(frozen=True, slots=True)
class LLMModelProfile:
    """后端模型目录中的稳定模型配置。"""

    id: str
    display_name: str
    provider: Literal["rightcode", "deepseek_official"]
    upstream_model: str
    wire_protocol: LLMWireProtocol
    base_url_key: str
    enabled: bool
    is_default: bool
    supports_streaming: bool
    input_price_per_million: Decimal | None = None
    cached_input_price_per_million: Decimal | None = None
    output_price_per_million: Decimal | None = None
    reasoning_output_price_per_million: Decimal | None = None
    currency: str = "CNY"
    upstream_verified: bool = False


class LLMModelIdentity(BaseModel):
    """供既有运行评估记录使用的可审计模型身份。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = ""
    model_id: str = ""
    family: str = ""
    endpoint_kind: str = ""
    fingerprint: str | None = None
    known: bool = False
    unknown_reason: str | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if self.known:
            if not self.provider.strip() or not self.model_id.strip():
                raise ValueError("已知模型身份必须包含供应商和模型标识。")
            if self.unknown_reason is not None:
                raise ValueError("已知模型身份不能包含未知原因。")
        elif not (self.unknown_reason or "").strip():
            raise ValueError("未知模型身份必须说明原因。")
        return self

    @classmethod
    def unknown(
        cls,
        reason: str,
        *,
        provider: str = "",
        model_id: str = "",
        family: str = "",
        endpoint_kind: str = "",
    ) -> LLMModelIdentity:
        return cls(
            provider=provider,
            model_id=model_id,
            family=family,
            endpoint_kind=endpoint_kind,
            known=False,
            unknown_reason=reason,
        )


@runtime_checkable
class LLMGatewayContract(Protocol):
    """应用层唯一允许依赖的模型网关。"""

    async def complete(self, request: LLMRequest) -> LLMResponse:
        ...

    def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        ...

    def list_models(self) -> list[LLMModelProfile]:
        ...


def response_text(response: LLMResponse | str) -> str:
    """读取响应正文，并兼容仅存在于测试替身中的字符串返回值。"""
    return response.text if isinstance(response, LLMResponse) else response
