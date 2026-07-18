"""召回评测数据集、逐例指标和结果模型。"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from taichu.domain.models.structured_knowledge import StructuredKnowledgeType


class RetrievalEvaluationModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RetrievalEvaluationCategory(StrEnum):
    EXACT_NAME_ALIAS = "exact_name_alias"
    SEMANTIC_PARAPHRASE = "semantic_paraphrase"
    STATE_RELATION_EVENT_RULE = "state_relation_event_rule"
    MULTI_ENTITY_DISAMBIGUATION = "multi_entity_disambiguation"
    NO_ANSWER_ADVERSARIAL = "no_answer_adversarial"


_CATEGORY_MINIMUMS = {
    RetrievalEvaluationCategory.EXACT_NAME_ALIAS: 15,
    RetrievalEvaluationCategory.SEMANTIC_PARAPHRASE: 20,
    RetrievalEvaluationCategory.STATE_RELATION_EVENT_RULE: 15,
    RetrievalEvaluationCategory.MULTI_ENTITY_DISAMBIGUATION: 5,
    RetrievalEvaluationCategory.NO_ANSWER_ADVERSARIAL: 5,
}


class RetrievalEvaluationCase(RetrievalEvaluationModel):
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    label: str = Field(min_length=1, max_length=200)
    category: RetrievalEvaluationCategory
    query_text: str = Field(min_length=1, max_length=20_000)
    context_text: str = Field(default="", max_length=100_000)
    knowledge_types: frozenset[StructuredKnowledgeType] = Field(
        default_factory=frozenset
    )
    relevant_card_ids: list[str] = Field(default_factory=list, max_length=50)
    must_not_return_card_ids: list[str] = Field(default_factory=list, max_length=50)
    should_be_empty: bool = False
    expected_top_k: Literal[1, 3, 5, 10] = 10

    @model_validator(mode="after")
    def validate_expectations(self) -> RetrievalEvaluationCase:
        relevant = set(self.relevant_card_ids)
        forbidden = set(self.must_not_return_card_ids)
        if len(relevant) != len(self.relevant_card_ids):
            raise ValueError("相关知识卡标识不能重复。")
        if len(forbidden) != len(self.must_not_return_card_ids):
            raise ValueError("禁止返回知识卡标识不能重复。")
        if relevant & forbidden:
            raise ValueError("相关知识卡与禁止返回知识卡不能重叠。")
        if self.should_be_empty and relevant:
            raise ValueError("空结果样例不能声明相关知识卡。")
        if not self.should_be_empty and not relevant:
            raise ValueError("非空样例必须声明至少一张相关知识卡。")
        return self


class RetrievalEvaluationDataset(RetrievalEvaluationModel):
    dataset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    evaluation_type: Literal["retrieval"] = "retrieval"
    label: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10_000)
    lifecycle: Literal["confirmed"] = "confirmed"
    updated_at: str = Field(min_length=1)
    cases: list[RetrievalEvaluationCase] = Field(min_length=60, max_length=500)
    checksum: str = Field(default="", max_length=64)

    @model_validator(mode="after")
    def validate_dataset_shape(self) -> RetrievalEvaluationDataset:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("召回评测样例标识必须唯一。")
        for category, minimum in _CATEGORY_MINIMUMS.items():
            actual = sum(case.category is category for case in self.cases)
            if actual < minimum:
                raise ValueError(
                    f"召回评测类别“{category.value}”至少需要 {minimum} 个样例。"
                )
        return self


class RetrievalAtKMetric(RetrievalEvaluationModel):
    k: Literal[1, 3, 5, 10]
    recall: float = Field(ge=0, le=1)
    precision: float = Field(ge=0, le=1)
    ndcg: float = Field(ge=0, le=1)


class RetrievalEvaluationCaseResult(RetrievalEvaluationModel):
    case_id: str
    category: RetrievalEvaluationCategory
    retrieval_id: str
    returned_card_ids: list[str] = Field(default_factory=list)
    forbidden_hit_ids: list[str] = Field(default_factory=list)
    at_k: list[RetrievalAtKMetric] = Field(min_length=4, max_length=4)
    reciprocal_rank: float = Field(ge=0, le=1)
    empty_result_correct: bool | None = None
    latency_ms: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    truncated: bool = False
    budget_limited: bool = False
    content_chars_used: int = Field(ge=0)


class RetrievalEvaluationSummary(RetrievalEvaluationModel):
    case_count: int = Field(ge=1)
    relevance_case_count: int = Field(ge=0)
    at_k: list[RetrievalAtKMetric] = Field(min_length=4, max_length=4)
    mrr: float = Field(ge=0, le=1)
    empty_result_accuracy: float = Field(ge=0, le=1)
    forbidden_hit_rate: float = Field(ge=0, le=1)
    average_latency_ms: float = Field(ge=0)
    p95_latency_ms: float = Field(ge=0)
    average_candidate_count: float = Field(ge=0)
    truncation_rate: float = Field(ge=0, le=1)
    content_budget_hit_rate: float = Field(ge=0, le=1)


class RetrievalEvaluationGroupResult(RetrievalEvaluationModel):
    category: RetrievalEvaluationCategory
    summary: RetrievalEvaluationSummary


class RetrievalEvaluationFailure(RetrievalEvaluationModel):
    case_id: str
    reasons: list[str] = Field(min_length=1)
    returned_card_ids: list[str] = Field(default_factory=list)


class RetrievalEvaluationRecord(RetrievalEvaluationModel):
    evaluation_id: str = Field(
        pattern=r"^retrieval_eval_\d{8}_\d{6}_[a-z0-9]{6}$"
    )
    lifecycle: Literal["confirmed"] = "confirmed"
    status: Literal["completed"] = "completed"
    dataset_id: str
    dataset_checksum: str = Field(min_length=64, max_length=64)
    requested_strategy: str
    effective_strategies: list[str] = Field(min_length=1)
    index_snapshot_id: str = Field(min_length=1, max_length=128)
    confirmed_card_count: int = Field(ge=0)
    policy_snapshots: list[dict[str, str | int | bool | None]] = Field(
        min_length=1
    )
    summary: RetrievalEvaluationSummary
    groups: list[RetrievalEvaluationGroupResult] = Field(min_length=5, max_length=5)
    cases: list[RetrievalEvaluationCaseResult] = Field(min_length=60)
    failures: list[RetrievalEvaluationFailure] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    started_at: str = Field(min_length=1)
    finished_at: str = Field(min_length=1)
