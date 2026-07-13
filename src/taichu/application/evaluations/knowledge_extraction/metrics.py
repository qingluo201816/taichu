"""Pure deterministic metrics and quality-state aggregation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from taichu.application.evaluations.knowledge_extraction.models import (
    ActualCandidate,
    BatchDiagnosticMetrics,
    CandidateAction,
    CandidateIdentificationMetrics,
    CandidateMatchResult,
    CandidateTypeMetrics,
    DeterministicEvaluationMetrics,
    DeterministicQualityInputs,
    EligibilityFacts,
    EligibilityLevel,
    EligibilityReason,
    EvaluationCaseRef,
    EvaluationEligibility,
    EvaluationRules,
    EvaluationScopeType,
    EvidenceMetrics,
    ExpectedEvidenceGroup,
    ExpectedCard,
    FieldComparisonKind,
    FieldDiff,
    LocatedEvidence,
    NegativeCase,
    NegativeSuppressionMetrics,
    OverallScoreInputs,
    QualityState,
    SemanticQualityInputs,
    SetScore,
    StructuredFieldMetrics,
)
from taichu.application.evaluations.knowledge_extraction.normalization import (
    normalize_exact_value,
    normalize_identity,
    normalize_set,
    normalized_identities,
)
from taichu.application.evaluations.knowledge_extraction.profiles import (
    KNOWLEDGE_EXTRACTION_BALANCED,
    MetricProfile,
)
from taichu.domain.models.structured_knowledge import StructuredKnowledgeType


# 作者人工判断的出现频率不参与模型提取质量的对错评测。
_NON_EVALUATED_CARD_FIELDS = frozenset({"appearance_chapter_count"})


def _harmonic_mean(left: float, right: float) -> float:
    if left + right == 0:
        return 0.0
    return 2 * left * right / (left + right)


def _candidate_metrics(
    true_positive_count: int,
    false_positive_count: int,
    false_negative_count: int,
) -> CandidateTypeMetrics:
    actual_count = true_positive_count + false_positive_count
    expected_count = true_positive_count + false_negative_count
    if actual_count == 0 and expected_count == 0:
        precision = recall = f1 = None
    elif actual_count == 0:
        precision = recall = f1 = 0.0
    elif expected_count == 0:
        precision = 0.0
        recall = None
        f1 = 0.0
    else:
        precision = true_positive_count / actual_count
        recall = true_positive_count / expected_count
        f1 = _harmonic_mean(precision, recall)
    return CandidateTypeMetrics(
        true_positive_count=true_positive_count,
        false_positive_count=false_positive_count,
        false_negative_count=false_negative_count,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def compute_candidate_identification_metrics(
    result: CandidateMatchResult,
) -> CandidateIdentificationMetrics:
    """Compute micro and eight-type macro candidate identification metrics."""

    true_positives = Counter(match.knowledge_type for match in result.matches)
    false_positives = Counter(item.knowledge_type for item in result.false_positives)
    false_negatives = Counter(item.knowledge_type for item in result.false_negatives)
    by_type = {
        knowledge_type: _candidate_metrics(
            true_positives[knowledge_type],
            false_positives[knowledge_type],
            false_negatives[knowledge_type],
        )
        for knowledge_type in StructuredKnowledgeType
    }
    macro_values = [metric.f1 for metric in by_type.values() if metric.f1 is not None]
    micro = _candidate_metrics(
        sum(true_positives.values()),
        sum(false_positives.values()),
        sum(false_negatives.values()),
    )
    return CandidateIdentificationMetrics(
        micro=micro,
        by_type=by_type,
        macro_f1=(sum(macro_values) / len(macro_values) if macro_values else None),
        ambiguous_count=result.ambiguous_count,
    )


def compute_set_score(actual_values: Any, expected_values: Any) -> SetScore:
    """Compute set precision/recall/F1 using the documented N/A rules."""

    actual = normalize_set(actual_values)
    expected = normalize_set(expected_values)
    if not actual and not expected:
        return SetScore(precision=None, recall=None, f1=None)
    if not actual:
        return SetScore(precision=0.0, recall=0.0, f1=0.0)
    if not expected:
        return SetScore(precision=0.0, recall=None, f1=0.0)
    intersection_count = len(actual & expected)
    precision = intersection_count / len(actual)
    recall = intersection_count / len(expected)
    return SetScore(
        precision=precision,
        recall=recall,
        f1=_harmonic_mean(precision, recall),
    )


def _reference_score(
    actual_value: Any,
    expected_value: Any,
    identity_map: Mapping[str, str],
) -> tuple[float | None, str | None]:
    actual = normalize_exact_value(actual_value)
    expected = normalize_exact_value(expected_value)
    if not actual and not expected:
        return 1.0, None
    if not actual or not expected:
        return 0.0, None
    actual_identity = identity_map.get(str(actual))
    expected_identity = identity_map.get(str(expected))
    if actual_identity is None or expected_identity is None:
        return None, "reference_identity_unavailable"
    return (
        float(
            normalize_identity(actual_identity) == normalize_identity(expected_identity)
        ),
        None,
    )


def _exact_values_equal(actual_value: Any, expected_value: Any) -> bool:
    actual = normalize_exact_value(actual_value)
    expected = normalize_exact_value(expected_value)
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    return actual == expected


def compare_structured_fields(
    match_result: CandidateMatchResult,
    actual_candidates: Sequence[ActualCandidate],
    expected_cards: Sequence[ExpectedCard],
    rules: EvaluationRules,
) -> StructuredFieldMetrics:
    """Compare projected exact/set fields for all successfully matched cards."""

    actual_by_id = {
        candidate.actual_candidate_id: candidate for candidate in actual_candidates
    }
    expected_by_id = {card.expected_card_id: card for card in expected_cards}
    diffs: list[FieldDiff] = []
    weighted_correct = 0.0
    weighted_total = 0.0
    reference_fields = set(rules.reference_fields)

    for match in match_result.matches:
        try:
            actual = actual_by_id[match.actual_candidate_id]
            expected = expected_by_id[match.expected_card_id]
        except KeyError as exc:
            raise ValueError(
                "match refers to a card outside the supplied inputs"
            ) from exc

        for field_name in expected.exact_fields:
            if field_name in _NON_EVALUATED_CARD_FIELDS:
                continue
            actual_value = actual.card.get(field_name)
            expected_value = expected.card.get(field_name)
            weight = rules.field_weights.get(field_name, 1.0)
            if field_name in reference_fields:
                kind = FieldComparisonKind.REFERENCE
                score, reason = _reference_score(
                    actual_value,
                    expected_value,
                    rules.reference_identity_map,
                )
            else:
                kind = FieldComparisonKind.EXACT
                score = float(_exact_values_equal(actual_value, expected_value))
                reason = None
            comparable = score is not None
            diffs.append(
                FieldDiff(
                    actual_candidate_id=actual.actual_candidate_id,
                    expected_card_id=expected.expected_card_id,
                    field_name=field_name,
                    kind=kind,
                    expected_value=expected_value,
                    actual_value=actual_value,
                    score=score,
                    weight=weight,
                    comparable=comparable,
                    reason=reason,
                )
            )
            if comparable and score is not None:
                weighted_correct += score * weight
                weighted_total += weight

        for field_name in expected.set_fields:
            if field_name in _NON_EVALUATED_CARD_FIELDS:
                continue
            actual_value = actual.card.get(field_name)
            expected_value = expected.card.get(field_name)
            weight = rules.field_weights.get(field_name, 1.0)
            set_score = compute_set_score(actual_value, expected_value)
            comparable = set_score.f1 is not None
            reason = None if comparable else "empty_set_not_applicable"
            diffs.append(
                FieldDiff(
                    actual_candidate_id=actual.actual_candidate_id,
                    expected_card_id=expected.expected_card_id,
                    field_name=field_name,
                    kind=FieldComparisonKind.SET,
                    expected_value=expected_value,
                    actual_value=actual_value,
                    score=set_score.f1,
                    weight=weight,
                    comparable=comparable,
                    reason=reason,
                )
            )
            if comparable and set_score.f1 is not None:
                weighted_correct += set_score.f1 * weight
                weighted_total += weight

    return StructuredFieldMetrics(
        score=(weighted_correct / weighted_total if weighted_total else None),
        weighted_correct=weighted_correct,
        weighted_total=weighted_total,
        diffs=diffs,
    )


def compute_evidence_metrics(
    *,
    matched_card_count: int,
    actual_evidence_count: int,
    grounded_evidence_count: int,
    expected_evidence_group_count: int,
    covered_evidence_group_count: int,
) -> EvidenceMetrics:
    """Compute evidence metrics after the locator has produced audited counts."""

    counts = (
        matched_card_count,
        actual_evidence_count,
        grounded_evidence_count,
        expected_evidence_group_count,
        covered_evidence_group_count,
    )
    if any(value < 0 for value in counts):
        raise ValueError("evidence counts cannot be negative")
    if grounded_evidence_count > actual_evidence_count:
        raise ValueError("grounded evidence cannot exceed actual evidence")
    if covered_evidence_group_count > expected_evidence_group_count:
        raise ValueError("covered groups cannot exceed expected groups")

    if matched_card_count == 0:
        grounded_precision = expected_recall = score = None
    elif expected_evidence_group_count > 0 and actual_evidence_count == 0:
        grounded_precision = expected_recall = score = 0.0
    else:
        grounded_precision = (
            grounded_evidence_count / actual_evidence_count
            if actual_evidence_count
            else None
        )
        expected_recall = (
            covered_evidence_group_count / expected_evidence_group_count
            if expected_evidence_group_count
            else None
        )
        score = (
            _harmonic_mean(grounded_precision, expected_recall)
            if grounded_precision is not None and expected_recall is not None
            else None
        )
    return EvidenceMetrics(
        actual_evidence_count=actual_evidence_count,
        grounded_evidence_count=grounded_evidence_count,
        expected_evidence_group_count=expected_evidence_group_count,
        covered_evidence_group_count=covered_evidence_group_count,
        grounded_precision=grounded_precision,
        expected_recall=expected_recall,
        score=score,
    )


def _evidence_overlaps(
    actual: LocatedEvidence,
    expected_chapter_id: str,
    expected_start_offset: int,
    expected_end_offset: int,
) -> bool:
    if not actual.located or actual.chapter_id != expected_chapter_id:
        return False
    assert actual.start_offset is not None
    assert actual.end_offset is not None
    return max(actual.start_offset, expected_start_offset) < min(
        actual.end_offset,
        expected_end_offset,
    )


def compute_evidence_metrics_from_spans(
    *,
    matched_card_count: int,
    actual_evidence: Sequence[LocatedEvidence],
    expected_groups: Sequence[ExpectedEvidenceGroup],
) -> EvidenceMetrics:
    """Compute evidence metrics from same-chapter half-open interval overlap."""

    located = [evidence for evidence in actual_evidence if evidence.located]
    covered_group_count = sum(
        1
        for group in expected_groups
        if any(
            _evidence_overlaps(
                actual,
                quote.chapter_id,
                quote.start_offset,
                quote.end_offset,
            )
            for actual in located
            for quote in group.quotes
        )
    )
    return compute_evidence_metrics(
        matched_card_count=matched_card_count,
        actual_evidence_count=len(actual_evidence),
        grounded_evidence_count=len(located),
        expected_evidence_group_count=len(expected_groups),
        covered_evidence_group_count=covered_group_count,
    )


def compute_negative_suppression(
    actual_candidates: Sequence[ActualCandidate],
    negative_cases: Sequence[NegativeCase],
) -> NegativeSuppressionMetrics:
    """Measure how many human-confirmed negative examples avoided card creation."""

    violated_case_ids: list[str] = []
    for negative_case in negative_cases:
        negative_names = {
            normalize_identity(name)
            for name in negative_case.accepted_names
            if normalize_identity(name)
        }
        violated = any(
            candidate.knowledge_type is negative_case.knowledge_type
            and bool(
                normalized_identities(candidate.name, candidate.aliases)
                & negative_names
            )
            for candidate in actual_candidates
        )
        if violated:
            violated_case_ids.append(negative_case.negative_case_id)

    total = len(negative_cases)
    suppressed = total - len(violated_case_ids)
    return NegativeSuppressionMetrics(
        negative_case_count=total,
        suppressed_count=suppressed,
        violated_case_ids=sorted(violated_case_ids),
        score=(suppressed / total if total else None),
    )


def compute_schema_compliance_rate(
    *,
    passed_count: int,
    total_count: int,
) -> float | None:
    """Return schema compliance as 0..1, or N/A for a zero denominator."""

    if passed_count < 0 or total_count < 0 or passed_count > total_count:
        raise ValueError("invalid schema compliance counts")
    return passed_count / total_count if total_count else None


def compute_execution_coverage(
    *,
    scope_type: EvaluationScopeType,
    run_status: str,
    expected_chapter_ids: Sequence[str],
    batch_chapter_statuses: Mapping[str, str] | None = None,
    failed_chapter_count: int = 0,
) -> float:
    """Compute run completeness from scope-specific source-of-truth fields."""

    if failed_chapter_count < 0:
        raise ValueError("failed_chapter_count cannot be negative")
    if scope_type is EvaluationScopeType.CHAPTER:
        if len(expected_chapter_ids) != 1:
            raise ValueError("chapter scope must expect exactly one chapter")
        return float(run_status == "completed")

    expected = set(expected_chapter_ids)
    if not expected:
        raise ValueError("batch scope must expect at least one chapter")
    statuses = batch_chapter_statuses or {}
    successful_count = sum(
        1 for chapter_id in expected if statuses.get(chapter_id) == "success"
    )
    if failed_chapter_count and successful_count == len(expected):
        successful_count -= 1
    return successful_count / len(expected)


def case_scope_matches(
    case: EvaluationCaseRef,
    *,
    scope_type: EvaluationScopeType,
    chapter_ids: Sequence[str],
) -> bool:
    """Match a run scope to a case without using chapter order as identity."""

    if case.scope_type is not scope_type:
        return False
    if scope_type is EvaluationScopeType.CHAPTER:
        return len(chapter_ids) == 1 and chapter_ids[0] == case.chapter_ids[0]
    return len(chapter_ids) == len(set(chapter_ids)) and set(chapter_ids) == set(
        case.chapter_ids
    )


def compare_source_hashes(
    expected_hashes: Mapping[str, str],
    actual_hashes: Mapping[str, str] | None,
) -> bool | None:
    """Return true, false, or unverified for a frozen run's source hashes."""

    if not actual_hashes or any(
        chapter_id not in actual_hashes for chapter_id in expected_hashes
    ):
        return None
    return all(
        actual_hashes[chapter_id] == expected_hash
        for chapter_id, expected_hash in expected_hashes.items()
    )


