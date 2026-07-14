"""Tool 与专业子 Agent 共用的最小技术调用模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Generic, Literal, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class InvocationModel(BaseModel):
    """不可变且拒绝额外字段的调用模型基类。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class InvocationStatus(StrEnum):
    """一次能力调用的技术状态。"""

    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class InvocationBudget(InvocationModel):
    """由上层调用方传入的有限资源预算。"""

    max_input_chars: int = Field(default=120_000, ge=1, le=500_000)
    max_output_chars: int = Field(default=30_000, ge=1, le=200_000)
    max_tool_calls: int = Field(default=12, ge=0, le=100)
    max_retries: int = Field(default=1, ge=0, le=5)
    max_output_tokens: int = Field(default=8_000, ge=128, le=100_000)


class InvocationContext(InvocationModel):
    """关联调用树、权限和业务范围，但不替代业务运行状态。"""

    task_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    call_id: str = Field(
        default_factory=lambda: f"call_{uuid4().hex}",
        min_length=1,
        max_length=128,
    )
    parent_call_id: str | None = Field(default=None, max_length=128)
    caller_type: Literal["application", "orchestrator", "subagent", "test"]
    caller_name: str = Field(min_length=1, max_length=128)
    phase: str = Field(default="execution", min_length=1, max_length=128)
    user_goal: str = Field(default="", max_length=20_000)
    author_constraints: list[str] = Field(default_factory=list, max_length=100)
    scope: dict[str, object] = Field(default_factory=dict)
    external_access_grant_id: str | None = Field(default=None, max_length=128)
    deadline_at: str | None = Field(default=None, max_length=64)
    budget: InvocationBudget = Field(default_factory=InvocationBudget)

    def child(
        self,
        *,
        caller_type: Literal["application", "orchestrator", "subagent", "test"],
        caller_name: str,
        phase: str | None = None,
    ) -> InvocationContext:
        """创建具有新调用 ID 的子调用上下文。"""
        return self.model_copy(
            update={
                "call_id": f"call_{uuid4().hex}",
                "parent_call_id": self.call_id,
                "caller_type": caller_type,
                "caller_name": caller_name,
                "phase": phase or self.phase,
            }
        )


OutputT = TypeVar("OutputT", bound=BaseModel)


class InvocationEnvelope(InvocationModel, Generic[OutputT]):
    """统一技术结果信封，领域输出仍保留具体 Schema。"""

    invocation_id: str = Field(min_length=1)
    capability_type: Literal["tool", "subagent"]
    capability_name: str = Field(min_length=1)
    status: InvocationStatus
    output: OutputT
    source_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trace_id: str = Field(min_length=1)
    started_at: str = Field(min_length=1)
    finished_at: str = Field(min_length=1)
    duration_ms: int = Field(ge=0)


class InvocationTraceRecord(InvocationModel):
    """不保存完整输入输出的分层技术调用记录。"""

    lifecycle: Literal["confirmed"] = "confirmed"
    trace_id: str = Field(min_length=1)
    capability_type: Literal["tool", "subagent", "llm"]
    capability_name: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    call_id: str = Field(min_length=1)
    parent_call_id: str | None = None
    caller_type: str = Field(min_length=1)
    caller_name: str = Field(min_length=1)
    status: InvocationStatus
    input_sha256: str = Field(min_length=64, max_length=64)
    input_char_count: int = Field(ge=0)
    output_char_count: int = Field(default=0, ge=0)
    source_count: int = Field(default=0, ge=0)
    side_effect: str = "none"
    authorization_reference: str | None = None
    model_role: str | None = None
    model_id: str | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    retry_count: int = Field(default=0, ge=0)
    started_at: str = Field(min_length=1)
    finished_at: str = Field(min_length=1)
    duration_ms: int = Field(ge=0)
    error_type: str | None = None
    error_message: str | None = None


def now_iso() -> str:
    """返回统一 UTC 时间文本。"""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
