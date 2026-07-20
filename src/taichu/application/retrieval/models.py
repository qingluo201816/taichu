"""统一知识召回的稳定输入、输出与技术观测模型。"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeType,
)
from taichu.domain.rules.fact_scope import (
    FactScopeSource,
    RetrievalScopeName,
)


class RetrievalModel(BaseModel):
    """不可变且拒绝额外字段的召回契约基类。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class RetrievalMode(StrEnum):
    """第一版统一召回支持的读取模式。"""

    RELEVANCE = "relevance"
    IDENTITY = "identity"
    CATALOG = "catalog"


class RetrievalStatus(StrEnum):
    """一次召回调用的技术状态。"""

    COMPLETED = "completed"
    EMPTY = "empty"
    FAILED = "failed"


class RetrievalBranchStatus(StrEnum):
    """单个策略分支的技术执行状态。"""

    COMPLETED = "completed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class RetrievalFallbackReasonCode(StrEnum):
    """可机读且不泄露查询内容的回退原因。"""

    STRATEGY_UNAVAILABLE = "strategy_unavailable"
    BACKEND_TIMEOUT = "backend_timeout"
    BACKEND_ERROR = "backend_error"


class RetrievalConsumerContext(RetrievalModel):
    """关联业务运行但不统一业务日志的最小上下文。"""

    consumer_type: str = Field(default="unspecified", min_length=1, max_length=64)
    run_id: str | None = Field(default=None, max_length=128)
    stage: str | None = Field(default=None, max_length=128)


class RetrievalIdentityQuery(RetrievalModel):
    """知识沉淀流程用于已有知识匹配的精确身份。"""

    knowledge_type: StructuredKnowledgeType
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list, max_length=50)


class RetrievalRequest(RetrievalModel):
    """所有消费者共用的只读知识召回请求。"""

    mode: RetrievalMode = RetrievalMode.RELEVANCE
    query_text: str = Field(default="", max_length=20_000)
    context_text: str = Field(default="", max_length=100_000)
    identity: RetrievalIdentityQuery | None = None
    scope: RetrievalScopeName = RetrievalScopeName.FACT
    source: FactScopeSource = FactScopeSource.CONFIRMED_KNOWLEDGE
    knowledge_types: frozenset[StructuredKnowledgeType] = Field(
        default_factory=frozenset
    )
    top_k: int | None = Field(default=None, ge=1, le=200)
    max_content_chars: int | None = Field(default=None, ge=500, le=50_000)
    requested_strategy: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{1,63}$",
    )
    consumer: RetrievalConsumerContext = Field(default_factory=RetrievalConsumerContext)

    @model_validator(mode="after")
    def validate_first_version_scope(self) -> RetrievalRequest:
        """锁定第一版事实范围并校验模式专属字段。"""
        if self.scope is not RetrievalScopeName.FACT:
            raise ValueError("第一版知识召回只支持事实范围。")
        if self.source is not FactScopeSource.CONFIRMED_KNOWLEDGE:
            raise ValueError("第一版知识召回只支持已确认知识库。")
        if self.mode is RetrievalMode.RELEVANCE:
            if not self.query_text.strip() and not self.context_text.strip():
                raise ValueError("相关性召回必须提供查询文本或辅助上下文。")
            if self.identity is not None:
                raise ValueError("相关性召回不能提供身份匹配参数。")
        elif self.mode is RetrievalMode.IDENTITY:
            if self.identity is None:
                raise ValueError("身份召回必须提供知识类型、名称和别名。")
        elif self.identity is not None:
            raise ValueError("有效知识快照不能提供身份匹配参数。")
        if (
            self.mode is not RetrievalMode.RELEVANCE
            and self.requested_strategy not in (None, "mongo_lexical")
        ):
            raise ValueError("身份和目录召回只能使用确定性词法策略。")
        return self


class RetrievalBackendCandidate(RetrievalModel):
    """召回后端交给统一服务的一条已排序候选。"""

    card: StructuredKnowledgeCard
    score: float = Field(ge=0)
    match_reasons: list[str] = Field(default_factory=list)
    estimated_content_chars: int = Field(default=0, ge=0)


class RetrievalBackendMetrics(RetrievalModel):
    """可选的后端细分耗时与 Embedding 用量，不保存输入或向量。"""

    embedding_call_id: str | None = Field(default=None, max_length=128)
    embedding_duration_ms: int | None = Field(default=None, ge=0)
    embedding_input_tokens: int | None = Field(default=None, ge=0)
    embedding_cost_amount: float = Field(default=0, ge=0)
    index_search_duration_ms: int | None = Field(default=None, ge=0)


