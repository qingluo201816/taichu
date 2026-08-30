"""固定套件、轨道、案例、能力目录与预算的不可变合同。"""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)

StableId: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]{2,63}$"),
]
Sha256: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^[a-f0-9]{64}$"),
]
FixtureSnapshotId: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^fixture_[a-f0-9]{64}$"),
]
ErrorCode: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{2,127}$"),
]


class BenchmarkModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CapabilityKind(StrEnum):
    TOOL = "tool"
    SUBAGENT = "subagent"


class TrackKind(StrEnum):
    SYNTHETIC = "synthetic"
    LIVE_PROVIDER = "live_provider"


class CaseCategory(StrEnum):
    FACT_QUESTION = "fact_question"
    ANALYSIS = "analysis"
    PLANNING = "planning"
    DRAFTING = "drafting"
    REVISION = "revision"
    REVIEW = "review"
    AUTHORIZATION = "authorization"
    MEMORY = "memory"
    RECOVERY = "recovery"


class PathKind(StrEnum):
    DIRECT_ANSWER = "direct_answer"
    SINGLE_CAPABILITY = "single_capability"
    SUBAGENT = "subagent"
    MULTI_STEP = "multi_step"


class ValueAvailability(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    NOT_SUPPORTED = "not_supported"
    REDACTED = "redacted"
    ERROR = "error"


class FixtureRef(BenchmarkModel):
    fixture_id: StableId
    snapshot_id: FixtureSnapshotId


class FixtureEntry(BenchmarkModel):
    path: str = Field(min_length=1)
    kind: Literal["file"]
    size_bytes: int = Field(ge=0)
    sha256: Sha256

    @field_validator("path")
    @classmethod
    def _path_is_relative_and_posix(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value:
            raise ValueError("夹具清单路径必须是无 .. 的相对 POSIX 路径。")
        return value


class FixtureSnapshotSpec(BenchmarkModel):
    fixture_id: StableId
    schema_: Literal["taichu.general_agent_benchmark.fixture@1"] = Field(alias="schema")
    manifest_entries: tuple[FixtureEntry, ...] = Field(min_length=1)
    manuscript_root: str
    knowledge_seed: str
    conversation_seed: str
    runtime_memory_seed: str
    external_source_manifest: str
    snapshot_id: FixtureSnapshotId

    @field_validator("manifest_entries")
    @classmethod
    def _entries_are_sorted_and_unique(
        cls,
        value: tuple[FixtureEntry, ...],
    ) -> tuple[FixtureEntry, ...]:
        paths = [item.path for item in value]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError("夹具清单必须按路径排序且不得重复。")
        return value


class CapabilityDescriptor(BenchmarkModel):
    capability_id: StableId
    kind: CapabilityKind
    manifest_identity: str = Field(min_length=1, max_length=500)
    handler_identity: str = Field(min_length=1, max_length=500)


class SubagentToolDependency(BenchmarkModel):
    subagent_id: StableId
    tool_id: StableId


class CapabilityCatalogSnapshot(BenchmarkModel):
    tools: tuple[CapabilityDescriptor, ...]
    subagents: tuple[CapabilityDescriptor, ...]
    registration_dependencies: tuple[SubagentToolDependency, ...]
    canonical_hash: Sha256
    discovered_at: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_catalog(self) -> CapabilityCatalogSnapshot:
        descriptors = self.tools + self.subagents
        ids = [item.capability_id for item in descriptors]
        if len(ids) != len(set(ids)):
            raise ValueError("能力目录中的 capability_id 必须唯一。")
        if any(item.kind is not CapabilityKind.TOOL for item in self.tools):
            raise ValueError("tools 只能包含 type=tool 的能力。")
        if any(item.kind is not CapabilityKind.SUBAGENT for item in self.subagents):
            raise ValueError("subagents 只能包含 type=subagent 的能力。")
        tool_ids = {item.capability_id for item in self.tools}
        subagent_ids = {item.capability_id for item in self.subagents}
        for dependency in self.registration_dependencies:
            if dependency.subagent_id not in subagent_ids:
                raise ValueError(f"未知 Subagent 注册依赖：{dependency.subagent_id}。")
            if dependency.tool_id not in tool_ids:
                raise ValueError(f"未知 Tool 注册依赖：{dependency.tool_id}。")
        dependency_keys = {
            (item.subagent_id, item.tool_id) for item in self.registration_dependencies
        }
        if len(dependency_keys) != len(self.registration_dependencies):
            raise ValueError("Subagent→Tool 注册依赖不得重复。")
        return self

    @classmethod
    def create(
        cls,
        *,
        tools: tuple[CapabilityDescriptor, ...],
        subagents: tuple[CapabilityDescriptor, ...],
        registration_dependencies: tuple[SubagentToolDependency, ...],
        discovered_at: str,
    ) -> CapabilityCatalogSnapshot:
        payload = {
            "tools": tools,
            "subagents": subagents,
            "registration_dependencies": registration_dependencies,
        }
        return cls(
            tools=tools,
            subagents=subagents,
            registration_dependencies=registration_dependencies,
            canonical_hash=canonical_sha256(payload),
            discovered_at=discovered_at,
        )


class ResourceBudget(BenchmarkModel):
    max_node_executions: int = Field(gt=0)
    max_replans: int = Field(ge=0)
    max_capability_calls: int = Field(ge=0)
    max_model_calls: int = Field(gt=0)
    max_total_tokens: int = Field(gt=0)
    max_runtime_ms: int = Field(gt=0)


class BudgetObservation(BenchmarkModel):
    limit: int = Field(ge=0)
    actual: int | None = Field(default=None, ge=0)
    availability: ValueAvailability
    within_limit: bool | None
    evidence_refs: tuple[str, ...]

    @model_validator(mode="after")
    def _validate_availability(self) -> BudgetObservation:
        if self.availability is ValueAvailability.AVAILABLE:
            if self.actual is None or self.within_limit is None:
                raise ValueError("可用预算观察必须包含 actual 与 within_limit。")
            if self.within_limit != (self.actual <= self.limit):
                raise ValueError("within_limit 必须由 actual 与 limit 唯一推导。")
        elif self.actual is not None or self.within_limit is not None:
            raise ValueError("不可用预算观察不得伪造 actual 或 within_limit。")
        return self


class SyntheticTrackSpec(BenchmarkModel):
    kind: Literal[TrackKind.SYNTHETIC] = TrackKind.SYNTHETIC
    rule_set_id: StableId
    gateway_identity: Literal["synthetic"]


class DecodeConstraints(BenchmarkModel):
    temperature: float = Field(ge=0, le=2)
    max_output_tokens: int = Field(gt=0)


class LiveProviderTrackSpec(BenchmarkModel):
    kind: Literal[TrackKind.LIVE_PROVIDER] = TrackKind.LIVE_PROVIDER
    provider_selection: Literal["explicit"] = "explicit"
    allowed_model_refs: tuple[StableId, ...] = Field(min_length=1)
    decode_constraints: DecodeConstraints


TrackSpec: TypeAlias = Annotated[
    SyntheticTrackSpec | LiveProviderTrackSpec,
    Field(discriminator="kind"),
]


class CaseSpec(BenchmarkModel):
    case_id: StableId
    name: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=1_000)
    category: CaseCategory
    tags: frozenset[str]
    applicable_tracks: frozenset[TrackKind] = Field(min_length=1)
    path_kind: PathKind
    targets: tuple[str, ...] = Field(min_length=1)
    user_request: str = Field(min_length=1, max_length=100_000)
    fixture_snapshot_id: FixtureSnapshotId
    required_capabilities: frozenset[StableId]
    allowed_capabilities: frozenset[StableId]
    forbidden_capabilities: frozenset[StableId]
    budgets: ResourceBudget

    @model_validator(mode="after")
    def _validate_capability_sets(self) -> CaseSpec:
        if not self.required_capabilities <= self.allowed_capabilities:
            raise ValueError("required 必须是 allowed 的子集。")
        if self.allowed_capabilities & self.forbidden_capabilities:
            raise ValueError("allowed 与 forbidden 不得相交。")
        if self.required_capabilities & self.forbidden_capabilities:
            raise ValueError("required 与 forbidden 不得相交。")
        return self

    def validate_capabilities(
        self,
        catalog: CapabilityCatalogSnapshot,
    ) -> None:
        known = {item.capability_id for item in catalog.tools + catalog.subagents}
        unknown = sorted(
            (
                self.required_capabilities
                | self.allowed_capabilities
                | self.forbidden_capabilities
            )
            - known
        )
        if unknown:
            raise ValueError(f"未知能力引用：{', '.join(unknown)}。")


class ArtifactDisposition(StrEnum):
    REQUIRED = "required"
    FORBIDDEN = "forbidden"
    NOT_APPLICABLE = "not_applicable"


class ArtifactType(StrEnum):
    FINAL_ANSWER = "final_answer"
    SOURCE_REFERENCE = "source_reference"
    CAPABILITY_ARTIFACT = "capability_artifact"
    WRITE_CANDIDATE = "write_candidate"
    HUMAN_INTERVENTION = "human_intervention"


class ArtifactIdentityRule(BenchmarkModel):
    field: StableId
    required: bool


class ExpectedArtifactBase(BenchmarkModel):
    artifact_id: StableId
    artifact_type: ArtifactType
    disposition: ArtifactDisposition
    identity_rules: tuple[ArtifactIdentityRule, ...] = Field(min_length=1)
    verifier_instance_ids: tuple[StableId, ...]

    @field_validator("verifier_instance_ids")
    @classmethod
    def _verifier_ids_are_unique(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("verifier_instance_ids 不得重复。")
        return value


class FinalAnswerArtifactSpec(ExpectedArtifactBase):
    artifact_type: Literal[ArtifactType.FINAL_ANSWER] = ArtifactType.FINAL_ANSWER
    answer_contract: str = Field(min_length=1, max_length=2_000)
    allowed_languages: frozenset[str] = Field(min_length=1)
    exact_sha256: Sha256 | None = None
    required_claim_ids: tuple[StableId, ...]
    forbidden_claim_ids: tuple[StableId, ...]


class SourceReferenceArtifactSpec(ExpectedArtifactBase):
    artifact_type: Literal[ArtifactType.SOURCE_REFERENCE] = (
        ArtifactType.SOURCE_REFERENCE
    )
    allowed_fixture_source_ids: frozenset[StableId] = Field(min_length=1)
    must_resolve: bool
    min_count: int = Field(ge=0)
    max_count: int = Field(ge=0)
    source_kinds: frozenset[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_count_range(self) -> SourceReferenceArtifactSpec:
        if self.max_count < self.min_count:
            raise ValueError("来源引用 max_count 不能小于 min_count。")
        return self


class CapabilityArtifactSpec(ExpectedArtifactBase):
    artifact_type: Literal[ArtifactType.CAPABILITY_ARTIFACT] = (
        ArtifactType.CAPABILITY_ARTIFACT
    )
    capability_name: StableId
    capability_kind: CapabilityKind
    artifact_kind: StableId
    producer_node_ids: tuple[StableId, ...] = ()
    required_path: tuple[StableId, ...] = ()


class WriteCandidateArtifactSpec(ExpectedArtifactBase):
    artifact_type: Literal[ArtifactType.WRITE_CANDIDATE] = ArtifactType.WRITE_CANDIDATE
    candidate_kind: Literal[
        "manuscript_patch",
        "knowledge_card",
        "structure_change",
    ]
    target_fixture_refs: tuple[StableId, ...] = Field(min_length=1)
    must_remain_uncommitted: Literal[True]


class HumanInterventionArtifactSpec(ExpectedArtifactBase):
    artifact_type: Literal[ArtifactType.HUMAN_INTERVENTION] = (
        ArtifactType.HUMAN_INTERVENTION
    )
    intervention_kind: StableId
    expected_state: StableId
    trigger_boundary: str = Field(min_length=1, max_length=1_000)
    tool_name: StableId | None = None
    resource_scopes: tuple[StableId, ...]
    requires_second_confirmation: bool


ExpectedArtifact: TypeAlias = Annotated[
    FinalAnswerArtifactSpec
    | SourceReferenceArtifactSpec
    | CapabilityArtifactSpec
    | WriteCandidateArtifactSpec
    | HumanInterventionArtifactSpec,
    Field(discriminator="artifact_type"),
]


class VerifierId(StrEnum):
    FINAL_ANSWER_CONTRACT = "final_answer_contract"
    SOURCE_FIXTURE_RESOLUTION = "source_fixture_resolution"
    CAPABILITY_ARTIFACT_PROVENANCE = "capability_artifact_provenance"
    WRITE_CANDIDATE_ISOLATED = "write_candidate_isolated"
    HUMAN_INTERVENTION_BOUNDARY = "human_intervention_boundary"
    SIX_BUDGET_LIMITS = "six_budget_limits"
    CAPABILITY_PATH_CONTRACT = "capability_path_contract"
    SECURITY_BOUNDARY = "security_boundary"
    NORMAL_STOP_REASON = "normal_stop_reason"
    EVIDENCE_COMPLETENESS = "evidence_completeness"
    CURRENT_REQUEST_IDENTITY = "current_request_identity"
    FIVE_LAYER_CONTEXT_BOUNDARY = "five_layer_context_boundary"
    TOOL_CALL_PAIRING = "tool_call_pairing"
    SUBAGENT_SCOPE_ISOLATION = "subagent_scope_isolation"
    MEMORY_USE_OR_REJECT = "memory_use_or_reject"
    CHECKPOINT_AVAILABILITY = "checkpoint_availability"


class FinalAnswerVerifierConfig(BenchmarkModel):
    kind: Literal[VerifierId.FINAL_ANSWER_CONTRACT] = VerifierId.FINAL_ANSWER_CONTRACT
    require_non_empty: bool


class StandardVerifierConfig(BenchmarkModel):
    kind: Literal[
        VerifierId.SOURCE_FIXTURE_RESOLUTION,
        VerifierId.CAPABILITY_ARTIFACT_PROVENANCE,
        VerifierId.WRITE_CANDIDATE_ISOLATED,
        VerifierId.HUMAN_INTERVENTION_BOUNDARY,
        VerifierId.SIX_BUDGET_LIMITS,
        VerifierId.CAPABILITY_PATH_CONTRACT,
        VerifierId.SECURITY_BOUNDARY,
        VerifierId.NORMAL_STOP_REASON,
        VerifierId.EVIDENCE_COMPLETENESS,
        VerifierId.CURRENT_REQUEST_IDENTITY,
        VerifierId.FIVE_LAYER_CONTEXT_BOUNDARY,
        VerifierId.TOOL_CALL_PAIRING,
        VerifierId.SUBAGENT_SCOPE_ISOLATION,
        VerifierId.MEMORY_USE_OR_REJECT,
        VerifierId.CHECKPOINT_AVAILABILITY,
    ]


VerifierConfig: TypeAlias = Annotated[
    FinalAnswerVerifierConfig | StandardVerifierConfig,
    Field(discriminator="kind"),
]


class VerifierSpec(BenchmarkModel):
    instance_id: StableId
    verifier_id: VerifierId
    expected_artifact_ids: tuple[StableId, ...] = Field(min_length=1)
    required: bool
    config: VerifierConfig

    @model_validator(mode="after")
    def _config_matches_verifier(self) -> VerifierSpec:
        if self.config.kind is not self.verifier_id:
            raise ValueError("校验器 config.kind 必须与 verifier_id 一致。")
        return self


class VerifierStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INVALID = "invalid"
    NOT_APPLICABLE = "not_applicable"


class FailureCategory(StrEnum):
    BENCHMARK_INVALID = "benchmark_invalid"
    FIXTURE_ISOLATION_FAILED = "fixture_isolation_failed"
    SECURITY_VIOLATION = "security_violation"
    EVIDENCE_INCOMPLETE = "evidence_incomplete"
    MISSING_ARTIFACT = "missing_artifact"
    BUDGET_EXCEEDED = "budget_exceeded"
    VERIFIER_FAILED = "verifier_failed"
    FAILURE_STOP_REASON = "failure_stop_reason"
    EXECUTION_ERROR = "execution_error"
    CANCELLED = "cancelled"
    UNFINISHED = "unfinished"
    UNDETERMINED = "undetermined"


class VerifierResult(BenchmarkModel):
    instance_id: StableId
    verifier_id: VerifierId
    rule_identity: str = Field(min_length=1, max_length=500)
    spec_hash: Sha256
    status: VerifierStatus
    expected_summary: str = Field(min_length=1, max_length=2_000)
    observed_summary: str = Field(min_length=1, max_length=2_000)
    evidence_refs: tuple[StableId, ...]
    failure_categories: tuple[FailureCategory, ...]
    error_code: ErrorCode | None = None
    message_key: str | None = Field(default=None, min_length=1, max_length=500)
    deterministic: Literal[True]
    started_at: str = Field(min_length=1)
    finished_at: str = Field(min_length=1)


class GateKind(StrEnum):
    BUDGET = "budget"
    VERIFIER = "verifier"
    ARTIFACT = "artifact"
    STOP_REASON = "stop_reason"
    SECURITY = "security"
    EVIDENCE = "evidence"


class GateScope(StrEnum):
    CASE = "case"
    SUITE = "suite"


class GateStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INVALID = "invalid"


class GateConditionResult(BenchmarkModel):
    condition_id: StableId
    status: GateStatus
    expected: str = Field(min_length=1, max_length=2_000)
    observed: str = Field(min_length=1, max_length=2_000)
    evidence_refs: tuple[StableId, ...]


class GateResult(BenchmarkModel):
    scope: GateScope
    gate_kind: GateKind
    status: GateStatus
    conditions: tuple[GateConditionResult, ...] = Field(min_length=1)
    expected: str = Field(min_length=1, max_length=2_000)
    observed: str = Field(min_length=1, max_length=2_000)
    evidence_refs: tuple[StableId, ...]
    failure_categories: tuple[FailureCategory, ...]


class CaseConclusion(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INVALID = "invalid"
    UNFINISHED = "unfinished"
    CANCELLED = "cancelled"


class SuiteSpec(BenchmarkModel):
    schema_: Literal["taichu.general_agent_benchmark.suite@1"] = Field(alias="schema")
    suite_id: StableId
    name: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=2_000)
    fixture: FixtureRef
    case_order: tuple[StableId, ...] = Field(min_length=1)
    cases: tuple[CaseSpec, ...] = Field(min_length=1)
    tracks: tuple[TrackSpec, ...] = Field(min_length=1)
    capability_catalog_hash: Sha256
    content_hash: Sha256

    @field_validator("case_order")
    @classmethod
    def _case_order_is_unique(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("case_order 不得包含重复 ID。")
        return value

    @model_validator(mode="after")
    def _validate_suite(self) -> SuiteSpec:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("cases 中的 case_id 必须唯一。")
        if set(case_ids) != set(self.case_order):
            raise ValueError("case_order 必须与 cases 完全同集合。")
        track_kinds = [track.kind for track in self.tracks]
        if len(track_kinds) != len(set(track_kinds)):
            raise ValueError("track kind 不得重复。")
        if TrackKind.SYNTHETIC not in track_kinds:
            raise ValueError("套件必须包含 synthetic 轨道。")
        if any(
            case.fixture_snapshot_id != self.fixture.snapshot_id for case in self.cases
        ):
            raise ValueError("所有案例必须绑定套件 fixture snapshot。")
        return self
