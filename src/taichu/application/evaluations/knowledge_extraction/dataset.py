"""Loaded dataset models for knowledge-extraction evaluation."""

from __future__ import annotations

from pydantic import Field

from taichu.application.evaluations.knowledge_extraction.models import (
    DatasetManifest,
    EvaluationCaseRef,
    EvaluationLifecycle,
    EvaluationModel,
    EvaluationRules,
    ExpectedCard,
    NegativeCase,
    SourceEvidence,
)


class LoadedEvaluationCase(EvaluationModel):
    """One fully loaded and validated evaluation case."""

    ref: EvaluationCaseRef
    expected_cards: list[ExpectedCard]
    rules: EvaluationRules
    source_evidence: list[SourceEvidence]
    negative_cases: list[NegativeCase]
    checksum: str = Field(min_length=1)


class LoadedEvaluationDataset(EvaluationModel):
    """One immutable dataset ready for preview or snapshotting."""

    manifest: DatasetManifest
    cases: dict[str, LoadedEvaluationCase]
    checksum: str = Field(min_length=1)


class DatasetValidationIssue(EvaluationModel):
    """One stable dataset validation problem with a Chinese explanation."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    path: str | None = None


class DatasetValidationResult(EvaluationModel):
    """Result returned by explicit dataset validation."""

    dataset_id: str = Field(min_length=1)
    valid: bool
    lifecycle: EvaluationLifecycle | None = None
    checksum: str | None = None
    issues: list[DatasetValidationIssue] = Field(default_factory=list)


class EvaluationDatasetSummary(EvaluationModel):
    """Compact dataset information used by the monitor page."""

    dataset_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    lifecycle: EvaluationLifecycle
    case_count: int = Field(ge=0)
    valid: bool
    checksum: str | None = None
    issues: list[DatasetValidationIssue] = Field(default_factory=list)
