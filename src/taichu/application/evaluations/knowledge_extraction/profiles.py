"""Stable metric profiles for knowledge-extraction evaluation."""

from __future__ import annotations

from pydantic import Field, model_validator

from taichu.application.evaluations.knowledge_extraction.models import (
    EvaluationModel,
)


class OverallMetricWeights(EvaluationModel):
    """Transparent weights used by the overall reference score."""

    candidate_f1_micro: float = Field(ge=0, le=1)
    structured_field_score: float = Field(ge=0, le=1)
    semantic_score: float = Field(ge=0, le=1)
    evidence_score: float = Field(ge=0, le=1)
    negative_suppression_score: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> OverallMetricWeights:
        if abs(sum(self.model_dump().values()) - 1.0) > 1e-9:
            raise ValueError("overall metric weights must sum to one")
        return self


class DeterministicQualityThresholds(EvaluationModel):
    """Short-board thresholds for deterministic quality states."""

    stable_candidate_f1: float = Field(ge=0, le=1)
    stable_structured_score: float = Field(ge=0, le=1)
    stable_evidence_score: float = Field(ge=0, le=1)
    stable_negative_score: float = Field(ge=0, le=1)
    usable_candidate_f1: float = Field(ge=0, le=1)
    usable_structured_score: float = Field(ge=0, le=1)
    usable_evidence_score: float = Field(ge=0, le=1)
    usable_negative_score: float = Field(ge=0, le=1)
    needs_review_candidate_f1: float = Field(ge=0, le=1)


class SemanticQualityThresholds(EvaluationModel):
    """Thresholds for judge-based semantic quality states."""

    stable_score: float = Field(ge=0, le=1)
    stable_coverage: float = Field(ge=0, le=1)
    usable_score: float = Field(ge=0, le=1)
    usable_coverage: float = Field(ge=0, le=1)
    needs_review_score: float = Field(ge=0, le=1)


class MetricProfile(EvaluationModel):
    """Frozen scoring parameters identified by a stable compatibility ID."""

    metric_profile_id: str = Field(min_length=1)
    overall_weights: OverallMetricWeights
    deterministic_thresholds: DeterministicQualityThresholds
    semantic_thresholds: SemanticQualityThresholds
    minimum_overall_judge_coverage: float = Field(ge=0, le=1)


KNOWLEDGE_EXTRACTION_BALANCED = MetricProfile(
    metric_profile_id="knowledge_extraction_balanced",
    overall_weights=OverallMetricWeights(
        candidate_f1_micro=0.35,
        structured_field_score=0.20,
        semantic_score=0.25,
        evidence_score=0.15,
        negative_suppression_score=0.05,
    ),
    deterministic_thresholds=DeterministicQualityThresholds(
        stable_candidate_f1=0.90,
        stable_structured_score=0.95,
        stable_evidence_score=0.95,
        stable_negative_score=0.90,
        usable_candidate_f1=0.80,
        usable_structured_score=0.90,
        usable_evidence_score=0.90,
        usable_negative_score=0.80,
        needs_review_candidate_f1=0.60,
    ),
    semantic_thresholds=SemanticQualityThresholds(
        stable_score=0.90,
        stable_coverage=1.0,
        usable_score=0.80,
        usable_coverage=0.95,
        needs_review_score=0.60,
    ),
    minimum_overall_judge_coverage=0.90,
)

_PROFILES = {
    KNOWLEDGE_EXTRACTION_BALANCED.metric_profile_id: KNOWLEDGE_EXTRACTION_BALANCED,
}


def get_metric_profile(metric_profile_id: str) -> MetricProfile:
    """Resolve a supported metric profile or fail closed."""

    try:
        return _PROFILES[metric_profile_id]
    except KeyError as exc:
        raise ValueError(f"unsupported metric profile: {metric_profile_id}") from exc


def all_metric_profiles() -> tuple[MetricProfile, ...]:
    """Return all registered profiles in stable ID order."""

    return tuple(_PROFILES[key] for key in sorted(_PROFILES))
