"""Graph RAG Golden 数据与评测结果模型。"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class RAGEvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RAGGoldenCategory(StrEnum):
    SINGLE_FACT = "single_fact"
    CROSS_SOURCE = "cross_source"
    GRAPH_MULTI_HOP = "graph_multi_hop"
    HARD_NEGATIVE = "hard_negative"


def normalize_relation_text(value: str) -> str:
    """把图索引展示文本归一化为可跨重建比较的关系身份输入。"""

    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"\s+", " ", normalized)


def stable_relation_id(value: str) -> str:
    normalized = normalize_relation_text(value)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return f"relation-{digest}"


class RAGExpectedRelation(RAGEvaluationModel):
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str = Field(min_length=1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def relation_id(self) -> str:
        return stable_relation_id(self.text)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def text(self) -> str:
        return normalize_relation_text(
            f"{self.subject} {self.predicate} {self.object}"
        )


class RAGGoldenCase(RAGEvaluationModel):
    case_id: str = Field(pattern=r"^(single|cross|graph|negative)-\d{3}$")
    query: str = Field(min_length=1)
    category: RAGGoldenCategory
    graph_required: bool = False
    smoke: bool = False
    expected_source_ids: list[str] = Field(default_factory=list)
    expected_relations: list[RAGExpectedRelation] = Field(default_factory=list)
    expected_path: list[str] = Field(default_factory=list)
    expected_claims: list[str] = Field(min_length=1)
    reference_answer: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_graph_expectations(self) -> RAGGoldenCase:
        relation_ids = {item.relation_id for item in self.expected_relations}
        if self.graph_required:
            if self.category is not RAGGoldenCategory.GRAPH_MULTI_HOP:
                raise ValueError("graph_required 仅适用于 graph_multi_hop 用例。")
            if not self.expected_relations or not self.expected_path:
                raise ValueError("Graph 用例必须声明预期关系和完整路径。")
            if not set(self.expected_path).issubset(relation_ids):
                raise ValueError("完整路径只能引用本用例的预期关系标识。")
        return self


class RAGGoldenSuite(RAGEvaluationModel):
    suite_id: str = Field(min_length=1)
    cases: list[RAGGoldenCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_case_ids(self) -> RAGGoldenSuite:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Golden 集中的 case_id 必须唯一。")
        return self


class RAGCaseScore(RAGEvaluationModel):
    case_id: str
    recall_at_k: float | None = Field(default=None, ge=0, le=1)
    mrr_at_k: float | None = Field(default=None, ge=0, le=1)
    authority_verified: bool
    relation_recall_at_k: float | None = Field(default=None, ge=0, le=1)
    complete_path_recall: float | None = Field(default=None, ge=0, le=1)
    graph_expansion_noise_rate: float | None = Field(default=None, ge=0, le=1)
    retrieved_source_ids: list[str] = Field(default_factory=list)
    retrieved_relation_ids: list[str] = Field(default_factory=list)


class RAGAblationScore(RAGEvaluationModel):
    case_id: str
    graph_on: RAGCaseScore
    graph_off: RAGCaseScore
    recall_delta: float | None
    mrr_delta: float | None
    relation_recall_delta: float
    complete_path_delta: float


class RAGEvaluationSummary(RAGEvaluationModel):
    case_count: int = Field(ge=0)
    graph_case_count: int = Field(ge=0)
    mean_recall_at_k: float = Field(ge=0, le=1)
    mean_mrr_at_k: float = Field(ge=0, le=1)
    authority_pass_rate: float = Field(ge=0, le=1)
    mean_relation_recall_at_k: float | None = Field(default=None, ge=0, le=1)
    complete_path_pass_rate: float | None = Field(default=None, ge=0, le=1)
    mean_ablation_recall_delta: float | None = None
    mean_ablation_complete_path_delta: float | None = None


class RAGEvaluationReport(RAGEvaluationModel):
    suite_id: str
    mode: str
    created_at: str
    top_k: int = Field(ge=1)
    case_scores: list[RAGCaseScore]
    ablation_scores: list[RAGAblationScore]
    summary: RAGEvaluationSummary


class RAGGateResult(RAGEvaluationModel):
    passed: bool
    failures: list[str] = Field(default_factory=list)


class RAGRunReport(RAGEvaluationModel):
    deterministic: RAGEvaluationReport
    semantic_scores: list[dict[str, object]] = Field(default_factory=list)
    runtime_identity: dict[str, str] = Field(default_factory=dict)
    gate: RAGGateResult


class RAGInfrastructureFailureReport(RAGEvaluationModel):
    status: str = "infrastructure_failed"
    mode: str
    created_at: str
    error_type: str
    error_message: str


class RAGEvaluationResultSummary(RAGEvaluationModel):
    run_id: str
    mode: str
    created_at: str
    status: str
    passed: bool | None = None
    case_count: int | None = Field(default=None, ge=0)
    graph_case_count: int | None = Field(default=None, ge=0)
    error_message: str | None = None


class RAGEvaluationPipelineStage(RAGEvaluationModel):
    key: str
    order: int = Field(ge=1)
    name: str
    description: str


class RAGEvaluationParameter(RAGEvaluationModel):
    key: str
    name: str
    value: str
    description: str


class RAGEvaluationCIPolicy(RAGEvaluationModel):
    name: str
    trigger: str
    scope: str


class RAGEvaluationConfiguration(RAGEvaluationModel):
    pipeline: list[RAGEvaluationPipelineStage]
    parameters: list[RAGEvaluationParameter]
    ci_policies: list[RAGEvaluationCIPolicy]
