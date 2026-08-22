"""可用于运行回放与评测的 LLM 调用输入输出资产。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LLMReplayModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LLMReplayToolCall(LLMReplayModel):
    call_id: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=128)
    arguments_json: str = Field(max_length=1_000_000)


class LLMReplayToolDefinition(LLMReplayModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(max_length=20_000)
    parameters: dict[str, Any]
    strict: bool = True


class LLMReplayMessage(LLMReplayModel):
    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: str = Field(max_length=1_000_000)
    tool_calls: list[LLMReplayToolCall] = Field(default_factory=list, max_length=100)
    tool_call_id: str | None = Field(default=None, max_length=256)
    tool_name: str | None = Field(default=None, max_length=128)
    is_error: bool = False


class LLMCallReplayRecord(LLMReplayModel):
    """保存脱敏后的实际模型消息与规范化响应，不保存传输鉴权数据。"""

    call_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    context_snapshot_id: str | None = Field(default=None, max_length=128)
    task_type: str = Field(min_length=1, max_length=128)
    task_name: str = Field(min_length=1, max_length=256)
    feature: str = Field(default="", max_length=128)
    model_id: str = Field(min_length=1, max_length=128)
    provider: str = Field(default="rightcode", min_length=1, max_length=128)
    fallback_from_provider: str | None = Field(default=None, max_length=128)
    upstream_model: str = Field(min_length=1, max_length=256)
    wire_protocol: str = Field(min_length=1, max_length=64)
    status: Literal["completed", "failed"]
    response_mode: Literal["text", "json"]
    temperature: float | None = None
    max_output_tokens: int | None = Field(default=None, ge=1)
    wire_request_body: dict[str, Any] | None = None
    messages: list[LLMReplayMessage] = Field(min_length=1, max_length=200)
    tools: list[LLMReplayToolDefinition] = Field(default_factory=list, max_length=100)
    tool_choice: Literal["auto", "none", "required"] = "auto"
    response_tool_calls: list[LLMReplayToolCall] = Field(
        default_factory=list,
        max_length=100,
    )
    response_text: str = Field(default="", max_length=1_000_000)
    request_sha256: str = Field(min_length=64, max_length=64)
    response_sha256: str = Field(min_length=64, max_length=64)
    redaction_count: int = Field(default=0, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    finish_reason: str | None = Field(default=None, max_length=128)
    provider_request_id: str | None = Field(default=None, max_length=256)
    started_at: str = Field(min_length=1, max_length=64)
    finished_at: str = Field(min_length=1, max_length=64)
    duration_ms: int = Field(ge=0)
    error_code: str | None = Field(default=None, max_length=128)
    error_message: str | None = Field(default=None, max_length=2_000)
