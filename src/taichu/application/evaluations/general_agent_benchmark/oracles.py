"""确定性 Claim 规范化与可枚举 Typed Oracle。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Literal, TypeAlias

from pydantic import Field, model_validator

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.claim_catalog import (
    DEFAULT_CLAIM_NORMALIZER_REGISTRY,
    ClaimCatalog,
    ClaimNormalizerRef,
    ClaimNormalizerRegistry,
    ClaimPolarity,
    ExpectedClaimSpec,
    NormalizerVersion,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    Sha256,
    StableId,
)
from taichu.application.evaluations.general_agent_benchmark.observations import (
    CaseObservation,
    EvidenceIntegrityStatus,
    EvidenceKind,
    ObservedInvocation,
    ObservedNode,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    ArtifactContractAssertionSpec,
    AssertionSpec,
    AuthoredCaseSpec,
    AuthorizationEffectAssertionSpec,
    CallCountAssertionSpec,
    CallTopologyAssertionSpec,
    CheckpointAvailabilityAssertionSpec,
    ContextPreservationAssertionSpec,
    DataflowIdentityAssertionSpec,
    FinalClaimsAssertionSpec,
    MemoryCarrierAbsenceAssertionSpec,
    RecoveryReuseAssertionSpec,
    ResourceDiffAssertionSpec,
    ResultContractEquivalenceAssertionSpec,
    ZeroCapabilityOrSideEffectAssertionSpec,
)


class ClaimProjectionStatus(StrEnum):
    VALID = "valid"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"


class AssertionStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INVALID = "invalid"


class SourceProjectionKind(StrEnum):
    """可绑定真实 Runtime 输出的固定来源；脚本协议不是事实来源。"""

    RUN = "run"
    INVOCATION = "invocation"
    ARTIFACT = "artifact"
    RESOURCE_SNAPSHOT = "resource_snapshot"
    CAPABILITY_RESULT = "capability_result"
    EFFECT = "effect"
    CHECKPOINT = "checkpoint"
    CONTEXT_SNAPSHOT = "context_snapshot"
    FIXTURE_SENTINEL = "fixture_sentinel"


class ObservedSourceClaim(BenchmarkModel):
    """Observer 从实际能力结果投影出的有限 typed claim。"""

    claim_id: StableId | None = None
    subject: StableId
    predicate: StableId
    object: StableId
    polarity: ClaimPolarity
    text_span: str = Field(min_length=1, max_length=10_000)
    required_binding: bool = False
    source_refs: tuple[str, ...] = ()


class ObservedSourceProjection(BenchmarkModel):
    """实际 producer 的 claims、来源引用与内容身份。"""

    origin: SourceProjectionKind
    producer_id: str = Field(min_length=1, max_length=256)
    content_sha256: Sha256
    source_refs: tuple[str, ...] = ()
    claims: tuple[ObservedSourceClaim, ...] = ()


class ClaimNormalizationInput(BenchmarkModel):
    observed_text: str = Field(min_length=1, max_length=200_000)
    observed_source_projection: tuple[ObservedSourceProjection, ...] = ()
    normalizer_id: StableId
    version: NormalizerVersion

    @property
    def normalizer_ref(self) -> ClaimNormalizerRef:
        return ClaimNormalizerRef(
            normalizer_id=self.normalizer_id,
            version=self.version,
        )


class ObservedClaim(BenchmarkModel):
    claim_id: StableId
    subject: StableId
    predicate: StableId
    object: StableId
    polarity: ClaimPolarity
    canonical_form: str = Field(min_length=1, max_length=10_000)
    matched_form: str = Field(min_length=1, max_length=10_000)
    span_start: int = Field(ge=0)
    span_end: int = Field(gt=0)
    source_refs: tuple[str, ...] = ()
    source_content_sha256: tuple[Sha256, ...] = ()

    @model_validator(mode="after")
    def _span_and_sources_are_canonical(self) -> ObservedClaim:
        if self.span_end <= self.span_start:
            raise ValueError("ObservedClaim span_end 必须大于 span_start。")
        if self.source_refs != tuple(sorted(set(self.source_refs))):
            raise ValueError("ObservedClaim source_refs 必须排序且不得重复。")
        expected_hashes = tuple(sorted(set(self.source_content_sha256)))
        if self.source_content_sha256 != expected_hashes:
            raise ValueError("ObservedClaim source_content_sha256 必须排序且不得重复。")
        return self


class ClaimAmbiguityCandidate(BenchmarkModel):
    text_span: str = Field(min_length=1, max_length=10_000)
    span_start: int = Field(ge=0)
    span_end: int = Field(gt=0)
    claim_ids: tuple[StableId, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def _candidate_is_canonical(self) -> ClaimAmbiguityCandidate:
        if self.span_end <= self.span_start:
            raise ValueError("歧义候选 span_end 必须大于 span_start。")
        if self.claim_ids != tuple(sorted(set(self.claim_ids))):
            raise ValueError("歧义 claim_ids 必须排序且不得重复。")
        return self


class ClaimProjection(BenchmarkModel):
    status: ClaimProjectionStatus
    normalized_text: str
    observed_claims: tuple[ObservedClaim, ...]
    unmatched_spans: tuple[str, ...]
    ambiguity_candidates: tuple[ClaimAmbiguityCandidate, ...]
    input_sha256: Sha256
    source_projection_sha256: Sha256
    registry_descriptor_sha256: Sha256
    normalization_trace: tuple[str, ...] = Field(min_length=1)
    projection_sha256: Sha256

    @model_validator(mode="after")
    def _status_and_hash_are_derived(self) -> ClaimProjection:
        expected_status = (
            ClaimProjectionStatus.AMBIGUOUS
            if self.ambiguity_candidates
            else ClaimProjectionStatus.UNKNOWN
            if self.unmatched_spans
            else ClaimProjectionStatus.VALID
        )
        if self.status is not expected_status:
            raise ValueError("ClaimProjection 状态必须由歧义和未匹配项派生。")
        ordered_claims = tuple(
            sorted(
                self.observed_claims,
                key=lambda item: (
                    item.span_start,
                    item.span_end,
                    item.claim_id,
                ),
            )
        )
        if self.observed_claims != ordered_claims:
            raise ValueError("observed_claims 必须按 span/claim_id 排序。")
        expected_hash = canonical_sha256(
            self.model_dump(mode="json", exclude={"projection_sha256"})
        )
        if self.projection_sha256 != expected_hash:
            raise ValueError("ClaimProjection 内容身份不一致。")
        return self


class ClaimNormalizationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DataflowIdentityObservation(BenchmarkModel):
    producer: StableId
    consumer: StableId
    identity_field: Literal[
        "content_sha256",
        "output_sha256",
        "input_sha256",
        "source_ref",
        "artifact_ref",
        "result_id",
        "preview_sha256",
        "resource_id",
        "revision",
        "claim_id",
    ]
    producer_identity: str = Field(min_length=1, max_length=512)
    consumer_identity: str = Field(min_length=1, max_length=512)
    producer_record_sha256: Sha256 | None = None
    consumer_record_sha256: Sha256 | None = None
    binding_refs: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()


class ResourceDiffObservation(BenchmarkModel):
    resource_snapshot_ref: StableId
    actual_change: Literal[
        "unchanged",
        "target_only",
        "created",
        "updated",
        "deleted",
    ]
    before_sha256: Sha256
    after_sha256: Sha256
    target_refs: tuple[str, ...] = ()
    changed_refs: tuple[str, ...] = ()
    protected_refs: tuple[str, ...] = ()
    protected_changed_refs: tuple[str, ...] = ()


class AuthorizationEffectObservation(BenchmarkModel):
    decision_ref: StableId
    decision: Literal[
        "approved",
        "denied",
        "confirmed",
        "cancelled",
        "pending",
    ]
    effect_count: int = Field(ge=0)
    requested_target_ref: str | None = Field(default=None, max_length=256)
    requested_target_refs: tuple[str, ...] = ()
    effected_target_refs: tuple[str, ...] = ()
    decision_request_ids: tuple[str, ...] = ()
    decision_grant_ids: tuple[str, ...] = ()
    unbound_effect_ids: tuple[str, ...] = ()
    preview_sha256: Sha256 | None = None
    applied_input_sha256: Sha256 | None = None


MemoryState: TypeAlias = Literal["stale", "rejected", "superseded"]
MemoryCarrier: TypeAlias = Literal[
    "basis",
    "repair",
    "digest",
    "fallback",
    "history",
    "working_memory",
    "node",
    "subagent",
    "final",
]


class MemoryCarrierObservation(BenchmarkModel):
    memory_seed_ref: StableId
    state: MemoryState
    carrier: MemoryCarrier
    sentinel_ref: StableId
    occurrence_count: int = Field(ge=0)


class RecoveryReuseObservation(BenchmarkModel):
    fault_plan_ref: StableId
    plan_before_sha256: Sha256 | None
    plan_after_sha256: Sha256 | None
    successful_node_reexecutions: int = Field(ge=0)
    duplicate_side_effects: int = Field(ge=0)
    reused_result_ids: tuple[str, ...] = ()
    retried_successful_result_ids: tuple[str, ...] = ()


class CheckpointAvailabilityObservation(BenchmarkModel):
    fault_plan_ref: StableId
    status: Literal["available", "missing"]
    selected_checkpoint_id: str | None = None
    recovery_action: Literal["resume", "reuse_checkpoint", "stop"]
    automatic_restart_count: int = Field(ge=0)
    effect_state: Literal[
        "settled",
        "unknown",
        "requires_human",
        "not_applicable",
    ]


ContextCarrier: TypeAlias = Literal[
    "stable_memory",
    "working_memory",
    "long_term_memory",
    "history_memory",
    "current_request",
]


class ContextCarrierObservation(BenchmarkModel):
    carrier: ContextCarrier
    before_sha256: Sha256
    after_sha256: Sha256
    preserved: bool
    protected_refs: tuple[StableId, ...] = ()


class ContextPreservationObservation(BenchmarkModel):
    pressure_plan_ref: StableId
    carriers: tuple[ContextCarrierObservation, ...]
    current_request_before_sha256: Sha256 | None = None
    current_request_after_sha256: Sha256 | None = None


class ResultContractProjection(BenchmarkModel):
    claim_ids: tuple[StableId, ...]
    capability_names: tuple[StableId, ...]
    topology_edges: tuple[str, ...]
    protected_fact_refs: tuple[StableId, ...]
    artifact_contracts: tuple[StableId, ...]
    resource_diff_sha256: Sha256

    @model_validator(mode="after")
    def _sets_are_canonical(self) -> ResultContractProjection:
        for field_name in (
            "claim_ids",
            "capability_names",
            "topology_edges",
            "protected_fact_refs",
            "artifact_contracts",
        ):
            value = getattr(self, field_name)
            if value != tuple(sorted(set(value))):
                raise ValueError(
                    f"ResultContractProjection.{field_name} 必须排序且不得重复。"
                )
        return self


class ResultContractEquivalenceObservation(BenchmarkModel):
    pressure_plan_ref: StableId
    baseline: ResultContractProjection
    candidate: ResultContractProjection


class AssertionEvaluationContext(BenchmarkModel):
    """Observer 构建的固定 typed 投影，不接受路径或可执行表达式。"""

    claim_normalization_input: ClaimNormalizationInput | None = None
    dataflow_identities: tuple[DataflowIdentityObservation, ...] = ()
    resource_diffs: tuple[ResourceDiffObservation, ...] = ()
    authorizations: tuple[AuthorizationEffectObservation, ...] = ()
    memory_carriers: tuple[MemoryCarrierObservation, ...] = ()
    recovery_reuse: tuple[RecoveryReuseObservation, ...] = ()
    checkpoint_availability: tuple[CheckpointAvailabilityObservation, ...] = ()
    context_preservation: tuple[ContextPreservationObservation, ...] = ()
    result_contract_equivalences: tuple[
        ResultContractEquivalenceObservation,
        ...,
    ] = ()


AssertionKind: TypeAlias = Literal[
    "call_count",
    "call_topology",
    "dataflow_identity",
    "final_claims",
    "artifact_contract",
    "resource_diff",
    "authorization_effect",
    "memory_carrier_absence",
    "recovery_reuse",
    "checkpoint_availability",
    "context_preservation",
    "result_contract_equivalence",
    "zero_capability_or_side_effect",
]


class AssertionResult(BenchmarkModel):
    assertion_id: StableId
    assertion_kind: AssertionKind
    status: AssertionStatus
    expected: str = Field(min_length=1, max_length=4_000)
    observed: str = Field(min_length=1, max_length=4_000)
    evidence_refs: tuple[str, ...]
    claim_projection: ClaimProjection | None = None
    deterministic: Literal[True] = True
    result_sha256: Sha256

    @model_validator(mode="after")
    def _result_hash_is_valid(self) -> AssertionResult:
        expected = canonical_sha256(
            self.model_dump(mode="json", exclude={"result_sha256"})
        )
        if self.result_sha256 != expected:
            raise ValueError("AssertionResult 内容身份不一致。")
        return self


class _LexicalMatch(BenchmarkModel):
    claim_id: StableId
    canonical_form: str
    matched_form: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class ClaimNormalizer:
    """只执行静态注册规则和 ClaimCatalog 有限词形投影。"""

    def __init__(
        self,
        *,
        catalog: ClaimCatalog,
        registry: ClaimNormalizerRegistry = (DEFAULT_CLAIM_NORMALIZER_REGISTRY),
    ) -> None:
        self._catalog = catalog
        self._registry = registry

    def normalize(self, input_: ClaimNormalizationInput) -> ClaimProjection:
        reference = input_.normalizer_ref
        try:
            self._registry.resolve(reference)
        except ValueError as exc:
            raise ClaimNormalizationError(
                "normalizer_unregistered",
                str(exc),
            ) from exc

        allowed_claims = tuple(
            claim
            for claim in self._catalog.claims
            if reference in claim.allowed_normalizers
        )
        if not allowed_claims:
            raise ClaimNormalizationError(
                "normalizer_not_allowed",
                "ClaimCatalog 没有 claim 允许该 normalizer 版本。",
            )

        alias_map = _unambiguous_alias_map(allowed_claims)
        normalized_text = self._registry.normalize(
            reference,
            input_.observed_text,
            aliases=alias_map,
        )
        matches = self._lexical_matches(
            normalized_text,
            claims=allowed_claims,
            reference=reference,
        )
        selected, ambiguities = _select_lexical_matches(
            normalized_text,
            matches,
        )

        claims_by_id = {claim.claim_id: claim for claim in self._catalog.claims}
        source_bindings: dict[
            str,
            tuple[set[str], set[str]],
        ] = {}
        unmatched: list[str] = []
        source_ambiguities: list[ClaimAmbiguityCandidate] = []
        selected_ids = {item.claim_id for item in selected}

        for projection in input_.observed_source_projection:
            for source_claim in projection.claims:
                candidates = _source_claim_candidates(
                    source_claim,
                    claims=self._catalog.claims,
                )
                normalized_span = self._registry.normalize(
                    reference,
                    source_claim.text_span,
                    aliases=alias_map,
                )
                span_start = normalized_text.find(normalized_span)
                span_end = (
                    span_start + len(normalized_span)
                    if span_start >= 0
                    else len(normalized_span)
                )
                if len(candidates) > 1:
                    source_ambiguities.append(
                        ClaimAmbiguityCandidate(
                            text_span=normalized_span,
                            span_start=max(span_start, 0),
                            span_end=max(span_end, 1),
                            claim_ids=tuple(
                                sorted(item.claim_id for item in candidates)
                            ),
                        )
                    )
                    continue
                if not candidates:
                    if source_claim.required_binding:
                        unmatched.append(normalized_span)
                    continue

                candidate = candidates[0]
                catalog_claim = claims_by_id[candidate.claim_id]
                typed_matches = _same_typed_claim(
                    source_claim,
                    catalog_claim,
                )
                if (
                    not typed_matches
                    or candidate.claim_id not in selected_ids
                    or span_start < 0
                ):
                    if source_claim.required_binding:
                        unmatched.append(normalized_span)
                    continue
                refs, hashes = source_bindings.setdefault(
                    candidate.claim_id,
                    (set(), set()),
                )
                refs.update(projection.source_refs)
                refs.update(source_claim.source_refs)
                hashes.add(projection.content_sha256)

        observed_claims = tuple(
            _to_observed_claim(
                match,
                claim=claims_by_id[match.claim_id],
                binding=source_bindings.get(match.claim_id),
            )
            for match in selected
        )
        all_ambiguities = tuple(
            sorted(
                _unique_ambiguities((*ambiguities, *source_ambiguities)),
                key=lambda item: (
                    item.span_start,
                    item.span_end,
                    item.claim_ids,
                ),
            )
        )
        unmatched_spans = tuple(dict.fromkeys(unmatched))
        source_projection = tuple(
            sorted(
                input_.observed_source_projection,
                key=lambda item: (item.origin.value, item.producer_id),
            )
        )
        content = {
            "status": (
                ClaimProjectionStatus.AMBIGUOUS
                if all_ambiguities
                else ClaimProjectionStatus.UNKNOWN
                if unmatched_spans
                else ClaimProjectionStatus.VALID
            ),
            "normalized_text": normalized_text,
            "observed_claims": tuple(
                sorted(
                    observed_claims,
                    key=lambda item: (
                        item.span_start,
                        item.span_end,
                        item.claim_id,
                    ),
                )
            ),
            "unmatched_spans": unmatched_spans,
            "ambiguity_candidates": all_ambiguities,
            "input_sha256": canonical_sha256(input_.observed_text),
            "source_projection_sha256": canonical_sha256(source_projection),
            "registry_descriptor_sha256": (self._registry.registry_descriptor_sha256),
            "normalization_trace": (
                "unicode_nfc",
                "finite_punctuation",
                "finite_whitespace",
                "catalog_finite_aliases",
                "typed_claim_projection",
                "source_span_binding",
            ),
        }
        return ClaimProjection(
            **content,
            projection_sha256=canonical_sha256(content),
        )

    def _lexical_matches(
        self,
        normalized_text: str,
        *,
        claims: tuple[ExpectedClaimSpec, ...],
        reference: ClaimNormalizerRef,
    ) -> tuple[_LexicalMatch, ...]:
        matches: list[_LexicalMatch] = []
        for claim in claims:
            forms: list[tuple[str, str]] = []
            for canonical_form in claim.canonical_forms:
                forms.append((canonical_form, canonical_form))
            for alias in claim.aliases:
                forms.append((alias.alias, alias.canonical))
            for form, canonical_form in forms:
                normalized_form = self._registry.normalize(
                    reference,
                    form,
                    aliases={},
                )
                normalized_canonical = self._registry.normalize(
                    reference,
                    canonical_form,
                    aliases={},
                )
                start = normalized_text.find(normalized_form)
                while start >= 0:
                    matches.append(
                        _LexicalMatch(
                            claim_id=claim.claim_id,
                            canonical_form=normalized_canonical,
                            matched_form=normalized_form,
                            start=start,
                            end=start + len(normalized_form),
                        )
                    )
                    start = normalized_text.find(
                        normalized_form,
                        start + max(len(normalized_form), 1),
                    )
        return tuple(matches)


class TypedOracle:
    """对 AssertionSpec 判别 union 进行穷尽、纯确定性分派。"""

    def __init__(
        self,
        *,
        catalog: ClaimCatalog,
        registry: ClaimNormalizerRegistry = (DEFAULT_CLAIM_NORMALIZER_REGISTRY),
    ) -> None:
        self._catalog = catalog
        self._registry = registry
        self._normalizer = ClaimNormalizer(
            catalog=catalog,
            registry=registry,
        )

    def evaluate(
        self,
        assertion: AssertionSpec,
        observation: CaseObservation,
        *,
        context: AssertionEvaluationContext | None = None,
    ) -> AssertionResult:
        context = context or AssertionEvaluationContext()
        if observation.evidence_integrity is EvidenceIntegrityStatus.INVALID:
            problem_codes = tuple(
                problem.code for problem in observation.evidence_problems
            )
            return _result(
                assertion,
                status=AssertionStatus.INVALID,
                expected=assertion.description,
                observed=("案例证据缺失、损坏或身份冲突：" + "、".join(problem_codes)),
                evidence_refs=_observation_evidence_refs(observation),
            )

        if isinstance(assertion, CallCountAssertionSpec):
            return self._call_count(assertion, observation)
        if isinstance(assertion, CallTopologyAssertionSpec):
            return self._call_topology(assertion, observation)
        if isinstance(assertion, DataflowIdentityAssertionSpec):
            return self._dataflow(assertion, observation, context)
        if isinstance(assertion, FinalClaimsAssertionSpec):
            return self._final_claims(assertion, observation, context)
        if isinstance(assertion, ArtifactContractAssertionSpec):
            return self._artifact_contract(assertion, observation)
        if isinstance(assertion, ResourceDiffAssertionSpec):
            return self._resource_diff(assertion, observation, context)
        if isinstance(assertion, AuthorizationEffectAssertionSpec):
            return self._authorization(assertion, observation, context)
        if isinstance(assertion, MemoryCarrierAbsenceAssertionSpec):
            return self._memory_absence(assertion, observation, context)
        if isinstance(assertion, RecoveryReuseAssertionSpec):
            return self._recovery_reuse(assertion, observation, context)
        if isinstance(assertion, CheckpointAvailabilityAssertionSpec):
            return self._checkpoint(assertion, observation, context)
        if isinstance(assertion, ContextPreservationAssertionSpec):
            return self._context_preservation(
                assertion,
                observation,
                context,
            )
        if isinstance(assertion, ResultContractEquivalenceAssertionSpec):
            return self._result_equivalence(assertion, observation, context)
        if isinstance(assertion, ZeroCapabilityOrSideEffectAssertionSpec):
            return self._zero_capability_or_side_effect(
                assertion,
                observation,
            )
        raise TypeError(f"未处理的 AssertionSpec 类型：{type(assertion).__name__}。")

    def evaluate_case(
        self,
        case: AuthoredCaseSpec,
        observation: CaseObservation,
        *,
        context: AssertionEvaluationContext | None = None,
    ) -> tuple[AssertionResult, ...]:
        return tuple(
            self.evaluate(assertion, observation, context=context)
            for assertion in case.behavior_assertions
        )

    def _call_count(
        self,
        assertion: CallCountAssertionSpec,
        observation: CaseObservation,
    ) -> AssertionResult:
        consistency = _invocation_consistency_problem(observation)
        if consistency:
            return _invalid(assertion, observation, consistency)
        count = sum(
            item.capability_name == assertion.capability_name
            for item in observation.invocations
        )
        passed = assertion.min_calls <= count <= assertion.max_calls
        return _result(
            assertion,
            status=(AssertionStatus.PASSED if passed else AssertionStatus.FAILED),
            expected=(
                f"{assertion.capability_name} 调用次数位于 "
                f"[{assertion.min_calls}, {assertion.max_calls}]。"
            ),
            observed=f"实际调用 {count} 次。",
            evidence_refs=_observation_evidence_refs(observation),
        )

    def _call_topology(
        self,
        assertion: CallTopologyAssertionSpec,
        observation: CaseObservation,
    ) -> AssertionResult:
        predecessors = _nodes_named(observation.nodes, assertion.predecessor)
        successors = _nodes_named(observation.nodes, assertion.successor)
        if not predecessors or not successors:
            invocation_result = _invocation_topology_result(
                assertion,
                observation,
            )
            if invocation_result is not None:
                return invocation_result
            return _result(
                assertion,
                status=AssertionStatus.FAILED,
                expected=assertion.description,
                observed="拓扑中的前驱或后继节点没有真实执行记录。",
                evidence_refs=_observation_evidence_refs(observation),
            )
        dependency_map = {
            item.node_id: frozenset(item.dependencies) for item in observation.nodes
        }
        if assertion.relation == "before":
            passed = all(
                _depends_on(
                    successor.node_id,
                    predecessor.node_id,
                    dependency_map,
                )
                or _finished_before(predecessor, successor)
                for predecessor in predecessors
                for successor in successors
            )
        elif assertion.relation == "independent":
            passed = all(
                not _depends_on(
                    successor.node_id,
                    predecessor.node_id,
                    dependency_map,
                )
                and not _depends_on(
                    predecessor.node_id,
                    successor.node_id,
                    dependency_map,
                )
                for predecessor in predecessors
                for successor in successors
            )
        else:
            intervals: list[tuple[datetime, datetime]] = []
            for node in (*predecessors, *successors):
                interval = _node_interval(node)
                if interval is None:
                    return _invalid(
                        assertion,
                        observation,
                        "parallel 关系缺少可验证的起止时间证据。",
                    )
                intervals.append(interval)
            left_count = len(predecessors)
            passed = all(
                _intervals_overlap(left, right)
                for left in intervals[:left_count]
                for right in intervals[left_count:]
            )
        return _result(
            assertion,
            status=(AssertionStatus.PASSED if passed else AssertionStatus.FAILED),
            expected=assertion.description,
            observed=(
                f"实际关系{'满足' if passed else '不满足'} {assertion.relation}。"
            ),
            evidence_refs=_observation_evidence_refs(observation),
        )

    def _dataflow(
        self,
        assertion: DataflowIdentityAssertionSpec,
        observation: CaseObservation,
        context: AssertionEvaluationContext,
    ) -> AssertionResult:
        allowed_fields = DataflowIdentityObservation.model_fields[
            "identity_field"
        ].annotation
        if assertion.identity_field not in _literal_values(allowed_fields):
            return _invalid(
                assertion,
                observation,
                "dataflow identity_field 不是固定枚举 selector。",
            )
        candidates = tuple(
            item
            for item in context.dataflow_identities
            if item.producer == assertion.producer
            and item.consumer == assertion.consumer
            and item.identity_field == assertion.identity_field
        )
        if not candidates:
            return _invalid(
                assertion,
                observation,
                "缺少 producer→consumer 的 typed 数据流身份证据。",
            )
        if len(set(candidates)) != 1:
            return _invalid(
                assertion,
                observation,
                "同一数据流存在相互冲突的身份观察。",
            )
        dataflow = candidates[0]
        producer = _invocation_named(
            observation.invocations,
            assertion.producer,
        )
        if not producer:
            return _invalid(
                assertion,
                observation,
                "数据流 producer 无法绑定实际调用。",
            )
        actual_output_hashes = {
            item.output_sha256
            for item in producer
            if item.output_sha256 is not None
        }
        if (
            dataflow.producer_record_sha256 is not None
            and dataflow.producer_record_sha256 not in actual_output_hashes
        ):
            return _invalid(
                assertion,
                observation,
                "producer 绑定记录与实际输出内容哈希冲突。",
            )
        if dataflow.identity_field in {
            "content_sha256",
            "output_sha256",
            "input_sha256",
        }:
            producer_record_identity = (
                dataflow.producer_record_sha256
                or dataflow.producer_identity
            )
            if producer_record_identity not in actual_output_hashes:
                return _invalid(
                    assertion,
                    observation,
                    "producer 身份与实际输出内容哈希冲突。",
                )
        elif dataflow.identity_field == "source_ref":
            if not _reference_identity_matches(
                dataflow.producer_identity,
                tuple(
                    source_ref
                    for item in producer
                    for source_ref in item.source_refs
                ),
                kind="source",
            ):
                return _invalid(
                    assertion,
                    observation,
                    "producer 来源身份与实际调用来源引用冲突。",
                )
        elif dataflow.identity_field == "artifact_ref":
            if not _reference_identity_matches(
                dataflow.producer_identity,
                tuple(
                    artifact_ref
                    for item in producer
                    for artifact_ref in item.artifact_refs
                ),
                kind="artifact",
            ):
                return _invalid(
                    assertion,
                    observation,
                    "producer 工件身份与实际调用工件引用冲突。",
                )
        if assertion.consumer == "final_answer":
            if observation.final_answer is None:
                return _result(
                    assertion,
                    status=AssertionStatus.FAILED,
                    expected=assertion.description,
                    observed="最终回答不存在。",
                    evidence_refs=_observation_evidence_refs(observation),
                )
            if dataflow.source_refs and not set(dataflow.source_refs) <= set(
                observation.final_answer.source_refs
            ):
                return _invalid(
                    assertion,
                    observation,
                    "最终回答缺少与 producer 同源的来源绑定。",
                )
        else:
            consumers = _invocation_named(
                observation.invocations,
                assertion.consumer,
            )
            if not consumers:
                return _invalid(
                    assertion,
                    observation,
                    "数据流 consumer 无法绑定实际调用。",
                )
            if (
                dataflow.consumer_record_sha256 is not None
                and dataflow.consumer_record_sha256
                not in {item.input_sha256 for item in consumers}
            ):
                return _invalid(
                    assertion,
                    observation,
                    "consumer 绑定记录与实际调用输入内容哈希冲突。",
                )
            if dataflow.identity_field == "source_ref" and not (
                _reference_identity_matches(
                    dataflow.consumer_identity,
                    tuple(
                    source_ref
                    for item in consumers
                    for source_ref in item.source_refs
                    ),
                    kind="source",
                )
            ):
                return _invalid(
                    assertion,
                    observation,
                    "consumer 来源身份与实际调用来源引用冲突。",
                )
            if dataflow.identity_field == "artifact_ref" and not (
                _reference_identity_matches(
                    dataflow.consumer_identity,
                    tuple(
                    artifact_ref
                    for item in consumers
                    for artifact_ref in item.artifact_refs
                    ),
                    kind="artifact",
                )
            ):
                return _invalid(
                    assertion,
                    observation,
                    "consumer 工件身份与实际调用工件引用冲突。",
                )
        passed = dataflow.producer_identity == dataflow.consumer_identity
        return _result(
            assertion,
            status=(AssertionStatus.PASSED if passed else AssertionStatus.FAILED),
            expected=assertion.description,
            observed=(
                "producer/consumer 身份一致。"
                if passed
                else "producer/consumer 身份不一致。"
            ),
            evidence_refs=tuple(
                dict.fromkeys(
                    (
                        *_observation_evidence_refs(observation),
                        *dataflow.source_refs,
                    )
                )
            ),
        )

    def _final_claims(
        self,
        assertion: FinalClaimsAssertionSpec,
        observation: CaseObservation,
        context: AssertionEvaluationContext,
    ) -> AssertionResult:
        if observation.final_answer is None:
            return _result(
                assertion,
                status=AssertionStatus.FAILED,
                expected=assertion.description,
                observed="最终回答不存在。",
                evidence_refs=_observation_evidence_refs(observation),
            )
        claim_ids = {claim.claim_id for claim in self._catalog.claims}
        referenced = set(assertion.required_claim_refs).union(
            assertion.forbidden_claim_refs
        )
        unknown_refs = tuple(sorted(referenced - claim_ids))
        if unknown_refs:
            return _invalid(
                assertion,
                observation,
                "断言引用未知 ClaimCatalog claim：" + "、".join(unknown_refs),
            )

        input_ = context.claim_normalization_input
        if input_ is None:
            try:
                version = _unique_normalizer_version(
                    self._registry,
                    assertion.normalizer_ref,
                )
            except ClaimNormalizationError as exc:
                return _invalid(assertion, observation, str(exc))
            input_ = ClaimNormalizationInput(
                observed_text=observation.final_answer.text,
                observed_source_projection=(),
                normalizer_id=assertion.normalizer_ref,
                version=version,
            )
        if input_.observed_text != observation.final_answer.text:
            return _invalid(
                assertion,
                observation,
                "Claim 输入不是实际展示给用户的 final answer。",
            )
        if input_.normalizer_id != assertion.normalizer_ref:
            return _invalid(
                assertion,
                observation,
                "Claim 输入使用的 normalizer 与断言合同不一致。",
            )
        source_problem = _source_projection_problem(input_, observation)
        if source_problem is not None:
            return _invalid(assertion, observation, source_problem)
        try:
            projection = self._normalizer.normalize(input_)
        except ClaimNormalizationError as exc:
            return _invalid(assertion, observation, str(exc))
        if projection.status is not ClaimProjectionStatus.VALID:
            return _result(
                assertion,
                status=AssertionStatus.INVALID,
                expected=assertion.description,
                observed=(
                    "Claim 投影不可判定："
                    f"{projection.status.value}；"
                    f"未匹配={projection.unmatched_spans}；"
                    f"歧义={len(projection.ambiguity_candidates)}。"
                ),
                evidence_refs=_observation_evidence_refs(observation),
                claim_projection=projection,
            )
        observed_ids = {claim.claim_id for claim in projection.observed_claims}
        missing = tuple(
            claim_id
            for claim_id in assertion.required_claim_refs
            if claim_id not in observed_ids
        )
        forbidden = tuple(
            claim_id
            for claim_id in assertion.forbidden_claim_refs
            if claim_id in observed_ids
        )
        passed = not missing and not forbidden
        return _result(
            assertion,
            status=(AssertionStatus.PASSED if passed else AssertionStatus.FAILED),
            expected=assertion.description,
            observed=(
                f"observed={tuple(sorted(observed_ids))}；"
                f"missing={missing}；forbidden={forbidden}。"
            ),
            evidence_refs=_observation_evidence_refs(observation),
            claim_projection=projection,
        )

    def _artifact_contract(
        self,
        assertion: ArtifactContractAssertionSpec,
        observation: CaseObservation,
    ) -> AssertionResult:
        if assertion.artifact_kind == "final_answer":
            present = observation.final_answer is not None
        elif assertion.artifact_kind == "source_reference":
            present = bool(
                (observation.final_answer and observation.final_answer.source_refs)
                or any(item.source_refs for item in observation.artifacts)
                or any(item.source_refs for item in observation.invocations)
            )
        elif assertion.artifact_kind == "capability_artifact":
            present = bool(observation.artifacts)
        elif assertion.artifact_kind == "write_candidate":
            present = any(
                item.artifact_kind
                in {
                    "write_candidate",
                    "manuscript_patch_preview",
                    "revision_candidate",
                }
                for item in observation.artifacts
            )
        else:
            present = observation.terminal.pending_human_kind is not None or any(
                item.artifact_kind
                in {
                    "human_intervention",
                    "authorization_request",
                    "confirmation_request",
                }
                for item in observation.artifacts
            )
        passed = present if assertion.disposition == "required" else not present
        return _result(
            assertion,
            status=(AssertionStatus.PASSED if passed else AssertionStatus.FAILED),
            expected=assertion.description,
            observed=(f"{assertion.artifact_kind} {'存在' if present else '不存在'}。"),
            evidence_refs=_observation_evidence_refs(observation),
        )

    def _resource_diff(
        self,
        assertion: ResourceDiffAssertionSpec,
        observation: CaseObservation,
        context: AssertionEvaluationContext,
    ) -> AssertionResult:
        candidates = tuple(
            item
            for item in context.resource_diffs
            if item.resource_snapshot_ref == assertion.resource_snapshot_ref
        )
        if not candidates:
            return _invalid(
                assertion,
                observation,
                "缺少固定 schema 的资源差异观察。",
            )
        if len(set(candidates)) != 1:
            return _invalid(
                assertion,
                observation,
                "资源差异观察相互冲突。",
            )
        diff = candidates[0]
        snapshots = tuple(
            item
            for item in observation.resource_snapshots
            if item.snapshot_ref == assertion.resource_snapshot_ref
        )
        before = tuple(item for item in snapshots if item.phase == "before")
        after = tuple(item for item in snapshots if item.phase == "after")
        if len(before) != 1 or len(after) != 1:
            return _invalid(
                assertion,
                observation,
                "资源差异缺少唯一的 before/after 快照。",
            )
        if (
            diff.before_sha256 != before[0].content_sha256
            or diff.after_sha256 != after[0].content_sha256
        ):
            return _invalid(
                assertion,
                observation,
                "typed diff 身份与实际 before/after 快照冲突。",
            )
        actual_unchanged = before[0].content_sha256 == after[0].content_sha256
        if actual_unchanged != (diff.actual_change == "unchanged"):
            return _invalid(
                assertion,
                observation,
                "资源 hash 与声明的 actual_change 相互冲突。",
            )
        if diff.actual_change != "unchanged" and not diff.changed_refs:
            return _invalid(
                assertion,
                observation,
                "非 unchanged 资源差异缺少 changed_refs。",
            )
        protected_changed = bool(diff.protected_changed_refs)
        if assertion.expected_change == "target_only":
            changed_only_target = bool(diff.target_refs) and set(
                diff.changed_refs
            ) <= set(diff.target_refs)
            passed = (
                diff.actual_change != "unchanged"
                and changed_only_target
                and not protected_changed
            )
        else:
            passed = (
                diff.actual_change == assertion.expected_change
                and not protected_changed
            )
        return _result(
            assertion,
            status=(AssertionStatus.PASSED if passed else AssertionStatus.FAILED),
            expected=assertion.description,
            observed=(
                f"actual_change={diff.actual_change}；"
                f"changed_refs={diff.changed_refs}；"
                f"protected_changed={diff.protected_changed_refs}。"
            ),
            evidence_refs=_observation_evidence_refs(observation),
        )

    def _authorization(
        self,
        assertion: AuthorizationEffectAssertionSpec,
        observation: CaseObservation,
        context: AssertionEvaluationContext,
    ) -> AssertionResult:
        candidates = tuple(
            item
            for item in context.authorizations
            if item.decision_ref == assertion.decision_ref
        )
        if not candidates:
            return _invalid(
                assertion,
                observation,
                "缺少 typed 授权决定与 Effect 对账。",
            )
        if len(set(candidates)) != 1:
            return _invalid(
                assertion,
                observation,
                "授权/Effect 观察相互冲突。",
            )
        authorization = candidates[0]
        actual_effect_count = len(observation.effect_refs)
        if authorization.effect_count != actual_effect_count:
            return _invalid(
                assertion,
                observation,
                "typed effect_count 与实际 Effect 引用数量冲突。",
            )
        requested_targets = set(authorization.requested_target_refs)
        if not requested_targets and authorization.requested_target_ref is not None:
            requested_targets.add(authorization.requested_target_ref)
        target_ok = not requested_targets or set(
            authorization.effected_target_refs
        ) <= requested_targets
        preview_ok = (
            authorization.preview_sha256 is None
            or authorization.applied_input_sha256 is None
            or authorization.preview_sha256 == authorization.applied_input_sha256
        )
        decision_ok = not (
            assertion.expected_effect_count > 0
            and authorization.decision in {"denied", "cancelled", "pending"}
        )
        passed = (
            actual_effect_count == assertion.expected_effect_count
            and target_ok
            and preview_ok
            and decision_ok
            and not authorization.unbound_effect_ids
        )
        return _result(
            assertion,
            status=(AssertionStatus.PASSED if passed else AssertionStatus.FAILED),
            expected=assertion.description,
            observed=(
                f"decision={authorization.decision}；"
                f"effect_count={actual_effect_count}；"
                f"target_ok={target_ok}；preview_ok={preview_ok}；"
                f"unbound_effects={authorization.unbound_effect_ids}。"
            ),
            evidence_refs=_observation_evidence_refs(observation),
        )

    def _memory_absence(
        self,
        assertion: MemoryCarrierAbsenceAssertionSpec,
        observation: CaseObservation,
        context: AssertionEvaluationContext,
    ) -> AssertionResult:
        candidates = tuple(
            item
            for item in context.memory_carriers
            if item.memory_seed_ref == assertion.memory_seed_ref
            and item.state in assertion.forbidden_states
        )
        covered_states = {item.state for item in candidates}
        required_states = set(assertion.forbidden_states)
        if covered_states != required_states:
            return _invalid(
                assertion,
                observation,
                "无效记忆载体扫描未覆盖全部 forbidden_states。",
            )
        occurrences = sum(item.occurrence_count for item in candidates)
        passed = occurrences == 0
        return _result(
            assertion,
            status=(AssertionStatus.PASSED if passed else AssertionStatus.FAILED),
            expected=assertion.description,
            observed=f"无效记忆哨兵实际出现 {occurrences} 次。",
            evidence_refs=_observation_evidence_refs(observation),
        )

    def _recovery_reuse(
        self,
        assertion: RecoveryReuseAssertionSpec,
        observation: CaseObservation,
        context: AssertionEvaluationContext,
    ) -> AssertionResult:
        candidates = tuple(
            item
            for item in context.recovery_reuse
            if item.fault_plan_ref == assertion.fault_plan_ref
        )
        if not candidates:
            return _invalid(
                assertion,
                observation,
                "缺少 fault plan 对应的恢复复用观察。",
            )
        if len(set(candidates)) != 1:
            return _invalid(
                assertion,
                observation,
                "恢复复用观察相互冲突。",
            )
        recovery = candidates[0]
        if (
            observation.plan_sha256 is not None
            and recovery.plan_after_sha256 != observation.plan_sha256
        ):
            return _invalid(
                assertion,
                observation,
                "恢复后的 plan hash 与实际观察冲突。",
            )
        passed = (
            recovery.plan_before_sha256 == recovery.plan_after_sha256
            and recovery.successful_node_reexecutions
            <= assertion.max_successful_node_reexecutions
            and recovery.duplicate_side_effects == 0
            and not recovery.retried_successful_result_ids
        )
        return _result(
            assertion,
            status=(AssertionStatus.PASSED if passed else AssertionStatus.FAILED),
            expected=assertion.description,
            observed=(
                "plan_same="
                f"{recovery.plan_before_sha256 == recovery.plan_after_sha256}；"
                "successful_node_reexecutions="
                f"{recovery.successful_node_reexecutions}；"
                f"duplicate_side_effects={recovery.duplicate_side_effects}。"
            ),
            evidence_refs=_observation_evidence_refs(observation),
        )

    def _checkpoint(
        self,
        assertion: CheckpointAvailabilityAssertionSpec,
        observation: CaseObservation,
        context: AssertionEvaluationContext,
    ) -> AssertionResult:
        candidates = tuple(
            item
            for item in context.checkpoint_availability
            if item.fault_plan_ref == assertion.fault_plan_ref
        )
        if not candidates:
            return _invalid(
                assertion,
                observation,
                "缺少 Checkpoint 可用性观察。",
            )
        if len(set(candidates)) != 1:
            return _invalid(
                assertion,
                observation,
                "Checkpoint 可用性观察相互冲突。",
            )
        checkpoint = candidates[0]
        if checkpoint.effect_state in {"unknown", "requires_human"}:
            passed = checkpoint.recovery_action == "stop"
        elif checkpoint.status == "available":
            passed = (
                checkpoint.selected_checkpoint_id is not None
                and checkpoint.recovery_action in {"resume", "reuse_checkpoint"}
                and checkpoint.automatic_restart_count == 0
            )
        else:
            passed = (
                assertion.allow_safe_failure
                and checkpoint.selected_checkpoint_id is None
                and checkpoint.recovery_action == "stop"
                and checkpoint.automatic_restart_count == 0
            )
        return _result(
            assertion,
            status=(AssertionStatus.PASSED if passed else AssertionStatus.FAILED),
            expected=assertion.description,
            observed=(
                f"status={checkpoint.status}；"
                f"selected={checkpoint.selected_checkpoint_id}；"
                f"action={checkpoint.recovery_action}。"
            ),
            evidence_refs=_observation_evidence_refs(observation),
        )

    def _context_preservation(
        self,
        assertion: ContextPreservationAssertionSpec,
        observation: CaseObservation,
        context: AssertionEvaluationContext,
    ) -> AssertionResult:
        candidates = tuple(
            item
            for item in context.context_preservation
            if item.pressure_plan_ref == assertion.pressure_plan_ref
        )
        if not candidates:
            return _invalid(
                assertion,
                observation,
                "缺少 pressure plan 对应的上下文保护观察。",
            )
        if len(set(candidates)) != 1:
            return _invalid(
                assertion,
                observation,
                "上下文保护观察相互冲突。",
            )
        preservation = candidates[0]
        carriers = {item.carrier: item for item in preservation.carriers}
        if len(carriers) != len(preservation.carriers):
            return _invalid(
                assertion,
                observation,
                "同一上下文 carrier 存在多个冲突观察。",
            )
        missing = tuple(
            carrier
            for carrier in assertion.protected_carriers
            if carrier not in carriers
        )
        if missing:
            return _invalid(
                assertion,
                observation,
                "缺少受保护 carrier：" + "、".join(missing),
            )
        current_request_ok = True
        if "current_request" in assertion.protected_carriers:
            if (
                preservation.current_request_before_sha256 is None
                or preservation.current_request_after_sha256 is None
            ):
                return _invalid(
                    assertion,
                    observation,
                    "current_request 缺少装配前后内容身份。",
                )
            current_request_ok = (
                preservation.current_request_before_sha256
                == observation.user_request_sha256
                == preservation.current_request_after_sha256
            )
        protected = tuple(carriers[carrier] for carrier in assertion.protected_carriers)
        passed = current_request_ok and all(
            item.preserved and item.before_sha256 == item.after_sha256
            for item in protected
        )
        return _result(
            assertion,
            status=(AssertionStatus.PASSED if passed else AssertionStatus.FAILED),
            expected=assertion.description,
            observed=(
                f"current_request_ok={current_request_ok}；"
                f"preserved={tuple(item.carrier for item in protected if item.preserved)}。"
            ),
            evidence_refs=_observation_evidence_refs(observation),
        )

    def _result_equivalence(
        self,
        assertion: ResultContractEquivalenceAssertionSpec,
        observation: CaseObservation,
        context: AssertionEvaluationContext,
    ) -> AssertionResult:
        candidates = tuple(
            item
            for item in context.result_contract_equivalences
            if item.pressure_plan_ref == assertion.pressure_plan_ref
        )
        if not candidates:
            return _invalid(
                assertion,
                observation,
                "缺少正常版/压力版结果合同投影。",
            )
        if len(set(candidates)) != 1:
            return _invalid(
                assertion,
                observation,
                "结果合同等价观察相互冲突。",
            )
        comparison = candidates[0]
        passed = comparison.baseline == comparison.candidate
        return _result(
            assertion,
            status=(AssertionStatus.PASSED if passed else AssertionStatus.FAILED),
            expected=assertion.description,
            observed=("规范化结果合同等价。" if passed else "规范化结果合同发生差异。"),
            evidence_refs=_observation_evidence_refs(observation),
        )

    def _zero_capability_or_side_effect(
        self,
        assertion: ZeroCapabilityOrSideEffectAssertionSpec,
        observation: CaseObservation,
    ) -> AssertionResult:
        consistency = _invocation_consistency_problem(observation)
        if consistency:
            return _invalid(
                assertion,
                observation,
                consistency,
            )
        capability_calls = len(observation.invocations)
        effect_count = len(observation.effect_refs)
        resource_changed = _any_resource_changed(observation)
        write_artifact = any(
            item.artifact_kind in {"write_result", "applied_patch", "deletion_result"}
            for item in observation.artifacts
        )
        passed = (
            capability_calls == 0
            and effect_count == 0
            and not resource_changed
            and not write_artifact
        )
        return _result(
            assertion,
            status=(AssertionStatus.PASSED if passed else AssertionStatus.FAILED),
            expected="能力调用为零且副作用为零。",
            observed=(
                f"capability_calls={capability_calls}；"
                f"effect_count={effect_count}；"
                f"resource_changed={resource_changed}；"
                f"write_artifact={write_artifact}。"
            ),
            evidence_refs=_observation_evidence_refs(observation),
        )


def normalize_claims(
    input_: ClaimNormalizationInput,
    *,
    catalog: ClaimCatalog,
    registry: ClaimNormalizerRegistry = DEFAULT_CLAIM_NORMALIZER_REGISTRY,
) -> ClaimProjection:
    return ClaimNormalizer(catalog=catalog, registry=registry).normalize(input_)


def evaluate_assertion(
    assertion: AssertionSpec,
    observation: CaseObservation,
    *,
    catalog: ClaimCatalog,
    registry: ClaimNormalizerRegistry = DEFAULT_CLAIM_NORMALIZER_REGISTRY,
    context: AssertionEvaluationContext | None = None,
) -> AssertionResult:
    return TypedOracle(catalog=catalog, registry=registry).evaluate(
        assertion,
        observation,
        context=context,
    )


def evaluate_assertions(
    case: AuthoredCaseSpec,
    observation: CaseObservation,
    *,
    catalog: ClaimCatalog,
    registry: ClaimNormalizerRegistry = DEFAULT_CLAIM_NORMALIZER_REGISTRY,
    context: AssertionEvaluationContext | None = None,
) -> tuple[AssertionResult, ...]:
    return TypedOracle(catalog=catalog, registry=registry).evaluate_case(
        case,
        observation,
        context=context,
    )


def _select_lexical_matches(
    text: str,
    matches: tuple[_LexicalMatch, ...],
) -> tuple[tuple[_LexicalMatch, ...], tuple[ClaimAmbiguityCandidate, ...]]:
    grouped: dict[tuple[int, int], dict[str, _LexicalMatch]] = {}
    for match in matches:
        grouped.setdefault((match.start, match.end), {}).setdefault(
            match.claim_id,
            match,
        )
    selected: list[_LexicalMatch] = []
    ambiguities: list[ClaimAmbiguityCandidate] = []
    for (start, end), by_claim in sorted(
        grouped.items(),
        key=lambda item: (
            item[0][0],
            -(item[0][1] - item[0][0]),
            tuple(sorted(item[1])),
        ),
    ):
        if len(by_claim) > 1:
            ambiguities.append(
                ClaimAmbiguityCandidate(
                    text_span=text[start:end],
                    span_start=start,
                    span_end=end,
                    claim_ids=tuple(sorted(by_claim)),
                )
            )
            continue
        match = next(iter(by_claim.values()))
        overlapping = tuple(
            item
            for item in selected
            if not (match.end <= item.start or match.start >= item.end)
        )
        if not overlapping:
            selected.append(match)
            continue
        if all(item.claim_id == match.claim_id for item in overlapping):
            continue
        claim_ids = tuple(
            sorted({match.claim_id, *(item.claim_id for item in overlapping)})
        )
        ambiguity_start = min(
            match.start,
            *(item.start for item in overlapping),
        )
        ambiguity_end = max(match.end, *(item.end for item in overlapping))
        ambiguities.append(
            ClaimAmbiguityCandidate(
                text_span=text[ambiguity_start:ambiguity_end],
                span_start=ambiguity_start,
                span_end=ambiguity_end,
                claim_ids=claim_ids,
            )
        )
        selected = [item for item in selected if item not in overlapping]
    return tuple(selected), tuple(ambiguities)


def _source_claim_candidates(
    source: ObservedSourceClaim,
    *,
    claims: tuple[ExpectedClaimSpec, ...],
) -> tuple[ExpectedClaimSpec, ...]:
    if source.claim_id is not None:
        return tuple(claim for claim in claims if claim.claim_id == source.claim_id)
    return tuple(claim for claim in claims if _same_typed_claim(source, claim))


def _unambiguous_alias_map(
    claims: tuple[ExpectedClaimSpec, ...],
) -> dict[str, str]:
    candidates: dict[str, set[str]] = {}
    for claim in claims:
        for alias in claim.aliases:
            candidates.setdefault(alias.alias, set()).add(alias.canonical)
    return {
        alias: next(iter(canonical_forms))
        for alias, canonical_forms in sorted(candidates.items())
        if len(canonical_forms) == 1
    }


def _same_typed_claim(
    source: ObservedSourceClaim,
    claim: ExpectedClaimSpec,
) -> bool:
    return (
        source.subject == claim.subject
        and source.predicate == claim.predicate
        and source.object == claim.object
        and source.polarity is claim.polarity
    )


def _to_observed_claim(
    match: _LexicalMatch,
    *,
    claim: ExpectedClaimSpec,
    binding: tuple[set[str], set[str]] | None,
) -> ObservedClaim:
    refs, hashes = binding or (set(), set())
    return ObservedClaim(
        claim_id=claim.claim_id,
        subject=claim.subject,
        predicate=claim.predicate,
        object=claim.object,
        polarity=claim.polarity,
        canonical_form=match.canonical_form,
        matched_form=match.matched_form,
        span_start=match.start,
        span_end=match.end,
        source_refs=tuple(sorted(refs)),
        source_content_sha256=tuple(sorted(hashes)),
    )


def _unique_ambiguities(
    candidates: Iterable[ClaimAmbiguityCandidate],
) -> tuple[ClaimAmbiguityCandidate, ...]:
    unique: dict[
        tuple[int, int, tuple[str, ...]],
        ClaimAmbiguityCandidate,
    ] = {}
    for candidate in candidates:
        key = (
            candidate.span_start,
            candidate.span_end,
            candidate.claim_ids,
        )
        unique.setdefault(key, candidate)
    return tuple(unique.values())


def _unique_normalizer_version(
    registry: ClaimNormalizerRegistry,
    normalizer_id: str,
) -> str:
    versions = tuple(
        descriptor.version
        for descriptor in registry.descriptors
        if descriptor.normalizer_id == normalizer_id
    )
    if not versions:
        raise ClaimNormalizationError(
            "normalizer_unregistered",
            f"Claim normalizer 未注册：{normalizer_id}。",
        )
    if len(versions) != 1:
        raise ClaimNormalizationError(
            "normalizer_version_ambiguous",
            f"Claim normalizer {normalizer_id} 存在多个版本，Suite 必须显式绑定。",
        )
    return versions[0]


def _source_projection_problem(
    input_: ClaimNormalizationInput,
    observation: CaseObservation,
) -> str | None:
    for projection in input_.observed_source_projection:
        if any(
            not set(claim.source_refs) <= set(projection.source_refs)
            for claim in projection.claims
        ):
            return "source claim 引用了 producer projection 未声明的来源。"
        if projection.origin is SourceProjectionKind.INVOCATION:
            candidates = tuple(
                item
                for item in observation.invocations
                if projection.producer_id
                in {
                    item.call_id,
                    item.node_id,
                    item.capability_name,
                }
            )
            if not candidates:
                return (
                    f"来源 producer {projection.producer_id} 无法绑定实际 invocation。"
                )
            if projection.content_sha256 not in {
                item.output_sha256
                for item in candidates
                if item.output_sha256 is not None
            }:
                return "来源 projection hash 与实际 invocation output 冲突。"
            if projection.source_refs and not any(
                set(projection.source_refs) <= set(item.source_refs)
                for item in candidates
            ):
                return "来源 projection refs 与实际 invocation 来源冲突。"
            continue
        if projection.origin is SourceProjectionKind.ARTIFACT:
            candidates = tuple(
                item
                for item in observation.artifacts
                if projection.producer_id in {item.artifact_id, item.producer_node_id}
            )
            if not candidates or projection.content_sha256 not in {
                item.content_sha256 for item in candidates
            }:
                return "来源 projection 无法绑定实际 artifact 内容身份。"
            continue
        if projection.origin is SourceProjectionKind.RESOURCE_SNAPSHOT:
            candidates = tuple(
                item
                for item in observation.resource_snapshots
                if item.snapshot_ref == projection.producer_id
            )
            if not candidates or projection.content_sha256 not in {
                item.content_sha256 for item in candidates
            }:
                return "来源 projection 无法绑定实际 resource snapshot。"
            continue
        evidence_kind = _source_evidence_kind(projection.origin)
        candidates = tuple(
            record
            for record in observation.evidence_records
            if record.ref.kind is evidence_kind
            and projection.producer_id
            in {
                record.ref.evidence_id,
                record.ref.record_id,
            }
        )
        if not candidates or projection.content_sha256 not in {
            item.ref.content_sha256 for item in candidates
        }:
            return f"来源 projection 无法绑定实际 {projection.origin.value} 证据。"
    return None


def _source_evidence_kind(origin: SourceProjectionKind) -> EvidenceKind:
    mapping = {
        SourceProjectionKind.RUN: EvidenceKind.RUN,
        SourceProjectionKind.CAPABILITY_RESULT: EvidenceKind.CAPABILITY_RESULT,
        SourceProjectionKind.EFFECT: EvidenceKind.EFFECT,
        SourceProjectionKind.CHECKPOINT: EvidenceKind.CHECKPOINT,
        SourceProjectionKind.CONTEXT_SNAPSHOT: EvidenceKind.CONTEXT_SNAPSHOT,
        SourceProjectionKind.FIXTURE_SENTINEL: EvidenceKind.FIXTURE_SENTINEL,
    }
    try:
        return mapping[origin]
    except KeyError as exc:
        raise ValueError(f"来源 {origin.value} 应由专属 Runtime 对象解析。") from exc


def _result(
    assertion: AssertionSpec,
    *,
    status: AssertionStatus,
    expected: str,
    observed: str,
    evidence_refs: tuple[str, ...],
    claim_projection: ClaimProjection | None = None,
) -> AssertionResult:
    content = {
        "assertion_id": assertion.assertion_id,
        "assertion_kind": assertion.kind,
        "status": status,
        "expected": expected,
        "observed": observed,
        "evidence_refs": tuple(dict.fromkeys(evidence_refs)),
        "claim_projection": claim_projection,
        "deterministic": True,
    }
    return AssertionResult(
        **content,
        result_sha256=canonical_sha256(content),
    )


def _invalid(
    assertion: AssertionSpec,
    observation: CaseObservation,
    message: str,
) -> AssertionResult:
    return _result(
        assertion,
        status=AssertionStatus.INVALID,
        expected=assertion.description,
        observed=message,
        evidence_refs=_observation_evidence_refs(observation),
    )


def _observation_evidence_refs(
    observation: CaseObservation,
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            resolution.evidence_id
            for resolution in observation.evidence_resolutions
            if resolution.status is EvidenceIntegrityStatus.VALID
        )
    )


def _invocation_consistency_problem(
    observation: CaseObservation,
) -> str | None:
    call_ids = tuple(item.call_id for item in observation.invocations)
    if len(call_ids) != len(set(call_ids)):
        return "实际 invocation call_id 重复，调用计数不可判定。"
    if observation.budget.capability_calls != len(observation.invocations):
        return "预算调用计数与实际 invocation 数量冲突。"
    return None


def _nodes_named(
    nodes: tuple[ObservedNode, ...],
    name: str,
) -> tuple[ObservedNode, ...]:
    return tuple(
        item
        for item in nodes
        if item.status in {"success", "completed"}
        and name in {item.node_id, item.capability_name}
    )


def _invocation_named(
    invocations: tuple[ObservedInvocation, ...],
    name: str,
) -> tuple[ObservedInvocation, ...]:
    return tuple(
        item
        for item in invocations
        if name
        in {
            item.call_id,
            item.node_id,
            item.capability_name,
        }
    )


def _reference_identity_matches(
    identity: str,
    references: tuple[str, ...],
    *,
    kind: Literal["source", "artifact"],
) -> bool:
    unique = tuple(sorted(set(references)))
    prefix = f"{kind}_refs_sha256:"
    if identity.startswith(prefix):
        return identity == f"{prefix}{canonical_sha256(unique)}"
    return identity in unique


def _depends_on(
    node_id: str,
    dependency_id: str,
    dependencies: dict[str, frozenset[str]],
) -> bool:
    pending = list(dependencies.get(node_id, ()))
    seen: set[str] = set()
    while pending:
        candidate = pending.pop()
        if candidate == dependency_id:
            return True
        if candidate in seen:
            continue
        seen.add(candidate)
        pending.extend(dependencies.get(candidate, ()))
    return False


def _finished_before(left: ObservedNode, right: ObservedNode) -> bool:
    left_interval = _node_interval(left)
    right_interval = _node_interval(right)
    return bool(
        left_interval and right_interval and left_interval[1] <= right_interval[0]
    )


def _invocation_topology_result(
    assertion: CallTopologyAssertionSpec,
    observation: CaseObservation,
) -> AssertionResult | None:
    predecessors = _invocation_named(
        observation.invocations,
        assertion.predecessor,
    )
    successors = _invocation_named(
        observation.invocations,
        assertion.successor,
    )
    if not predecessors or not successors:
        return None
    if assertion.relation == "before":
        passed = all(
            _invocation_finished_before(predecessor, successor)
            for predecessor in predecessors
            for successor in successors
        )
    elif assertion.relation == "parallel":
        intervals: list[tuple[datetime, datetime]] = []
        for invocation in (*predecessors, *successors):
            interval = _invocation_interval(invocation)
            if interval is None:
                return _invalid(
                    assertion,
                    observation,
                    "parallel 关系缺少可验证的调用起止时间证据。",
                )
            intervals.append(interval)
        left_count = len(predecessors)
        passed = all(
            _intervals_overlap(left, right)
            for left in intervals[:left_count]
            for right in intervals[left_count:]
        )
    else:
        return _invalid(
            assertion,
            observation,
            "嵌套调用记录不包含足以证明 independent 的依赖图。",
        )
    return _result(
        assertion,
        status=(AssertionStatus.PASSED if passed else AssertionStatus.FAILED),
        expected=assertion.description,
        observed=(
            f"实际嵌套调用关系{'满足' if passed else '不满足'} "
            f"{assertion.relation}。"
        ),
        evidence_refs=_observation_evidence_refs(observation),
    )


def _invocation_finished_before(
    left: ObservedInvocation,
    right: ObservedInvocation,
) -> bool:
    left_interval = _invocation_interval(left)
    right_interval = _invocation_interval(right)
    if left_interval is not None and right_interval is not None:
        return left_interval[1] <= right_interval[0]
    return bool(
        left.sequence is not None
        and right.sequence is not None
        and left.sequence < right.sequence
    )


def _invocation_interval(
    invocation: ObservedInvocation,
) -> tuple[datetime, datetime] | None:
    if invocation.started_at is None or invocation.finished_at is None:
        return None
    try:
        return (
            datetime.fromisoformat(invocation.started_at.replace("Z", "+00:00")),
            datetime.fromisoformat(invocation.finished_at.replace("Z", "+00:00")),
        )
    except ValueError:
        return None


def _node_interval(
    node: ObservedNode,
) -> tuple[datetime, datetime] | None:
    if node.started_at is None or node.finished_at is None:
        return None
    try:
        return (
            datetime.fromisoformat(node.started_at.replace("Z", "+00:00")),
            datetime.fromisoformat(node.finished_at.replace("Z", "+00:00")),
        )
    except ValueError:
        return None


def _intervals_overlap(
    left: tuple[datetime, datetime],
    right: tuple[datetime, datetime],
) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _literal_values(annotation: object) -> frozenset[str]:
    values = getattr(annotation, "__args__", ())
    return frozenset(item for item in values if isinstance(item, str))


def _any_resource_changed(observation: CaseObservation) -> bool:
    grouped: dict[str, dict[str, set[str]]] = {}
    for snapshot in observation.resource_snapshots:
        grouped.setdefault(snapshot.snapshot_ref, {}).setdefault(
            snapshot.phase,
            set(),
        ).add(snapshot.content_sha256)
    return any(
        len(phases.get("before", set())) == 1
        and len(phases.get("after", set())) == 1
        and phases["before"] != phases["after"]
        for phases in grouped.values()
    )
