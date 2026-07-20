"""Pure contracts for knowledge-extraction effect evaluation."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from taichu.domain.models.structured_knowledge import StructuredKnowledgeType


class EvaluationModel(BaseModel):
    """Strict immutable base model used by the deterministic evaluation core."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class EvaluationLifecycle(StrEnum):
    """Lifecycle shared by evaluation datasets and reports."""

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class EvaluationScopeType(StrEnum):
    """Supported extraction-run scopes."""

    CHAPTER = "chapter"
    CHAPTER_BATCH = "chapter_batch"


class EligibilityLevel(StrEnum):
    """How much of the effect evaluation can be performed for one run."""

    FULL = "full"
    DIAGNOSTIC = "diagnostic"
    INELIGIBLE = "ineligible"


class EligibilityReason(StrEnum):
    """Stable machine-readable reasons for an eligibility decision."""

    CASE_NOT_FOUND = "case_not_found"
    DATASET_INVALID = "dataset_invalid"
    CANDIDATES_UNREADABLE = "candidates_unreadable"
    SNAPSHOT_UNAVAILABLE = "snapshot_unavailable"
    SOURCE_HASH_MISMATCH = "source_hash_mismatch"
    SOURCE_HASH_UNVERIFIED = "source_hash_unverified"
    INCOMPLETE_EXECUTION = "incomplete_execution"
    UNRESOLVED_ACTION = "unresolved_action"
    # 兼容已冻结的历史评估快照；新资格判断不再使用该原因。
    NON_CREATE_ACTION = "non_create_action"


class CandidateAction(StrEnum):
    """Frozen candidate actions retained for evaluation and audit."""

    CREATE_CARD = "create_card"
    UPDATE_CARD = "update_card"
    CONFLICT = "conflict"
    IGNORE = "ignore"


class MatchKind(StrEnum):
    """Deterministic identity rule that created one match edge."""

    EXACT_NAME = "exact_name"
    ACCEPTED_NAME = "accepted_name"
    ALIAS_CROSS = "alias_cross"
    EVIDENCE_ANCHOR = "evidence_anchor"
    EVENT_SEMANTIC = "event_semantic"


class FieldComparisonKind(StrEnum):
    """Supported deterministic field comparison strategies."""

    EXACT = "exact"
    SET = "set"
    REFERENCE = "reference"


class QualityState(StrEnum):
    """Comparable quality states plus the separate non-comparable state."""

    HIGH_RISK = "high_risk"
    NEEDS_REVIEW = "needs_review"
    USABLE = "usable"
    STABLE = "stable"
    NOT_COMPARABLE = "not_comparable"


class ClaimImportance(StrEnum):
    """Importance of one expected semantic claim."""

    CRITICAL = "critical"
    MAJOR = "major"
    NORMAL = "normal"
    MINOR = "minor"


class EvaluationCaseRef(EvaluationModel):
    """Manifest entry pointing to all frozen inputs for one evaluation case."""

    case_id: str = Field(min_length=1)
    scope_type: EvaluationScopeType
    chapter_ids: list[str] = Field(min_length=1)
    source_chapter_hashes: dict[str, str]
    expected_cards_path: str = Field(min_length=1)
    evaluation_rules_path: str = Field(min_length=1)
    source_evidence_path: str = Field(min_length=1)
    negative_cases_path: str = Field(min_length=1)

    @field_validator("chapter_ids")
    @classmethod
    def _chapter_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("chapter_ids must be unique")
        return value

    @model_validator(mode="after")
    def _scope_has_valid_chapter_count(self) -> EvaluationCaseRef:
        if (
            self.scope_type is EvaluationScopeType.CHAPTER
            and len(self.chapter_ids) != 1
        ):
            raise ValueError("chapter scope must contain exactly one chapter_id")
        return self


class DatasetManifest(EvaluationModel):
    """Top-level contract for one file-backed evaluation dataset."""

    dataset_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    lifecycle: EvaluationLifecycle
    agent_name: str = Field(min_length=1)
    schema_snapshot_path: str = Field(min_length=1)
    checksum_manifest_path: str = Field(min_length=1)
    cases: list[EvaluationCaseRef] = Field(min_length=1)

    @field_validator("cases")
    @classmethod
    def _case_ids_are_unique(
        cls, value: list[EvaluationCaseRef]
    ) -> list[EvaluationCaseRef]:
        case_ids = [case.case_id for case in value]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case_id must be unique within a dataset")
        return value


