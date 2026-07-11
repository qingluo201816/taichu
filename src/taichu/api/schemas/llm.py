"""模型目录、检测与调用遥测 API 模型。"""

from decimal import Decimal

from pydantic import BaseModel, Field

from taichu.application.models.llm_usage import (
    LLMCallRecord,
    LLMUsageGroup,
    LLMTokenTrendPoint,
)


class PublicLLMModel(BaseModel):
    id: str
    display_name: str
    enabled: bool
    is_default: bool
    supports_streaming: bool
    availability: str = "unknown"
    last_probed_at: str | None = None
    availability_error: str | None = None
    upstream_verified: bool = False


class LLMModelListResponse(BaseModel):
    default_model_id: str
    models: list[PublicLLMModel] = Field(default_factory=list)


class LLMModelProbeResponse(BaseModel):
    model_id: str
    availability: str
    last_probed_at: str | None = None
    message: str


class LLMCallListResponse(BaseModel):
    items: list[LLMCallRecord] = Field(default_factory=list)
    page: int
    page_size: int
    total: int


class LLMUsageSummaryResponse(BaseModel):
    total_calls: int
    completed_calls: int
    failed_calls: int
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    total_tokens: int | None
    actual_cost: Decimal
    estimated_cost: Decimal
    unavailable_cost_calls: int
    average_duration_ms: int
    by_model: list[LLMUsageGroup]
    by_task_type: list[LLMUsageGroup]


class LLMTokenTrendResponse(BaseModel):
    bucket: str
    points: list[LLMTokenTrendPoint] = Field(default_factory=list)