class RetrievalBackendResult(RetrievalModel):
    """一个召回后端的候选结果。"""

    strategy: str = Field(min_length=1, max_length=64)
    candidate_count: int = Field(ge=0)
    candidates: list[RetrievalBackendCandidate] = Field(default_factory=list)
    index_snapshot_id: str | None = Field(default=None, max_length=128)
    metrics: RetrievalBackendMetrics = Field(default_factory=RetrievalBackendMetrics)


class RetrievalItem(RetrievalModel):
    """交给写作任务、Workflow 或 Tool 的标准知识条目。"""

    source_type: FactScopeSource = FactScopeSource.CONFIRMED_KNOWLEDGE
    source_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    rank: int = Field(ge=1)
    score: float = Field(ge=0)
    match_reasons: list[str] = Field(default_factory=list)
    estimated_content_chars: int = Field(default=0, ge=0)
    knowledge_card: StructuredKnowledgeCard


class RetrievalResult(RetrievalModel):
    """一次统一召回调用的完整结果。"""

    retrieval_id: str = Field(min_length=1)
    status: RetrievalStatus
    mode: RetrievalMode
    scope: RetrievalScopeName
    source: FactScopeSource
    strategy: str = Field(min_length=1)
    items: list[RetrievalItem] = Field(default_factory=list)
    candidate_count: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    truncated: bool = False
    empty_reason: str | None = None
    started_at: str = Field(min_length=1)
    finished_at: str = Field(min_length=1)
    duration_ms: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    policy_name: str = "legacy_default"
    requested_strategy: str | None = None
    effective_strategy: str | None = None
    fallback_used: bool = False
    fallback_reason_code: RetrievalFallbackReasonCode | None = None
    applied_top_k: int = Field(default=1, ge=1, le=200)
    applied_max_content_chars: int = Field(default=500, ge=500, le=50_000)
    content_chars_used: int = Field(default=0, ge=0)
    budget_limited: bool = False
    backend_duration_ms: int = Field(default=0, ge=0)
    post_filter_duration_ms: int = Field(default=0, ge=0)
    index_snapshot_id: str | None = Field(default=None, max_length=128)
    backend_metrics: RetrievalBackendMetrics = Field(
        default_factory=RetrievalBackendMetrics
    )
    strategy_snapshot: dict[str, str | int | bool | None] = Field(
        default_factory=dict
    )


class RetrievalTraceItem(RetrievalModel):
    """技术遥测中保存的轻量结果引用。"""

    source_id: str = Field(min_length=1)
    rank: int = Field(ge=1)
    score: float = Field(ge=0)
    match_reasons: list[str] = Field(default_factory=list)


class RetrievalTraceBranch(RetrievalModel):
    """一次请求内某个策略分支的脱敏观测。"""

    strategy: str = Field(min_length=1, max_length=64)
    status: RetrievalBranchStatus
    candidate_count: int = Field(default=0, ge=0)
    hit_count: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    reason_code: RetrievalFallbackReasonCode | None = None
    error_summary: str | None = Field(default=None, max_length=200)


class RetrievalTraceRecord(RetrievalModel):
    """不保存正文原文的召回技术遥测。"""

    lifecycle: Literal["confirmed"] = "confirmed"
    retrieval_id: str = Field(min_length=1)
    status: RetrievalStatus
    mode: RetrievalMode
    scope: RetrievalScopeName
    source: FactScopeSource
    strategy: str = Field(min_length=1)
    consumer: RetrievalConsumerContext
    query_sha256: str = Field(min_length=64, max_length=64)
    query_char_count: int = Field(ge=0)
    context_char_count: int = Field(ge=0)
    knowledge_types: list[StructuredKnowledgeType] = Field(default_factory=list)
    requested_top_k: int = Field(ge=1)
    requested_max_content_chars: int = Field(ge=500)
    candidate_count: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    truncated: bool = False
    items: list[RetrievalTraceItem] = Field(default_factory=list)
    started_at: str = Field(min_length=1)
    finished_at: str = Field(min_length=1)
    duration_ms: int = Field(ge=0)
    error_type: str | None = None
    error_message: str | None = None
    policy_name: str = "legacy_default"
    requested_strategy: str | None = None
    effective_strategy: str | None = None
    fallback_used: bool = False
    fallback_reason_code: RetrievalFallbackReasonCode | None = None
    backend_duration_ms: int = Field(default=0, ge=0)
    post_filter_duration_ms: int = Field(default=0, ge=0)
    strategy_snapshot: dict[str, str | int | bool | None] = Field(
        default_factory=dict
    )
    index_snapshot_id: str | None = Field(default=None, max_length=128)
    branches: list[RetrievalTraceBranch] = Field(default_factory=list)
    backend_metrics: RetrievalBackendMetrics = Field(
        default_factory=RetrievalBackendMetrics
    )