def classify_eligibility(facts: EligibilityFacts) -> EvaluationEligibility:
    """Classify a run as full, diagnostic, or ineligible in stable order."""

    blockers: list[EligibilityReason] = []
    if not facts.has_matching_case:
        blockers.append(EligibilityReason.CASE_NOT_FOUND)
    if not facts.dataset_valid:
        blockers.append(EligibilityReason.DATASET_INVALID)
    if not facts.candidates_readable:
        blockers.append(EligibilityReason.CANDIDATES_UNREADABLE)
    if not facts.snapshot_available:
        blockers.append(EligibilityReason.SNAPSHOT_UNAVAILABLE)
    if facts.source_hash_matches is False:
        blockers.append(EligibilityReason.SOURCE_HASH_MISMATCH)
    if blockers:
        return EvaluationEligibility(
            level=EligibilityLevel.INELIGIBLE,
            reasons=blockers,
            execution_coverage=facts.execution_coverage,
        )

    diagnostic_reasons: list[EligibilityReason] = []
    if facts.source_hash_matches is None:
        diagnostic_reasons.append(EligibilityReason.SOURCE_HASH_UNVERIFIED)
    if facts.execution_coverage < 1:
        diagnostic_reasons.append(EligibilityReason.INCOMPLETE_EXECUTION)
    if any(
        action in {CandidateAction.CONFLICT, CandidateAction.IGNORE}
        for action in facts.candidate_actions
    ):
        diagnostic_reasons.append(EligibilityReason.UNRESOLVED_ACTION)
    return EvaluationEligibility(
        level=(
            EligibilityLevel.DIAGNOSTIC if diagnostic_reasons else EligibilityLevel.FULL
        ),
        reasons=diagnostic_reasons,
        execution_coverage=facts.execution_coverage,
    )


