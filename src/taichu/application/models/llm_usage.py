"""LLM 运行遥测模型。"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


LLMCallStatus = Literal["running", "completed", "failed"]
LLMCallCostKind = Literal["actual", "estimated", "unavailable"]


class LLMCallRecord(BaseModel):
    """一次真实或探测调用的完整、脱敏记录。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    call_id: str = Field(min_length=1)
    run_id: str | None = None
    task_type: str = Field(min_length=1)
    task_name: str = Field(min_length=1)
    feature: str = ""
    chapter_ids: list[str] = Field(default_factory=list)
    model_id: str = Field(min_length=1)
    model_display_name: str = Field(min_length=1)
    provider: str = "rightcode"
    fallback_from_provider: str | None = None
    upstream_model: str = Field(min_length=1)
    wire_protocol: str = Field(min_length=1)
    status: LLMCallStatus
    started_at: str = Field(min_length=1)
    finished_at: str | None = None
    duration_ms: int = 0
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    cost_amount: Decimal | None = None
    cost_currency: str = "CNY"
    cost_kind: LLMCallCostKind = "unavailable"
    provider_request_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class LLMUsageQuery(BaseModel):
    """调用明细分页和筛选条件。"""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
    started_from: str | None = None
    started_to: str | None = None
    model_id: str | None = None
    task_type: str | None = None
    status: LLMCallStatus | None = None


class LLMUsagePage(BaseModel):
    """调用明细分页结果。"""

    items: list[LLMCallRecord] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0


class LLMUsageGroup(BaseModel):
    """按模型或任务类型聚合的统计行。"""

    key: str
    display_name: str
    total_calls: int = 0
    completed_calls: int = 0
    failed_calls: int = 0
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    actual_cost: Decimal = Decimal("0")
    estimated_cost: Decimal = Decimal("0")
    unavailable_cost_calls: int = 0
    average_duration_ms: int = 0


class LLMUsageSummary(BaseModel):
    """模型监控页面使用的汇总统计。"""

    total_calls: int = 0
    completed_calls: int = 0
    failed_calls: int = 0
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    actual_cost: Decimal = Decimal("0")
    estimated_cost: Decimal = Decimal("0")
    unavailable_cost_calls: int = 0
    average_duration_ms: int = 0
    by_model: list[LLMUsageGroup] = Field(default_factory=list)
    by_task_type: list[LLMUsageGroup] = Field(default_factory=list)


class LLMTokenTrendPoint(BaseModel):
    """一个小时或一天内的 Token 使用聚合点。"""

    bucket_start: str
    call_count: int = 0
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
