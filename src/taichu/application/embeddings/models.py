"""真实 Embedding 调用的稳定契约与脱敏遥测模型。"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EmbeddingModel(BaseModel):
    """不可变且拒绝额外字段的 Embedding 契约基类。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class EmbeddingPurpose(StrEnum):
    """区分索引文档和查询，以便适配模型专属指令。"""

    KNOWLEDGE_DOCUMENT = "knowledge_document"
    KNOWLEDGE_QUERY = "knowledge_query"


class EmbeddingNormalization(StrEnum):
    """向量归一化方式。"""

    L2 = "l2"
    NONE = "none"


class EmbeddingRequest(EmbeddingModel):
    """一次不可变的批量 Embedding 请求。"""

    texts: list[str] = Field(min_length=1, max_length=128)
    purpose: EmbeddingPurpose
    model_role: str = Field(default="knowledge_embedding", min_length=1, max_length=64)
    input_char_budget: int = Field(ge=1, le=1_000_000)
    run_id: str | None = Field(default=None, max_length=128)
    invocation_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_texts_and_budget(self) -> Self:
        if any(not text.strip() for text in self.texts):
            raise ValueError("Embedding 输入不能包含空文本。")
        if sum(len(text) for text in self.texts) > self.input_char_budget:
            raise ValueError("Embedding 输入超过本次字符预算。")
        return self


class EmbeddingResponse(EmbeddingModel):
    """协议无关且已完成一致性校验的向量响应。"""

    call_id: str = Field(pattern=r"^embedding_[a-f0-9]{32}$")
    model_id: str = Field(min_length=1, max_length=200)
    dimensions: int = Field(ge=1, le=100_000)
    normalization: EmbeddingNormalization
    vectors: list[list[float]] = Field(min_length=1, max_length=128)
    input_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost_amount: float = Field(default=0, ge=0)
    cost_currency: str = Field(default="CNY", min_length=1, max_length=16)
    duration_ms: int = Field(ge=0)
    provider_request_id: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def validate_vectors(self) -> Self:
        for vector in self.vectors:
            if len(vector) != self.dimensions:
                raise ValueError("Embedding 响应向量维度不一致。")
            if any(not math.isfinite(value) for value in vector):
                raise ValueError("Embedding 响应包含 NaN 或 Infinity。")
        return self


class EmbeddingModelProfile(EmbeddingModel):
    """当前真实 Embedding 服务的可审计能力快照。"""

    model_id: str = Field(min_length=1, max_length=200)
    dimensions: int = Field(ge=1, le=100_000)
    max_input_tokens: int = Field(ge=1)
    supports_chinese: bool
    supports_multilingual: bool
    transport: Literal["openai_compatible_http"]
    normalization: EmbeddingNormalization


class EmbeddingCallRecord(EmbeddingModel):
    """不保存原文或向量的 Embedding 调用遥测。"""

    lifecycle: Literal["confirmed"] = "confirmed"
    call_id: str = Field(pattern=r"^embedding_[a-f0-9]{32}$")
    run_id: str | None = Field(default=None, max_length=128)
    invocation_id: str | None = Field(default=None, max_length=128)
    purpose: EmbeddingPurpose
    model_role: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=200)
    dimensions: int = Field(ge=1, le=100_000)
    normalization: EmbeddingNormalization
    text_count: int = Field(ge=1, le=128)
    input_char_count: int = Field(ge=0)
    input_sha256: str = Field(min_length=64, max_length=64)
    input_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost_amount: float = Field(default=0, ge=0)
    cost_currency: str = Field(default="CNY", min_length=1, max_length=16)
    status: Literal["completed", "failed"]
    started_at: str = Field(min_length=1)
    finished_at: str = Field(min_length=1)
    duration_ms: int = Field(ge=0)
    provider_request_id: str | None = Field(default=None, max_length=256)
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = Field(default=None, max_length=200)