class ExpectedClaim(EvaluationModel):
    """One human-maintained semantic fact expected from a card."""

    claim_id: str = Field(min_length=1)
    field: str = Field(min_length=1)
    importance: ClaimImportance
    description: str = Field(min_length=1)
    source_quote_ids: list[str] = Field(min_length=1)


class ExpectedCard(EvaluationModel):
    """Gold card plus the field-level evaluation projection."""

    expected_card_id: str = Field(min_length=1)
    knowledge_type: StructuredKnowledgeType
    card: dict[str, Any]
    accepted_names: list[str]
    exact_fields: list[str]
    set_fields: list[str]
    semantic_fields: list[str]
    expected_claims: list[ExpectedClaim]
    source_quote_ids: list[str] = Field(min_length=1)

    @field_validator(
        "accepted_names",
        "exact_fields",
        "set_fields",
        "semantic_fields",
        "source_quote_ids",
    )
    @classmethod
    def _list_values_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evaluation card lists must not contain duplicates")
        return value

    @model_validator(mode="after")
    def _card_identity_is_consistent(self) -> ExpectedCard:
        name = self.card.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("expected card must contain a non-empty name")
        card_type = self.card.get("type")
        if card_type is not None and card_type != self.knowledge_type.value:
            raise ValueError("card.type must equal knowledge_type")
        projected = self.exact_fields + self.set_fields + self.semantic_fields
        if len(projected) != len(set(projected)):
            raise ValueError("a field cannot use more than one comparison strategy")
        return self


class EvaluationRules(EvaluationModel):
    """Case-specific deterministic field scoring rules."""

    field_weights: dict[str, float] = Field(default_factory=dict)
    reference_identity_map: dict[str, str] = Field(default_factory=dict)
    reference_fields: list[str] = Field(
        default_factory=lambda: [
            "owner_faction_id",
            "controlling_faction_id",
            "leader_id",
            "current_holder_id",
        ]
    )

    @field_validator("field_weights")
    @classmethod
    def _weights_are_positive(cls, value: dict[str, float]) -> dict[str, float]:
        if any(weight <= 0 for weight in value.values()):
            raise ValueError("field weights must be greater than zero")
        return value


class SourceEvidence(EvaluationModel):
    """One exact source quote frozen by the dataset."""

    quote_id: str = Field(min_length=1)
    chapter_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    source_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def _offsets_are_ordered(self) -> SourceEvidence:
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        return self


class NegativeCase(EvaluationModel):
    """Stable named object or expression that must not become a card."""

    negative_case_id: str = Field(min_length=1)
    knowledge_type: StructuredKnowledgeType
    accepted_names: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1)
    source_quote_ids: list[str] = Field(min_length=1)


class ActualCandidate(EvaluationModel):
    """Frozen actual review candidate consumed by the deterministic engine."""

    actual_candidate_id: str = Field(min_length=1)
    knowledge_type: StructuredKnowledgeType
    candidate_action: CandidateAction = CandidateAction.CREATE_CARD
    card: dict[str, Any]
    schema_valid: bool = True
    evidence_excerpts: list[str] = Field(default_factory=list)
    merge_preview_applied: bool = False

    @property
    def name(self) -> str:
        value = self.card.get("name")
        return value if isinstance(value, str) else ""

    @property
    def aliases(self) -> list[str]:
        value = self.card.get("aliases")
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]


class CandidateRef(EvaluationModel):
    """Compact identity used in unmatched and ambiguous results."""

    card_id: str = Field(min_length=1)
    knowledge_type: StructuredKnowledgeType
    name: str = ""


class CandidateMatch(EvaluationModel):
    """One deterministic one-to-one actual-to-expected match."""

    actual_candidate_id: str = Field(min_length=1)
    expected_card_id: str = Field(min_length=1)
    knowledge_type: StructuredKnowledgeType
    kind: MatchKind
    weight: int = Field(ge=1, le=100)
    normalized_key: str = Field(min_length=1)