def compute_duplicate_candidate_rate(
    actual_candidates: Sequence[ActualCandidate],
) -> float | None:
    """Return duplicate normalized type/name occurrences divided by card count."""

    if not actual_candidates:
        return None
    seen: set[tuple[StructuredKnowledgeType, str]] = set()
    duplicate_count = 0
    for candidate in actual_candidates:
        normalized_name = normalize_identity(candidate.name)
        key = (
            candidate.knowledge_type,
            normalized_name or candidate.actual_candidate_id,
        )
        if key in seen:
            duplicate_count += 1
        else:
            seen.add(key)
    return duplicate_count / len(actual_candidates)


def _checked_rate(correct_count: int, total_count: int, label: str) -> float | None:
    if correct_count < 0 or total_count < 0 or correct_count > total_count:
        raise ValueError(f"invalid {label} counts")
    return correct_count / total_count if total_count else None


def compute_batch_diagnostic_metrics(
    *,
    duplicate_candidate_count: int,
    total_candidate_count: int,
    merge_miss_count: int,
    merge_error_count: int,
    first_seen_correct_count: int,
    first_seen_total_count: int,
    last_seen_correct_count: int,
    last_seen_total_count: int,
    covered_source_chapter_count: int,
    expected_source_chapter_count: int,
) -> BatchDiagnosticMetrics:
    """Compute batch-only rates while preserving zero-denominator N/A values."""

    if merge_miss_count < 0 or merge_error_count < 0:
        raise ValueError("merge diagnostic counts cannot be negative")
    return BatchDiagnosticMetrics(
        duplicate_candidate_rate=_checked_rate(
            duplicate_candidate_count,
            total_candidate_count,
            "duplicate candidate",
        ),
        merge_miss_count=merge_miss_count,
        merge_error_count=merge_error_count,
        first_seen_chapter_accuracy=_checked_rate(
            first_seen_correct_count,
            first_seen_total_count,
            "first seen chapter",
        ),
        last_seen_chapter_accuracy=_checked_rate(
            last_seen_correct_count,
            last_seen_total_count,
            "last seen chapter",
        ),
        source_chapter_coverage=_checked_rate(
            covered_source_chapter_count,
            expected_source_chapter_count,
            "source chapter coverage",
        ),
    )


