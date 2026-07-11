"""Tests for deterministic knowledge-extraction evaluation metrics."""

from __future__ import annotations

import pytest

from taichu.application.evaluations.knowledge_extraction.matcher import (
    match_candidates,
)
from taichu.application.evaluations.knowledge_extraction.metrics import (
    case_scope_matches,
    classify_eligibility,
    compare_source_hashes,
    compare_structured_fields,
    compute_batch_diagnostic_metrics,
    compute_candidate_identification_metrics,
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
from taichu.application.evaluations.knowledge_extraction.models import (
    ActualCandidate,
    CandidateAction,
    CandidateMatch,
    CandidateMatchResult,
    CandidateRef,
    DeterministicQualityInputs,
    EligibilityFacts,
    EligibilityLevel,
    EligibilityReason,
    EvaluationCaseRef,
    EvaluationRules,
    EvaluationScopeType,
    ExpectedCard,
    ExpectedEvidenceGroup,
    LocatedEvidence,
    MatchKind,
    NegativeCase,
    OverallScoreInputs,
    QualityState,
    SemanticQualityInputs,
    SourceEvidence,
)
from taichu.domain.models.structured_knowledge import StructuredKnowledgeType


def _actual(
    candidate_id: str,
    name: str,
    *,
    aliases: list[str] | None = None,
    card_fields: dict[str, object] | None = None,
) -> ActualCandidate:
    card: dict[str, object] = {
        "type": "character",
        "name": name,
        "aliases": aliases or [],
    }
    card.update(card_fields or {})
    return ActualCandidate(
        actual_candidate_id=candidate_id,
        knowledge_type=StructuredKnowledgeType.CHARACTER,
        card=card,
    )


def _expected(
    card_id: str,
    name: str,
    *,
    aliases: list[str] | None = None,
    card_fields: dict[str, object] | None = None,
    exact_fields: list[str] | None = None,
    set_fields: list[str] | None = None,
) -> ExpectedCard:
    card: dict[str, object] = {
        "type": "character",
        "name": name,
        "aliases": aliases or [],
    }
    card.update(card_fields or {})
    return ExpectedCard(
        expected_card_id=card_id,
        knowledge_type=StructuredKnowledgeType.CHARACTER,
        card=card,
        accepted_names=[],
        exact_fields=exact_fields or [],
        set_fields=set_fields or [],
        semantic_fields=[],
        expected_claims=[],
        source_quote_ids=[f"quote_{card_id}"],
    )


def _ref(
    card_id: str,
    knowledge_type: StructuredKnowledgeType,
) -> CandidateRef:
    return CandidateRef(
        card_id=card_id,
        knowledge_type=knowledge_type,
        name=card_id,
    )


def test_candidate_metrics_follow_all_zero_denominator_rules() -> None:
    character = StructuredKnowledgeType.CHARACTER
    faction = StructuredKnowledgeType.FACTION
    result = CandidateMatchResult(
        matches=[
            CandidateMatch(
                actual_candidate_id="a1",
                expected_card_id="e1",
                knowledge_type=character,
                kind=MatchKind.EXACT_NAME,
                weight=100,
                normalized_key="甲",
            )
        ],
        false_positives=[_ref("a2", character), _ref("a3", faction)],
        false_negatives=[_ref("e2", character)],
    )

    metrics = compute_candidate_identification_metrics(result)

    assert metrics.micro.precision == pytest.approx(1 / 3)
    assert metrics.micro.recall == pytest.approx(1 / 2)
    assert metrics.micro.f1 == pytest.approx(0.4)
    assert metrics.by_type[character].f1 == pytest.approx(0.5)
    assert metrics.by_type[faction].precision == 0
    assert metrics.by_type[faction].recall is None
    assert metrics.by_type[faction].f1 == 0
    assert metrics.by_type[StructuredKnowledgeType.ITEM].f1 is None
    assert metrics.macro_f1 == pytest.approx(0.25)


@pytest.mark.parametrize(
    ("actual", "expected", "precision", "recall", "f1"),
    [
        ([], [], None, None, None),
        ([], ["甲"], 0.0, 0.0, 0.0),
        (["甲"], [], 0.0, None, 0.0),
        (["甲", "额外"], ["甲", "乙"], 0.5, 0.5, 0.5),
    ],
)
def test_set_score_uses_candidate_metric_boundary_semantics(
    actual: list[str],
    expected: list[str],
    precision: float | None,
    recall: float | None,
    f1: float | None,
) -> None:
    result = compute_set_score(actual, expected)
    assert result.precision == precision
    assert result.recall == recall
    assert result.f1 == f1


def test_structured_score_weights_fields_and_excludes_unmapped_references() -> None:
    actual = _actual(
        "a",
        "秦浩轩",
        aliases=["小轩", "额外"],
        card_fields={"status": "active", "leader_id": "actual_leader"},
    )
    expected = _expected(
        "e",
        "秦浩轩",
        aliases=["小轩", "浩轩"],
        card_fields={"status": "active", "leader_id": "gold_leader"},
        exact_fields=["status", "leader_id"],
        set_fields=["aliases"],
    )
    matches = match_candidates([actual], [expected])

    metrics = compare_structured_fields(
        matches,
        [actual],
        [expected],
        EvaluationRules(field_weights={"status": 2, "leader_id": 3, "aliases": 1}),
    )

    assert metrics.weighted_total == 3
    assert metrics.weighted_correct == pytest.approx(2.5)
    assert metrics.score == pytest.approx(5 / 6)
    reference_diff = next(
        diff for diff in metrics.diffs if diff.field_name == "leader_id"
    )
    assert reference_diff.comparable is False
    assert reference_diff.score is None
    assert reference_diff.reason == "reference_identity_unavailable"


def test_reference_ids_compare_through_canonical_identity_map() -> None:
    actual = _actual(
        "a",
        "太初教",
        card_fields={"leader_id": "runtime_qin"},
    )
    expected = _expected(
        "e",
        "太初教",
        card_fields={"leader_id": "gold_qin"},
        exact_fields=["leader_id"],
    )

    metrics = compare_structured_fields(
        match_candidates([actual], [expected]),
        [actual],
        [expected],
        EvaluationRules(
            reference_identity_map={
                "runtime_qin": "character:秦浩轩",
                "gold_qin": "character: 秦浩轩",
            }
        ),
    )

    assert metrics.score == 1


def test_no_comparable_structured_fields_returns_null_not_zero() -> None:
    actual = _actual("a", "秦浩轩")
    expected = _expected("e", "秦浩轩", set_fields=["aliases"])

    metrics = compare_structured_fields(
        match_candidates([actual], [expected]),
        [actual],
        [expected],
        EvaluationRules(),
    )

    assert metrics.score is None
    assert metrics.weighted_total == 0


def test_exact_boolean_field_does_not_equal_numeric_one() -> None:
    actual = _actual("a", "规则", card_fields={"enabled": 1})
    expected = _expected(
        "e",
        "规则",
        card_fields={"enabled": True},
        exact_fields=["enabled"],
    )

    metrics = compare_structured_fields(
        match_candidates([actual], [expected]),
        [actual],
        [expected],
        EvaluationRules(),
    )

    assert metrics.score == 0


def test_evidence_metrics_handle_no_match_missing_and_normal_cases() -> None:
    no_match = compute_evidence_metrics(
        matched_card_count=0,
        actual_evidence_count=0,
        grounded_evidence_count=0,
        expected_evidence_group_count=1,
        covered_evidence_group_count=0,
    )
    missing = compute_evidence_metrics(
        matched_card_count=1,
        actual_evidence_count=0,
        grounded_evidence_count=0,
        expected_evidence_group_count=2,
        covered_evidence_group_count=0,
    )
    normal = compute_evidence_metrics(
        matched_card_count=1,
        actual_evidence_count=4,
        grounded_evidence_count=3,
        expected_evidence_group_count=2,
        covered_evidence_group_count=1,
    )

    assert no_match.score is None
    assert missing.grounded_precision == 0
    assert missing.expected_recall == 0
    assert missing.score == 0
    assert normal.grounded_precision == 0.75
    assert normal.expected_recall == 0.5
    assert normal.score == pytest.approx(0.6)


def test_evidence_zero_expected_denominator_is_not_applicable() -> None:
    metrics = compute_evidence_metrics(
        matched_card_count=1,
        actual_evidence_count=1,
        grounded_evidence_count=1,
        expected_evidence_group_count=0,
        covered_evidence_group_count=0,
    )
    assert metrics.grounded_precision == 1
    assert metrics.expected_recall is None
    assert metrics.score is None


def test_evidence_span_coverage_requires_same_chapter_overlap() -> None:
    expected_group = ExpectedEvidenceGroup(
        group_id="group-1",
        quotes=[
            SourceEvidence(
                quote_id="quote-1",
                chapter_id="chapter-1",
                text="连续原文",
                start_offset=10,
                end_offset=20,
                source_hash="a" * 64,
            )
        ],
    )
    actual = [
        LocatedEvidence(
            evidence_id="actual-1",
            chapter_id="chapter-1",
            start_offset=19,
            end_offset=25,
        ),
        LocatedEvidence(
            evidence_id="actual-2",
            chapter_id="chapter-2",
            start_offset=10,
            end_offset=20,
        ),
        LocatedEvidence(evidence_id="unlocated"),
    ]

    metrics = compute_evidence_metrics_from_spans(
        matched_card_count=1,
        actual_evidence=actual,
        expected_groups=[expected_group],
    )

    assert metrics.grounded_precision == pytest.approx(2 / 3)
    assert metrics.expected_recall == 1
    assert metrics.score == pytest.approx(0.8)


def test_negative_suppression_matches_normalized_names_and_aliases() -> None:
    negatives = [
        NegativeCase(
            negative_case_id="generic_youths",
            knowledge_type=StructuredKnowledgeType.CHARACTER,
            accepted_names=["几个少年", "少年们"],
            reason="泛称群体",
            source_quote_ids=["q1"],
        ),
        NegativeCase(
            negative_case_id="generic_elder",
            knowledge_type=StructuredKnowledgeType.CHARACTER,
            accepted_names=["某位长老"],
            reason="泛称",
            source_quote_ids=["q2"],
        ),
    ]
    candidates = [_actual("a", "围观者", aliases=["少 年 们"])]

    metrics = compute_negative_suppression(candidates, negatives)

    assert metrics.violated_case_ids == ["generic_youths"]
    assert metrics.suppressed_count == 1
    assert metrics.score == 0.5
    assert compute_negative_suppression([], []).score is None


def test_execution_coverage_uses_scope_specific_rules() -> None:
    assert (
        compute_execution_coverage(
            scope_type=EvaluationScopeType.CHAPTER,
            run_status="completed",
            expected_chapter_ids=["chapter-1"],
        )
        == 1
    )
    assert (
        compute_execution_coverage(
            scope_type=EvaluationScopeType.CHAPTER,
            run_status="failed",
            expected_chapter_ids=["chapter-1"],
        )
        == 0
    )
    assert (
        compute_execution_coverage(
            scope_type=EvaluationScopeType.CHAPTER_BATCH,
            run_status="completed",
            expected_chapter_ids=["chapter-1", "chapter-2"],
            batch_chapter_statuses={"chapter-1": "success", "chapter-2": "failed"},
        )
        == 0.5
    )


def test_case_scope_mapping_ignores_batch_order_but_rejects_duplicates() -> None:
    case = EvaluationCaseRef(
        case_id="batch-1-2",
        scope_type=EvaluationScopeType.CHAPTER_BATCH,
        chapter_ids=["chapter-1", "chapter-2"],
        source_chapter_hashes={"chapter-1": "a", "chapter-2": "b"},
        expected_cards_path="expected.json",
        evaluation_rules_path="rules.json",
        source_evidence_path="evidence.json",
        negative_cases_path="negative.json",
    )

    assert case_scope_matches(
        case,
        scope_type=EvaluationScopeType.CHAPTER_BATCH,
        chapter_ids=["chapter-2", "chapter-1"],
    )
    assert not case_scope_matches(
        case,
        scope_type=EvaluationScopeType.CHAPTER_BATCH,
        chapter_ids=["chapter-1", "chapter-1"],
    )


def test_source_hash_comparison_distinguishes_mismatch_and_unverified() -> None:
    expected = {"chapter-1": "hash-1", "chapter-2": "hash-2"}

    assert compare_source_hashes(expected, expected) is True
    assert (
        compare_source_hashes(
            expected,
            {"chapter-1": "hash-1", "chapter-2": "changed"},
        )
        is False
    )
    assert compare_source_hashes(expected, {"chapter-1": "hash-1"}) is None
    assert compare_source_hashes(expected, None) is None


def test_eligibility_distinguishes_full_diagnostic_and_ineligible() -> None:
    full = classify_eligibility(
        EligibilityFacts(
            has_matching_case=True,
            dataset_valid=True,
            candidates_readable=True,
            snapshot_available=True,
            source_hash_matches=True,
            execution_coverage=1,
            candidate_actions=[CandidateAction.CREATE_CARD],
        )
    )
    diagnostic = classify_eligibility(
        EligibilityFacts(
            has_matching_case=True,
            dataset_valid=True,
            candidates_readable=True,
            snapshot_available=True,
            source_hash_matches=None,
            execution_coverage=0.5,
            candidate_actions=[CandidateAction.UPDATE_CARD],
        )
    )
    ineligible = classify_eligibility(
        EligibilityFacts(
            has_matching_case=False,
            dataset_valid=True,
            candidates_readable=True,
            snapshot_available=True,
            source_hash_matches=False,
            execution_coverage=1,
            candidate_actions=[],
        )
    )

    assert full.level is EligibilityLevel.FULL
    assert diagnostic.level is EligibilityLevel.DIAGNOSTIC
    assert diagnostic.reasons == [
        EligibilityReason.SOURCE_HASH_UNVERIFIED,
        EligibilityReason.INCOMPLETE_EXECUTION,
        EligibilityReason.NON_CREATE_ACTION,
    ]
    assert diagnostic.can_create is True
    assert ineligible.level is EligibilityLevel.INELIGIBLE
    assert ineligible.can_create is False


def test_overall_score_uses_fixed_weights_and_never_renormalizes() -> None:
    complete = OverallScoreInputs(
        candidate_f1_micro=0.8,
        structured_field_score=0.9,
        semantic_score=0.7,
        evidence_score=0.6,
        negative_suppression_score=1.0,
        judge_coverage=0.95,
    )
    missing = complete.model_copy(update={"evidence_score": None})
    low_coverage = complete.model_copy(update={"judge_coverage": 0.89})
    diagnostic = complete.model_copy(
        update={"eligibility_level": EligibilityLevel.DIAGNOSTIC}
    )

    assert compute_overall_quality_score(complete) == pytest.approx(0.775)
    assert compute_overall_quality_score(missing) is None
    assert compute_overall_quality_score(low_coverage) is None
    assert compute_overall_quality_score(diagnostic) is None


def test_batch_diagnostics_preserve_counts_and_null_zero_denominators() -> None:
    metrics = compute_batch_diagnostic_metrics(
        duplicate_candidate_count=2,
        total_candidate_count=10,
        merge_miss_count=1,
        merge_error_count=2,
        first_seen_correct_count=3,
        first_seen_total_count=4,
        last_seen_correct_count=0,
        last_seen_total_count=0,
        covered_source_chapter_count=4,
        expected_source_chapter_count=5,
    )

    assert metrics.duplicate_candidate_rate == 0.2
    assert metrics.merge_miss_count == 1
    assert metrics.merge_error_count == 2
    assert metrics.first_seen_chapter_accuracy == 0.75
    assert metrics.last_seen_chapter_accuracy is None
    assert metrics.source_chapter_coverage == 0.8


@pytest.mark.parametrize(
    ("inputs", "expected"),
    [
        (
            DeterministicQualityInputs(
                candidate_f1_micro=0.95,
                structured_field_score=0.98,
                evidence_score=0.97,
                negative_suppression_score=0.95,
                schema_compliance_rate=1,
            ),
            QualityState.STABLE,
        ),
        (
            DeterministicQualityInputs(
                candidate_f1_micro=0.85,
                structured_field_score=0.92,
                evidence_score=0.91,
                negative_suppression_score=0.82,
                schema_compliance_rate=1,
            ),
            QualityState.USABLE,
        ),
        (
            DeterministicQualityInputs(
                candidate_f1_micro=0.65,
                structured_field_score=0.5,
                evidence_score=0.5,
                negative_suppression_score=0.5,
                schema_compliance_rate=1,
            ),
            QualityState.NEEDS_REVIEW,
        ),
        (
            DeterministicQualityInputs(
                candidate_f1_micro=0.95,
                structured_field_score=0.98,
                evidence_score=0.97,
                negative_suppression_score=0.95,
                schema_compliance_rate=0.99,
            ),
            QualityState.HIGH_RISK,
        ),
        (
            DeterministicQualityInputs(
                candidate_f1_micro=0.95,
                structured_field_score=None,
                evidence_score=0.97,
                negative_suppression_score=0.95,
                schema_compliance_rate=1,
            ),
            QualityState.NOT_COMPARABLE,
        ),
    ],
)
def test_deterministic_quality_state_is_short_board_based(
    inputs: DeterministicQualityInputs,
    expected: QualityState,
) -> None:
    assert deterministic_quality_state(inputs) is expected


def test_semantic_and_final_quality_states_apply_caps_and_hard_risks() -> None:
    stable = semantic_quality_state(
        SemanticQualityInputs(semantic_score=0.95, judge_coverage=1)
    )
    advisory = semantic_quality_state(
        SemanticQualityInputs(
            semantic_score=0.95,
            judge_coverage=1,
            self_judge=True,
        )
    )
    hard_risk = semantic_quality_state(
        SemanticQualityInputs(
            semantic_score=None,
            judge_coverage=None,
            confirmed_hard_risk=True,
        )
    )

    assert stable is QualityState.STABLE
    assert advisory is QualityState.NEEDS_REVIEW
    assert hard_risk is QualityState.HIGH_RISK
    assert (
        final_quality_state(
            eligibility_level=EligibilityLevel.FULL,
            deterministic_state=QualityState.USABLE,
            semantic_state=QualityState.STABLE,
        )
        is QualityState.USABLE
    )
    assert (
        final_quality_state(
            eligibility_level=EligibilityLevel.FULL,
            deterministic_state=QualityState.STABLE,
            semantic_state=QualityState.STABLE,
            reference_conflict=True,
        )
        is QualityState.NEEDS_REVIEW
    )
    assert (
        final_quality_state(
            eligibility_level=EligibilityLevel.DIAGNOSTIC,
            deterministic_state=QualityState.HIGH_RISK,
            semantic_state=QualityState.STABLE,
        )
        is QualityState.NOT_COMPARABLE
    )
    assert (
        final_quality_state(
            eligibility_level=EligibilityLevel.DIAGNOSTIC,
            deterministic_state=QualityState.NOT_COMPARABLE,
            semantic_state=QualityState.NOT_COMPARABLE,
            confirmed_hard_risk=True,
        )
        is QualityState.HIGH_RISK
    )


def test_schema_and_duplicate_rates_keep_zero_to_one_contract() -> None:
    assert compute_schema_compliance_rate(passed_count=3, total_count=4) == 0.75
    assert compute_schema_compliance_rate(passed_count=0, total_count=0) is None
    assert (
        compute_duplicate_candidate_rate(
            [_actual("a1", "秦浩轩"), _actual("a2", " 秦 浩轩 ")]
        )
        == 0.5
    )

    with pytest.raises(ValueError, match="invalid schema"):
        compute_schema_compliance_rate(passed_count=2, total_count=1)