class AmbiguousMatch(EvaluationModel):
    """One unresolved equal-weight identity component."""

    knowledge_type: StructuredKnowledgeType
    weight: int = Field(ge=1, le=100)
    actual_candidates: list[CandidateRef] = Field(min_length=1)
    expected_cards: list[CandidateRef] = Field(min_length=1)
    normalized_keys: list[str] = Field(min_length=1)


class CandidateMatchResult(EvaluationModel):
    """Complete deterministic matching result and unresolved identity sets."""

    matches: list[CandidateMatch] = Field(default_factory=list)
    false_positives: list[CandidateRef] = Field(default_factory=list)
    false_negatives: list[CandidateRef] = Field(default_factory=list)
    ambiguities: list[AmbiguousMatch] = Field(default_factory=list)

    @property
    def true_positive_count(self) -> int:
        return len(self.matches)

    @property
    def false_positive_count(self) -> int:
        return len(self.false_positives)

    @property
    def false_negative_count(self) -> int:
        return len(self.false_negatives)

    @property
    def ambiguous_count(self) -> int:
        return len(self.ambiguities)


class CandidateTypeMetrics(EvaluationModel):
    """Precision/recall metrics for one knowledge type or the micro total."""

    true_positive_count: int = Field(ge=0)
    false_positive_count: int = Field(ge=0)
    false_negative_count: int = Field(ge=0)
    precision: float | None = Field(default=None, ge=0, le=1)
    recall: float | None = Field(default=None, ge=0, le=1)
    f1: float | None = Field(default=None, ge=0, le=1)


class CandidateIdentificationMetrics(EvaluationModel):
    """Candidate metrics across the eight supported knowledge types."""

    micro: CandidateTypeMetrics
    by_type: dict[StructuredKnowledgeType, CandidateTypeMetrics]
    macro_f1: float | None = Field(default=None, ge=0, le=1)
    ambiguous_count: int = Field(ge=0)


class SetScore(EvaluationModel):
    """Deterministic set precision/recall/F1 for one projected field."""

    precision: float | None = Field(default=None, ge=0, le=1)
    recall: float | None = Field(default=None, ge=0, le=1)
    f1: float | None = Field(default=None, ge=0, le=1)


class FieldDiff(EvaluationModel):
    """One auditable deterministic field comparison."""

    actual_candidate_id: str = Field(min_length=1)
    expected_card_id: str = Field(min_length=1)
    field_name: str = Field(min_length=1)
    kind: FieldComparisonKind
    expected_value: Any = None
    actual_value: Any = None
    score: float | None = Field(default=None, ge=0, le=1)
    weight: float = Field(gt=0)
    comparable: bool
    reason: str | None = None


class StructuredFieldMetrics(EvaluationModel):
    """Weighted structured-field score and its complete diff trail."""

    score: float | None = Field(default=None, ge=0, le=1)
    weighted_correct: float = Field(ge=0)
    weighted_total: float = Field(ge=0)
    diffs: list[FieldDiff] = Field(default_factory=list)


class EvidenceMetrics(EvaluationModel):
    """Grounding precision and expected evidence recall."""

    actual_evidence_count: int = Field(ge=0)
    grounded_evidence_count: int = Field(ge=0)
    expected_evidence_group_count: int = Field(ge=0)
    covered_evidence_group_count: int = Field(ge=0)
    grounded_precision: float | None = Field(default=None, ge=0, le=1)
    expected_recall: float | None = Field(default=None, ge=0, le=1)
    score: float | None = Field(default=None, ge=0, le=1)


class LocatedEvidence(EvaluationModel):
    """One actual evidence excerpt after deterministic Markdown location."""

    evidence_id: str = Field(min_length=1)
    chapter_id: str | None = None
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _location_is_complete_and_ordered(self) -> LocatedEvidence:
        location = (self.chapter_id, self.start_offset, self.end_offset)
        if all(value is None for value in location):
            return self
        if any(value is None for value in location):
            raise ValueError("evidence location must be either complete or absent")
        assert self.start_offset is not None
        assert self.end_offset is not None
        if self.end_offset <= self.start_offset:
            raise ValueError("evidence end_offset must be greater than start_offset")
        return self

    @property
    def located(self) -> bool:
        return self.chapter_id is not None


class ExpectedEvidenceGroup(EvaluationModel):
    """Expected source quotes where any overlap is sufficient for coverage."""

    group_id: str = Field(min_length=1)
    quotes: list[SourceEvidence] = Field(min_length=1)