def deterministic_quality_state(
    inputs: DeterministicQualityInputs,
    profile: MetricProfile = KNOWLEDGE_EXTRACTION_BALANCED,
) -> QualityState:
    """Apply the deterministic short-board thresholds in documented order."""

    required = (
        inputs.candidate_f1_micro,
        inputs.structured_field_score,
        inputs.evidence_score,
        inputs.negative_suppression_score,
        inputs.schema_compliance_rate,
    )
    if any(value is None for value in required):
        return QualityState.NOT_COMPARABLE
    candidate, structured, evidence, negative, schema = required
    assert candidate is not None
    assert structured is not None
    assert evidence is not None
    assert negative is not None
    assert schema is not None
    thresholds = profile.deterministic_thresholds
    if (
        candidate >= thresholds.stable_candidate_f1
        and structured >= thresholds.stable_structured_score
        and evidence >= thresholds.stable_evidence_score
        and negative >= thresholds.stable_negative_score
        and schema == 1
        and inputs.ambiguous_count == 0
        and not inputs.has_structural_conflict
    ):
        return QualityState.STABLE
    if (
        candidate >= thresholds.usable_candidate_f1
        and structured >= thresholds.usable_structured_score
        and evidence >= thresholds.usable_evidence_score
        and negative >= thresholds.usable_negative_score
        and schema == 1
        and not inputs.has_structural_conflict
    ):
        return QualityState.USABLE
    if (
        candidate >= thresholds.needs_review_candidate_f1
        and schema == 1
        and not inputs.has_structural_conflict
    ):
        return QualityState.NEEDS_REVIEW
    return QualityState.HIGH_RISK


