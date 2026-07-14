"""Persistent report models for knowledge-extraction effect evaluation."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from taichu.application.contracts.llm import LLMModelIdentity
from taichu.application.evaluations.knowledge_extraction.models import (
    EvaluationLifecycle,
    EvaluationModel,
    QualityState,
)


class EvaluationStatus(StrEnum):
    """Computation status for one evaluation report."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"


class EvaluationPhase(StrEnum):
    """Current background phase."""

    QUEUED = "queued"
    DETERMINISTIC = "deterministic"
    JUDGING = "judging"
    EXPLAINING = "explaining"
    AGGREGATING = "aggregating"
    FINISHED = "finished"


class EvaluationMode(StrEnum):
    """Whether semantic judging was explicitly enabled."""

    DETERMINISTIC_AND_JUDGE = "deterministic_and_judge"
    DETERMINISTIC_ONLY = "deterministic_only"


class IndependenceLevel(StrEnum):
    """Relationship between generation and judge runtimes."""

    DIFFERENT_MODEL = "different_model"
    SAME_PROVIDER_FAMILY = "same_provider_family"
    SAME_MODEL = "same_model"
    UNKNOWN = "unknown"


class DifferenceExplanationSource(StrEnum):
    """Whether a readable explanation came from the model or fixed rules."""

    MODEL = "model"
    RULE = "rule"


class DifferenceExplanation(EvaluationModel):
    """One persisted explanation shown before raw comparison details."""

    summary: str = Field(min_length=1, max_length=500)
    source: DifferenceExplanationSource
    call_id: str | None = None


class EvaluationNotice(EvaluationModel):
    """Stable code plus a Chinese explanation."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    run_id: str | None = None


class EvaluationProgress(EvaluationModel):
    """Compact progress counters polled by the monitor page."""

    run_total: int = Field(default=0, ge=0)
    run_completed: int = Field(default=0, ge=0)
    judge_card_total: int = Field(default=0, ge=0)
    judge_card_completed: int = Field(default=0, ge=0)
    judge_batch_total: int = Field(default=0, ge=0)
    judge_batch_completed: int = Field(default=0, ge=0)


class JudgeSummary(EvaluationModel):
    """Judge configuration that was actually used."""

    enabled: bool
    model_identity: LLMModelIdentity | None = None
    self_judge: bool | None = None
    independence_by_run: dict[str, IndependenceLevel] = Field(default_factory=dict)


class EvaluationComparison(EvaluationModel):
    """One expected/actual comparison with deterministic and judge details."""

    run_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    task_title: str = ""
    knowledge_type: str = Field(min_length=1)
    issue_type: str = Field(min_length=1)
    expected_card_id: str | None = None
    actual_candidate_id: str | None = None
    expected_card: dict[str, Any] | None = None
    actual_card: dict[str, Any] | None = None
    match_kind: str | None = None
    field_diffs: list[dict[str, Any]] = Field(default_factory=list)
    judge_result: dict[str, Any] | None = None
    explanation: DifferenceExplanation | None = None


class EvaluationRunResult(EvaluationModel):
    """One selected Agent run result stored independently from the summary."""

    run_id: str = Field(min_length=1)
    case_id: str | None = None
    display_title: str = ""
    eligibility_level: str = Field(min_length=1)
    eligibility_reasons: list[str] = Field(default_factory=list)
    generation_model_identity: LLMModelIdentity
    expected_card_count: int = Field(default=0, ge=0)
    actual_card_count: int = Field(default=0, ge=0)
    metrics: dict[str, Any] = Field(default_factory=dict)
    semantic_score: float | None = Field(default=None, ge=0, le=1)
    judge_coverage: float | None = Field(default=None, ge=0, le=1)
    overall_quality_score: float | None = Field(default=None, ge=0, le=1)
    final_quality_state: QualityState = QualityState.NOT_COMPARABLE
    comparisons: list[EvaluationComparison] = Field(default_factory=list)
    warnings: list[EvaluationNotice] = Field(default_factory=list)


class KnowledgeEvaluationRecord(EvaluationModel):
    """List-friendly report summary plus immutable audit references."""

    evaluation_id: str = Field(min_length=1)
    parent_evaluation_id: str | None = None
    request_fingerprint: str = Field(min_length=1)
    snapshot_root_hash: str = "pending"
    lifecycle: EvaluationLifecycle = EvaluationLifecycle.DRAFT
    status: EvaluationStatus = EvaluationStatus.PENDING
    phase: EvaluationPhase = EvaluationPhase.QUEUED
    evaluation_mode: EvaluationMode
    dataset_id: str = Field(min_length=1)
    dataset_label: str = Field(min_length=1)
    dataset_checksum: str = Field(min_length=1)
    subject_title: str = ""
    metric_profile_id: str = "knowledge_extraction_balanced"
    judge: JudgeSummary
    progress: EvaluationProgress
    run_ids: list[str] = Field(min_length=1)
    run_results: list[EvaluationRunResult] = Field(default_factory=list)
    aggregate_metrics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[EvaluationNotice] = Field(default_factory=list)
    errors: list[EvaluationNotice] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    created_at: str = Field(min_length=1)
    started_at: str | None = None
    updated_at: str = Field(min_length=1)
    heartbeat_at: str = Field(min_length=1)
    finished_at: str | None = None
    execution_token: str | None = None

    @property
    def is_active(self) -> bool:
        return self.status in {EvaluationStatus.PENDING, EvaluationStatus.RUNNING}

    @property
    def is_terminal(self) -> bool:
        return not self.is_active


class JudgeCallRecord(EvaluationModel):
    """Full auditable input and output for one judge request."""

    call_id: str = Field(min_length=1)
    evaluation_id: str = Field(min_length=1)
    run_ids: list[str] = Field(min_length=1)
    judge_model_identity: LLMModelIdentity
    independence_level: IndependenceLevel
    self_judge: bool = False
    prompt_contract_id: str = Field(min_length=1)
    prompt_hash: str = Field(min_length=1)
    input_snapshot_hash: str = Field(min_length=1)
    input_prompt: str
    raw_response: str | None = None
    parsed_output: dict[str, Any] | None = None
    started_at: str = Field(min_length=1)
    finished_at: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    retry_of: str | None = None
    error: str | None = None
    token_usage: dict[str, int] | None = None
