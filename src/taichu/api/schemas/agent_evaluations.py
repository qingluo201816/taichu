"""HTTP contracts for knowledge-extraction effect evaluation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from taichu.application.contracts.llm import LLMModelIdentity
from taichu.application.evaluations.knowledge_extraction.dataset import (
    DatasetValidationResult,
    EvaluationDatasetSummary,
)
from taichu.application.evaluations.knowledge_extraction.models import (
    EvaluationLifecycle,
)
from taichu.application.evaluations.knowledge_extraction.records import (
    EvaluationMode,
    EvaluationNotice,
    EvaluationPhase,
    EvaluationProgress,
    EvaluationRunResult,
    EvaluationStatus,
    IndependenceLevel,
    JudgeCallRecord,
    JudgeSummary,
)


class EvaluationApiModel(BaseModel):
    """Strict base model for public evaluation API payloads."""

    model_config = ConfigDict(extra="forbid")


class CreateKnowledgeEvaluationRequest(EvaluationApiModel):
    """Shared request for previewing or creating one evaluation."""

    dataset_id: str = Field(min_length=1)
    run_ids: list[str] = Field(min_length=1, max_length=1)
    judge_enabled: bool = True
    metric_profile_id: str = "knowledge_extraction_balanced"


class EvaluationDatasetListResponse(EvaluationApiModel):
    datasets: list[EvaluationDatasetSummary] = Field(default_factory=list)


class EvaluationDatasetDetailResponse(EvaluationApiModel):
    dataset: EvaluationDatasetSummary


class EvaluationDatasetValidationResponse(EvaluationApiModel):
    validation: DatasetValidationResult


class LatestEvaluationSummary(EvaluationApiModel):
    evaluation_id: str
    status: EvaluationStatus
    lifecycle: EvaluationLifecycle
    overall_quality_score: float | None = Field(default=None, ge=0, le=1)
    final_quality_state: str | None = None


class EligibleEvaluationRun(EvaluationApiModel):
    run_id: str
    case_id: str | None = None
    display_title: str
    model_display_name: str
    status: str
    scope_type: str
    chapter_id: str | None = None
    chapter_title: str | None = None
    chapter_ids: list[str] = Field(default_factory=list)
    chapter_titles: list[str] = Field(default_factory=list)
    total_chapter_count: int = Field(default=0, ge=0)
    started_at: str
    requested_model_name: str | None = None
    model_name: str | None = None
    generation_model_identity: LLMModelIdentity
    prompt_version: str
    schema_version: str
    eligibility_level: str
    reason: str | None = None
    suggested_card_available: bool
    latest_evaluation: LatestEvaluationSummary | None = None


class EligibleEvaluationRunListResponse(EvaluationApiModel):
    runs: list[EligibleEvaluationRun] = Field(default_factory=list)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)


class EvaluationDatasetReference(EvaluationApiModel):
    dataset_id: str
    checksum: str


class EvaluationPreviewRun(EvaluationApiModel):
    run_id: str
    case_id: str | None = None
    display_title: str
    model_display_name: str
    eligibility_level: str
    reason: str | None = None
    generation_model_identity: LLMModelIdentity
    independence_level: IndependenceLevel | None = None
    expected_card_count: int = Field(ge=0)
    estimated_matched_card_count: int = Field(ge=0)
    estimated_judge_card_count: int = Field(ge=0)


class EvaluationPreviewJudge(EvaluationApiModel):
    requested: bool
    available: bool | None = None
    model_identity: LLMModelIdentity | None = None
    unavailable_reason: str | None = None


class EvaluationPreviewEstimate(EvaluationApiModel):
    run_count: int = Field(ge=0)
    expected_card_count: int = Field(ge=0)
    matched_card_count: int = Field(ge=0)
    judge_card_count: int = Field(ge=0)
    judge_batch_count: int = Field(ge=0)


class KnowledgeEvaluationPreviewResponse(EvaluationApiModel):
    can_create: bool
    evaluation_mode: EvaluationMode
    has_diagnostic_runs: bool
    dataset: EvaluationDatasetReference
    runs: list[EvaluationPreviewRun] = Field(default_factory=list)
    judge: EvaluationPreviewJudge
    estimate: EvaluationPreviewEstimate
    warnings: list[str] = Field(default_factory=list)
    blocking_errors: list[str] = Field(default_factory=list)


class EvaluationRecordDataset(EvaluationApiModel):
    dataset_id: str
    display_name: str
    checksum: str


class KnowledgeEvaluationResponse(EvaluationApiModel):
    """Public report summary; deliberately excludes the execution token."""

    evaluation_id: str
    parent_evaluation_id: str | None = None
    request_fingerprint: str
    snapshot_root_hash: str
    evaluation_mode: EvaluationMode
    lifecycle: EvaluationLifecycle
    status: EvaluationStatus
    phase: EvaluationPhase
    dataset: EvaluationRecordDataset
    metric_profile_id: str
    subject_title: str
    judge: JudgeSummary
    progress: EvaluationProgress
    run_ids: list[str] = Field(default_factory=list)
    run_results: list[EvaluationRunResult] = Field(default_factory=list)
    aggregate_metrics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[EvaluationNotice] = Field(default_factory=list)
    errors: list[EvaluationNotice] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    created_at: str
    started_at: str | None = None
    updated_at: str
    heartbeat_at: str | None = None
    finished_at: str | None = None
    poll_url: str


class KnowledgeEvaluationListResponse(EvaluationApiModel):
    evaluations: list[KnowledgeEvaluationResponse] = Field(default_factory=list)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)


class KnowledgeEvaluationDetailResponse(EvaluationApiModel):
    evaluation: KnowledgeEvaluationResponse


class KnowledgeEvaluationComparison(EvaluationApiModel):
    comparison_id: str
    run_id: str
    case_id: str | None = None
    task_title: str
    knowledge_type: str
    issue_type: str
    display_title: str
    expected_card_id: str | None = None
    actual_review_item_id: str | None = None
    expected_card: dict[str, Any] | None = None
    actual_card: dict[str, Any] | None = None
    match_basis: str | None = None
    field_diffs: list[dict[str, Any]] = Field(default_factory=list)
    judge_result: dict[str, Any] | None = None
    explanation: dict[str, Any] | None = None


class KnowledgeEvaluationComparisonListResponse(EvaluationApiModel):
    comparisons: list[KnowledgeEvaluationComparison] = Field(default_factory=list)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)


class EvaluationJudgeCallResponse(EvaluationApiModel):
    judge_call: JudgeCallRecord


class EvaluationDeleteResponse(EvaluationApiModel):
    evaluation_id: str
    lifecycle: EvaluationLifecycle = EvaluationLifecycle.REJECTED