def semantic_quality_state(
    inputs: SemanticQualityInputs,
    profile: MetricProfile = KNOWLEDGE_EXTRACTION_BALANCED,
) -> QualityState:
    """Classify judge aggregates without allowing advisory risks to become facts."""

    if inputs.confirmed_hard_risk:
        return QualityState.HIGH_RISK
    if (
        not inputs.judge_enabled
        or inputs.semantic_score is None
        or inputs.judge_coverage is None
        or inputs.critical_claims_covered is not True
    ):
        return QualityState.NOT_COMPARABLE

    thresholds = profile.semantic_thresholds
    if inputs.semantic_score < thresholds.needs_review_score:
        return QualityState.HIGH_RISK
    if (
        inputs.self_judge
        or inputs.unknown_model_independence
        or inputs.reference_conflict
        or inputs.advisory_risk
        or inputs.judge_disagreement
    ):
        return QualityState.NEEDS_REVIEW
    if (
        inputs.semantic_score >= thresholds.stable_score
        and inputs.judge_coverage == thresholds.stable_coverage
        and not inputs.has_formal_critical_flag
    ):
        return QualityState.STABLE
    if (
        inputs.semantic_score >= thresholds.usable_score
        and inputs.judge_coverage >= thresholds.usable_coverage
        and not inputs.has_formal_critical_flag
    ):
        return QualityState.USABLE
    return QualityState.NEEDS_REVIEW


