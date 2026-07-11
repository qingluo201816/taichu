"""Deterministic and judge-ready knowledge-extraction evaluation contracts."""

from taichu.application.evaluations.knowledge_extraction.matcher import (
    match_candidates,
    match_weight_for,
)
from taichu.application.evaluations.knowledge_extraction.metrics import (
    assemble_deterministic_metrics,
    case_scope_matches,
    classify_eligibility,
    compare_source_hashes,
    compare_structured_fields,
    compute_candidate_identification_metrics,
    compute_batch_diagnostic_metrics,
    compute_duplicate_candidate_rate,
    compute_evidence_metrics,
    compute_evidence_metrics_from_spans,
    compute_execution_coverage,
    compute_negative_suppression,
    compute_overall_quality_score,
    compute_schema_compliance_rate,
    compute_set_score,
    deterministic_quality_state,
    final_quality_state,
    semantic_quality_state,
)
from taichu.application.evaluations.knowledge_extraction.profiles import (
    KNOWLEDGE_EXTRACTION_BALANCED,
    MetricProfile,
    all_metric_profiles,
    get_metric_profile,
)

__all__ = [
    "KNOWLEDGE_EXTRACTION_BALANCED",
    "MetricProfile",
    "all_metric_profiles",
    "assemble_deterministic_metrics",
    "case_scope_matches",
    "classify_eligibility",
    "compare_source_hashes",
    "compare_structured_fields",
    "compute_batch_diagnostic_metrics",
    "compute_candidate_identification_metrics",
    "compute_duplicate_candidate_rate",
    "compute_evidence_metrics",
    "compute_evidence_metrics_from_spans",
    "compute_execution_coverage",
    "compute_negative_suppression",
    "compute_overall_quality_score",
    "compute_schema_compliance_rate",
    "compute_set_score",
    "deterministic_quality_state",
    "final_quality_state",
    "get_metric_profile",
    "match_candidates",
    "match_weight_for",
    "semantic_quality_state",
]