class NegativeSuppressionMetrics(EvaluationModel):
    """Negative-example suppression score and violated case IDs."""

    negative_case_count: int = Field(ge=0)
    suppressed_count: int = Field(ge=0)
    violated_case_ids: list[str] = Field(default_factory=list)
    score: float | None = Field(default=None, ge=0, le=1)


class BatchDiagnosticMetrics(EvaluationModel):
    """Additional diagnostics for chapter-batch extraction runs."""

    duplicate_candidate_rate: float | None = Field(default=None, ge=0, le=1)
    merge_miss_count: int = Field(ge=0)
    merge_error_count: int = Field(ge=0)
    first_seen_chapter_accuracy: float | None = Field(default=None, ge=0, le=1)
    last_seen_chapter_accuracy: float | None = Field(default=None, ge=0, le=1)
    source_chapter_coverage: float | None = Field(default=None, ge=0, le=1)


class EvaluationEligibility(EvaluationModel):
    """Eligibility conclusion for one run/case pair."""

    level: EligibilityLevel
    reasons: list[EligibilityReason] = Field(default_factory=list)
    execution_coverage: float | None = Field(default=None, ge=0, le=1)

    @property
    def can_create(self) -> bool:
        return self.level is not EligibilityLevel.INELIGIBLE


class EligibilityFacts(EvaluationModel):
    """Pure inputs needed to classify first-release run eligibility."""

    has_matching_case: bool
    dataset_valid: bool
    candidates_readable: bool
    snapshot_available: bool
    source_hash_matches: bool | None
    execution_coverage: float = Field(ge=0, le=1)
    candidate_actions: list[CandidateAction]


class OverallScoreInputs(EvaluationModel):
    """Score components and gates required for the transparent overall score."""

    candidate_f1_micro: float | None = Field(default=None, ge=0, le=1)
    structured_field_score: float | None = Field(default=None, ge=0, le=1)
    semantic_score: float | None = Field(default=None, ge=0, le=1)
    evidence_score: float | None = Field(default=None, ge=0, le=1)
    negative_suppression_score: float | None = Field(default=None, ge=0, le=1)
    eligibility_level: EligibilityLevel = EligibilityLevel.FULL
    dataset_confirmed: bool = True
    dataset_checksum_valid: bool = True
    execution_coverage: float = Field(default=1, ge=0, le=1)
    candidate_snapshot_valid: bool = True
    source_hash_matches: bool = True
    judge_coverage: float | None = Field(default=None, ge=0, le=1)
    critical_claims_covered: bool = True
    unresolved_critical_disagreement: bool = False


class DeterministicQualityInputs(EvaluationModel):
    """Inputs for the deterministic short-board quality state."""

    candidate_f1_micro: float | None = Field(default=None, ge=0, le=1)
    structured_field_score: float | None = Field(default=None, ge=0, le=1)
    evidence_score: float | None = Field(default=None, ge=0, le=1)
    negative_suppression_score: float | None = Field(default=None, ge=0, le=1)
    schema_compliance_rate: float | None = Field(default=None, ge=0, le=1)
    ambiguous_count: int = Field(default=0, ge=0)
    has_structural_conflict: bool = False


class SemanticQualityInputs(EvaluationModel):
    """Judge aggregates needed to classify semantic quality."""

    semantic_score: float | None = Field(default=None, ge=0, le=1)
    judge_coverage: float | None = Field(default=None, ge=0, le=1)
    critical_claims_covered: bool | None = True
    judge_enabled: bool = True
    confirmed_hard_risk: bool = False
    self_judge: bool = False
    unknown_model_independence: bool = False
    reference_conflict: bool = False
    advisory_risk: bool = False
    judge_disagreement: bool = False
    has_formal_critical_flag: bool = False


class DeterministicEvaluationMetrics(EvaluationModel):
    """Deterministic metrics assembled before any LLM judge call."""

    candidates: CandidateIdentificationMetrics
    structured_fields: StructuredFieldMetrics
    evidence: EvidenceMetrics
    negative_suppression: NegativeSuppressionMetrics
    schema_compliance_rate: float | None = Field(default=None, ge=0, le=1)
    execution_coverage: float = Field(ge=0, le=1)
    deterministic_quality_state: QualityState