def compute_overall_quality_score(
    inputs: OverallScoreInputs,
    profile: MetricProfile = KNOWLEDGE_EXTRACTION_BALANCED,
) -> float | None:
    """Compute the non-renormalizing overall score only when every gate passes."""

    if (
        inputs.eligibility_level is not EligibilityLevel.FULL
        or not inputs.dataset_confirmed
        or not inputs.dataset_checksum_valid
        or inputs.execution_coverage < 1
        or not inputs.candidate_snapshot_valid
        or not inputs.source_hash_matches
        or inputs.judge_coverage is None
        or inputs.judge_coverage < profile.minimum_overall_judge_coverage
        or not inputs.critical_claims_covered
        or inputs.unresolved_critical_disagreement
    ):
        return None
    components = {
        "candidate_f1_micro": inputs.candidate_f1_micro,
        "structured_field_score": inputs.structured_field_score,
        "semantic_score": inputs.semantic_score,
        "evidence_score": inputs.evidence_score,
        "negative_suppression_score": inputs.negative_suppression_score,
    }
    if any(value is None for value in components.values()):
        return None
    weights = profile.overall_weights.model_dump()
    score = 0.0
    for name, weight in weights.items():
        component = components[name]
        assert component is not None
        score += component * weight
    return score


_QUALITY_RANK = {
    QualityState.HIGH_RISK: 0,
    QualityState.NEEDS_REVIEW: 1,
    QualityState.USABLE: 2,
    QualityState.STABLE: 3,
}


def final_quality_state(
    *,
    eligibility_level: EligibilityLevel,
    deterministic_state: QualityState,
    semantic_state: QualityState,
    confirmed_hard_risk: bool = False,
    reference_conflict: bool = False,
) -> QualityState:
    """Return the worse comparable state, with explicit non-comparable handling."""

    if confirmed_hard_risk:
        return QualityState.HIGH_RISK
    if eligibility_level is not EligibilityLevel.FULL:
        return QualityState.NOT_COMPARABLE
    if (
        deterministic_state is QualityState.NOT_COMPARABLE
        or semantic_state is QualityState.NOT_COMPARABLE
    ):
        return QualityState.NOT_COMPARABLE
    result = min(
        (deterministic_state, semantic_state),
        key=lambda state: _QUALITY_RANK[state],
    )
    if (
        reference_conflict
        and _QUALITY_RANK[result] > _QUALITY_RANK[QualityState.NEEDS_REVIEW]
    ):
        return QualityState.NEEDS_REVIEW
    return result


def assemble_deterministic_metrics(
    *,
    candidate_metrics: CandidateIdentificationMetrics,
    structured_metrics: StructuredFieldMetrics,
    evidence_metrics: EvidenceMetrics,
    negative_metrics: NegativeSuppressionMetrics,
    schema_compliance_rate: float | None,
    execution_coverage: float,
    has_structural_conflict: bool = False,
    profile: MetricProfile = KNOWLEDGE_EXTRACTION_BALANCED,
) -> DeterministicEvaluationMetrics:
    """Assemble deterministic results and derive their short-board state."""

    state = deterministic_quality_state(
        DeterministicQualityInputs(
            candidate_f1_micro=candidate_metrics.micro.f1,
            structured_field_score=structured_metrics.score,
            evidence_score=evidence_metrics.score,
            negative_suppression_score=negative_metrics.score,
            schema_compliance_rate=schema_compliance_rate,
            ambiguous_count=candidate_metrics.ambiguous_count,
            has_structural_conflict=has_structural_conflict,
        ),
        profile,
    )
    return DeterministicEvaluationMetrics(
        candidates=candidate_metrics,
        structured_fields=structured_metrics,
        evidence=evidence_metrics,
        negative_suppression=negative_metrics,
        schema_compliance_rate=schema_compliance_rate,
        execution_coverage=execution_coverage,
        deterministic_quality_state=state,
    )
