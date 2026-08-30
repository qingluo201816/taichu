"""权威固定基准与密封夹具的严格只读加载器。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import Field, field_validator, model_validator

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    CapabilityKind,
    FixtureEntry,
    FixtureRef,
    FixtureSnapshotId,
    GateKind,
    ResourceBudget,
    Sha256,
    StableId,
    TrackKind,
    TrackSpec,
)
from taichu.application.evaluations.general_agent_benchmark.strict_driver import (
    ScriptedStep,
)

_EXPECTED_CASES = (
    ("direct_answer_current_request", "当前请求直接回答"),
    ("single_manuscript_search", "单次正文检索"),
    ("structure_coverage_read", "结构与覆盖读取"),
    ("single_knowledge_retrieval", "单次知识检索"),
    ("knowledge_catalog_identity_read", "知识目录身份读取"),
    ("external_research_grounded", "外部资料有据研究"),
    ("single_canon_evidence", "单次设定证据"),
    ("summary_world_character", "摘要驱动世界与人物分析"),
    ("architecture_scene_draft", "架构场景与草稿流水线"),
    ("parallel_review_triad", "三类独立审查"),
    ("revision_from_reviews", "依据审查修订"),
    ("manuscript_preview_only", "正文补丁仅预览"),
    ("manuscript_patch_authorized_resume", "授权后应用确认预览"),
    ("structure_create_update", "结构创建并精确更新"),
    ("structure_delete_second_confirmation", "结构删除二次确认"),
    ("knowledge_create_update", "知识创建并精确更新"),
    ("write_authorization_denied", "写授权拒绝"),
    ("memory_active_projection", "有效运行工作记忆生效"),
    ("memory_stale_dependency", "过期记忆依赖排除"),
    ("memory_rejected_parallel_isolation", "被拒绝记忆分支隔离"),
    ("memory_superseded_repair", "被替代记忆修复"),
    ("recovery_after_plan_before_execution", "规划后执行前恢复"),
    ("recovery_tool_result_before_consumption", "Tool 结果未消费前恢复"),
    ("recovery_subagent_interrupted", "Subagent 中断恢复"),
    ("recovery_waiting_authorization", "授权等待中恢复"),
    (
        "recovery_after_write_before_effect_success",
        "写入后效果确认前恢复",
    ),
    ("recovery_verification_interruption", "校验阶段中断恢复"),
    ("recovery_multiple_interruptions", "多次中断恢复"),
    (
        "recovery_checkpoint_unavailable",
        "官方 Checkpoint 缺失时安全停止",
    ),
    ("context_long_history_fact_retention", "长历史关键事实保持"),
    ("context_long_working_memory_priority", "长工作记忆优先裁剪"),
    ("context_large_node_output_projection", "大节点输出投影"),
    ("context_multi_source_overflow", "多来源上下文共同超限"),
    ("context_compression_result_equivalence", "压缩前后结果等价"),
    (
        "context_invalid_memory_pressure_isolation",
        "无效记忆压力隔离",
    ),
    ("context_long_current_request_preserved", "长当前请求完整保留"),
    ("context_unsafe_compression_refusal", "无法安全压缩时拒绝"),
)
_EXPECTED_CASE_IDS = tuple(case_id for case_id, _ in _EXPECTED_CASES)
_BANNED_CASE_IDS = frozenset(
    {"external_access_denied", "runtime_checkpoint_recovery"}
)
_ALL_GATES = frozenset(GateKind)


class RequiredInvocationSpec(BenchmarkModel):
    type: CapabilityKind
    name: StableId
    min_calls: int = Field(ge=0)
    max_calls: int = Field(ge=0)
    expected_outcome: str
    parent: str | None
    partial_order: str | None

    @model_validator(mode="after")
    def _range_and_location_are_valid(self) -> RequiredInvocationSpec:
        if self.max_calls < self.min_calls:
            raise ValueError("required invocation max_calls 不能小于 min_calls。")
        if self.expected_outcome != "completed":
            raise ValueError("首批固定基准只接受 completed 调用结果。")
        if self.parent is None and self.partial_order is None:
            raise ValueError("required invocation 必须声明 parent 或 partial_order。")
        return self


class ScenarioSpec(BenchmarkModel):
    scenario_id: StableId
    objective: str = Field(min_length=1, max_length=2_000)
    target_final_artifact: str = Field(min_length=1, max_length=1_000)
    fixture_refs: tuple[StableId, ...] = Field(min_length=1)
    rag_placeholder: bool = False

    @field_validator("fixture_refs")
    @classmethod
    def _fixture_refs_are_unique(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("scenario.fixture_refs 不得重复。")
        return value


class SetupSpec(BenchmarkModel):
    fixture_ref: StableId
    resource_snapshot_refs: tuple[StableId, ...] = Field(min_length=1)
    memory_seed_ref: StableId | None = None
    human_decision_ref: StableId | None = None
    fault_plan_ref: StableId | None = None
    pressure_plan_ref: StableId | None = None
    expected_post_state_ref: StableId

    @field_validator("resource_snapshot_refs")
    @classmethod
    def _resource_refs_are_unique(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("setup.resource_snapshot_refs 不得重复。")
        return value


class ExpectedTerminalSpec(BenchmarkModel):
    run_status: Literal[
        "completed",
        "preview_only",
        "write_rejected",
        "waiting_human",
        "safe_failure",
    ]
    resumable: bool
    pending_human_kind: StableId | None
    recovery_action: Literal[
        "none",
        "resume",
        "reuse_checkpoint",
        "reconcile_effect",
        "stop",
    ]
    reason_code: StableId

    @model_validator(mode="after")
    def _human_and_recovery_state_are_consistent(
        self,
    ) -> ExpectedTerminalSpec:
        if (self.run_status == "waiting_human") != (
            self.pending_human_kind is not None
        ):
            raise ValueError(
                "只有 waiting_human 终态可以声明 pending_human_kind。"
            )
        if self.run_status == "waiting_human" and not self.resumable:
            raise ValueError("waiting_human 终态必须可续接。")
        return self


class AssertionBase(BenchmarkModel):
    assertion_id: StableId
    description: str = Field(min_length=1, max_length=2_000)


class CallCountAssertionSpec(AssertionBase):
    kind: Literal["call_count"]
    capability_name: StableId
    min_calls: int = Field(ge=0)
    max_calls: int = Field(ge=0)

    @model_validator(mode="after")
    def _call_range_is_valid(self) -> CallCountAssertionSpec:
        if self.max_calls < self.min_calls:
            raise ValueError("call_count.max_calls 不能小于 min_calls。")
        return self


class CallTopologyAssertionSpec(AssertionBase):
    kind: Literal["call_topology"]
    predecessor: StableId
    successor: StableId
    relation: Literal["before", "parallel", "independent"]


class DataflowIdentityAssertionSpec(AssertionBase):
    kind: Literal["dataflow_identity"]
    producer: StableId
    consumer: StableId
    identity_field: StableId


class FinalClaimsAssertionSpec(AssertionBase):
    kind: Literal["final_claims"]
    required_claim_refs: tuple[StableId, ...] = Field(min_length=1)
    forbidden_claim_refs: tuple[StableId, ...] = ()
    normalizer_ref: StableId


class ArtifactContractAssertionSpec(AssertionBase):
    kind: Literal["artifact_contract"]
    artifact_kind: Literal[
        "final_answer",
        "source_reference",
        "capability_artifact",
        "write_candidate",
        "human_intervention",
    ]
    disposition: Literal["required", "forbidden"]


class ResourceDiffAssertionSpec(AssertionBase):
    kind: Literal["resource_diff"]
    resource_snapshot_ref: StableId
    expected_change: Literal[
        "unchanged",
        "target_only",
        "created",
        "updated",
        "deleted",
    ]


class AuthorizationEffectAssertionSpec(AssertionBase):
    kind: Literal["authorization_effect"]
    decision_ref: StableId
    expected_effect_count: int = Field(ge=0)


class MemoryCarrierAbsenceAssertionSpec(AssertionBase):
    kind: Literal["memory_carrier_absence"]
    memory_seed_ref: StableId
    forbidden_states: tuple[
        Literal["stale", "rejected", "superseded"],
        ...,
    ] = Field(min_length=1)


class RecoveryReuseAssertionSpec(AssertionBase):
    kind: Literal["recovery_reuse"]
    fault_plan_ref: StableId
    max_successful_node_reexecutions: int = Field(ge=0)


class CheckpointAvailabilityAssertionSpec(AssertionBase):
    kind: Literal["checkpoint_availability"]
    fault_plan_ref: StableId
    allow_safe_failure: bool


class ContextPreservationAssertionSpec(AssertionBase):
    kind: Literal["context_preservation"]
    pressure_plan_ref: StableId
    protected_carriers: tuple[
        Literal[
            "stable_memory",
            "working_memory",
            "long_term_memory",
            "history_memory",
            "current_request",
        ],
        ...,
    ] = Field(min_length=1)


class ResultContractEquivalenceAssertionSpec(AssertionBase):
    kind: Literal["result_contract_equivalence"]
    pressure_plan_ref: StableId
    comparison: Literal["semantic_contract"]


class ZeroCapabilityOrSideEffectAssertionSpec(AssertionBase):
    kind: Literal["zero_capability_or_side_effect"]
    require_zero_capability_calls: Literal[True]
    require_zero_side_effects: Literal[True]


AssertionSpec: TypeAlias = Annotated[
    CallCountAssertionSpec
    | CallTopologyAssertionSpec
    | DataflowIdentityAssertionSpec
    | FinalClaimsAssertionSpec
    | ArtifactContractAssertionSpec
    | ResourceDiffAssertionSpec
    | AuthorizationEffectAssertionSpec
    | MemoryCarrierAbsenceAssertionSpec
    | RecoveryReuseAssertionSpec
    | CheckpointAvailabilityAssertionSpec
    | ContextPreservationAssertionSpec
    | ResultContractEquivalenceAssertionSpec
    | ZeroCapabilityOrSideEffectAssertionSpec,
    Field(discriminator="kind"),
]


class RunEvidenceProbeSpec(BenchmarkModel):
    kind: Literal["run"]
    selector: Literal["budget", "status", "stop_reason", "recovery"]


class InvocationEvidenceProbeSpec(BenchmarkModel):
    kind: Literal["invocation"]
    selector: Literal["count", "topology", "outcome", "dataflow"]


class ArtifactEvidenceProbeSpec(BenchmarkModel):
    kind: Literal["artifact"]
    selector: Literal["identity", "contract", "provenance"]


class ResourceSnapshotEvidenceProbeSpec(BenchmarkModel):
    kind: Literal["resource_snapshot"]
    selector: Literal["before", "after", "diff"]


class CapabilityResultEvidenceProbeSpec(BenchmarkModel):
    kind: Literal["capability_result"]
    selector: Literal["identity", "payload", "reuse"]


class EffectEvidenceProbeSpec(BenchmarkModel):
    kind: Literal["effect"]
    selector: Literal["request", "outcome", "reconciliation"]


class CheckpointEvidenceProbeSpec(BenchmarkModel):
    kind: Literal["checkpoint"]
    selector: Literal["revision", "integrity", "resume"]


class ContextSnapshotEvidenceProbeSpec(BenchmarkModel):
    kind: Literal["context_snapshot"]
    selector: Literal["layers", "projection", "compression"]


class FixtureSentinelEvidenceProbeSpec(BenchmarkModel):
    kind: Literal["fixture_sentinel"]
    selector: Literal["identity", "isolation", "unchanged"]


class ScriptProtocolEvidenceProbeSpec(BenchmarkModel):
    kind: Literal["script_protocol"]
    selector: Literal["consumption", "order", "completion"]


EvidenceProbeSpec: TypeAlias = Annotated[
    RunEvidenceProbeSpec
    | InvocationEvidenceProbeSpec
    | ArtifactEvidenceProbeSpec
    | ResourceSnapshotEvidenceProbeSpec
    | CapabilityResultEvidenceProbeSpec
    | EffectEvidenceProbeSpec
    | CheckpointEvidenceProbeSpec
    | ContextSnapshotEvidenceProbeSpec
    | FixtureSentinelEvidenceProbeSpec
    | ScriptProtocolEvidenceProbeSpec,
    Field(discriminator="kind"),
]


class EvidenceRequirementSpec(BenchmarkModel):
    evidence_id: StableId
    gate: GateKind
    probe: EvidenceProbeSpec
    comparison: Literal[
        "equality",
        "hash",
        "count",
        "order",
        "set",
        "dataflow",
        "claim_contract",
    ]
    required: Literal[True]


class UserRequestExpansionSpec(BenchmarkModel):
    """在权威套件中紧凑声明、在执行前确定性展开的长请求原文。"""

    repeat_text: str = Field(min_length=1, max_length=1_000)
    repeat_count: int = Field(gt=0, le=10_000)


class AuthoredCaseSpec(BenchmarkModel):
    case_id: StableId
    name: str = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=1_000)
    applicable_tracks: frozenset[TrackKind] = Field(min_length=1)
    user_request: str = Field(min_length=1, max_length=100_000)
    user_request_raw: str = Field(min_length=1, max_length=100_000)
    user_request_expansion: UserRequestExpansionSpec | None = None
    scenario: ScenarioSpec
    setup: SetupSpec
    expected_terminal: ExpectedTerminalSpec
    behavior_assertions: tuple[AssertionSpec, ...] = Field(min_length=1)
    required_evidence: tuple[EvidenceRequirementSpec, ...] = Field(
        min_length=6,
        max_length=6,
    )
    required_invocations: tuple[RequiredInvocationSpec, ...]
    scripted_steps: tuple[ScriptedStep, ...]
    budgets: ResourceBudget = ResourceBudget(
        max_node_executions=50,
        max_replans=4,
        max_capability_calls=20,
        max_model_calls=20,
        max_total_tokens=100_000,
        max_runtime_ms=600_000,
    )

    @model_validator(mode="before")
    @classmethod
    def _expand_declared_current_request(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        expansion_payload = value.get("user_request_expansion")
        if expansion_payload is None:
            return value
        expansion = UserRequestExpansionSpec.model_validate(expansion_payload)
        user_request = value.get("user_request")
        user_request_raw = value.get("user_request_raw")
        if not isinstance(user_request, str) or not isinstance(user_request_raw, str):
            return value
        suffix = expansion.repeat_text * expansion.repeat_count
        return {
            **value,
            "user_request": user_request + suffix,
            "user_request_raw": user_request_raw + suffix,
        }

    @field_validator("name", "summary")
    @classmethod
    def _visible_copy_is_chinese(cls, value: str) -> str:
        if not any("\u4e00" <= character <= "\u9fff" for character in value):
            raise ValueError("案例名称与说明必须包含中文。")
        return value

    @model_validator(mode="after")
    def _request_and_script_are_exact(self) -> AuthoredCaseSpec:
        if self.user_request != self.user_request_raw:
            raise ValueError("当前请求原文不得被 trim、摘要或改写。")
        is_preplan_safe_failure = (
            self.expected_terminal.run_status == "safe_failure"
            and self.expected_terminal.reason_code == "unsafe_context"
            and self.expected_terminal.resumable is False
            and not self.required_invocations
        )
        if not self.scripted_steps and not is_preplan_safe_failure:
            raise ValueError(
                "非规划前安全失败案例必须声明脚本步骤。"
            )
        if self.scripted_steps and is_preplan_safe_failure:
            raise ValueError(
                "规划前安全失败不得声明模型或能力脚本。"
            )
        expected_sequences = list(range(len(self.scripted_steps)))
        if [step.sequence for step in self.scripted_steps] != expected_sequences:
            raise ValueError("案例脚本 sequence 必须从 0 连续递增。")
        declared_steps = {
            (step.kind.value, step.name) for step in self.scripted_steps
        }
        missing = [
            f"{item.type.value}:{item.name}"
            for item in self.required_invocations
            if (item.type.value, item.name) not in declared_steps
        ]
        if missing:
            raise ValueError("脚本缺少 required invocation：" + ", ".join(missing))
        assertion_ids = [item.assertion_id for item in self.behavior_assertions]
        if len(assertion_ids) != len(set(assertion_ids)):
            raise ValueError("behavior assertion ID 不得重复。")
        evidence_ids = [item.evidence_id for item in self.required_evidence]
        evidence_gates = frozenset(item.gate for item in self.required_evidence)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("required evidence ID 不得重复。")
        if evidence_gates != _ALL_GATES:
            raise ValueError("required_evidence 必须精确覆盖六类 Gate。")
        if self.scenario.scenario_id != self.case_id:
            raise ValueError("scenario_id 必须等于 case_id。")
        return self


class AuthoredSuiteSpec(BenchmarkModel):
    schema_: Literal["taichu.general_agent_benchmark.suite@2"] = Field(
        alias="schema"
    )
    suite_id: StableId
    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    fixture: FixtureRef
    case_order: tuple[StableId, ...] = Field(min_length=1)
    cases: tuple[AuthoredCaseSpec, ...] = Field(min_length=1)
    tracks: tuple[TrackSpec, ...] = Field(min_length=1)
    capability_catalog_hash: Sha256
    content_hash: Sha256

    @model_validator(mode="after")
    def _case_order_is_exact(self) -> AuthoredSuiteSpec:
        case_ids = tuple(case.case_id for case in self.cases)
        if case_ids != self.case_order or len(case_ids) != len(set(case_ids)):
            raise ValueError("案例必须按唯一 case_order 原样声明。")
        case_contracts = tuple((case.case_id, case.name) for case in self.cases)
        if case_contracts != _EXPECTED_CASES:
            raise ValueError("活动套件必须精确声明规范顺序的 37 个 ID 与中文名。")
        if _BANNED_CASE_IDS.intersection(case_ids):
            raise ValueError("活动套件包含已废弃的正式案例 ID。")
        synthetic_ids = tuple(
            case.case_id
            for case in self.cases
            if TrackKind.SYNTHETIC in case.applicable_tracks
        )
        live_ids = tuple(
            case.case_id
            for case in self.cases
            if TrackKind.LIVE_PROVIDER in case.applicable_tracks
        )
        if synthetic_ids != _EXPECTED_CASE_IDS:
            raise ValueError("synthetic 轨道必须精确适用全部 37 条案例。")
        if live_ids != _EXPECTED_CASE_IDS[:21]:
            raise ValueError("live_provider 轨道必须精确适用前 21 条案例。")
        track_kinds = frozenset(track.kind for track in self.tracks)
        if track_kinds != {TrackKind.SYNTHETIC, TrackKind.LIVE_PROVIDER}:
            raise ValueError("Suite@2 必须且只声明 synthetic/live_provider 轨道。")
        for index, case in enumerate(self.cases, start=1):
            if case.scenario.rag_placeholder is not (2 <= index <= 6):
                raise ValueError("只有第 2—6 条可以标记为检索/RAG 占坑合同。")
            if case.setup.fixture_ref != self.fixture.fixture_id:
                raise ValueError("案例 setup.fixture_ref 必须绑定套件夹具。")
            if index == 36:
                if (
                    case.user_request_expansion is None
                    or len(case.user_request_raw) < 12_000
                ):
                    raise ValueError(
                        "第 36 条必须显式声明并展开为至少 12,000 字符的长当前请求。"
                    )
            elif case.user_request_expansion is not None:
                raise ValueError("只有第 36 条可以声明长当前请求展开合同。")
        return self


class ScenarioAssetBase(BenchmarkModel):
    asset_id: StableId
    description: str = Field(min_length=1, max_length=1_000)


class ResourceSnapshotAssetSpec(ScenarioAssetBase):
    kind: Literal["resource_snapshot"]
    manifest_paths: tuple[str, ...] = Field(min_length=1)


class MemorySeedAssetSpec(ScenarioAssetBase):
    kind: Literal["memory_seed"]
    manifest_path: str = Field(min_length=1)


class HumanDecisionAssetSpec(ScenarioAssetBase):
    kind: Literal["human_decision"]
    decision: Literal["approved", "denied", "confirmed", "pending"]


class FaultPlanAssetSpec(ScenarioAssetBase):
    kind: Literal["fault_plan"]
    injection_points: tuple[StableId, ...] = Field(min_length=1)
    max_interruptions: int = Field(gt=0)
    recovery_expectation: Literal[
        "resume",
        "reuse_result",
        "reconcile_effect",
        "safe_failure",
    ]


class PressurePlanAssetSpec(ScenarioAssetBase):
    kind: Literal["pressure_plan"]
    carrier: Literal[
        "history",
        "working_memory",
        "node_output",
        "multi_source",
        "equivalence_pair",
        "invalid_memory",
        "current_request",
        "unsafe_total",
    ]
    target_units: int = Field(gt=0)
    protected_refs: tuple[StableId, ...] = Field(min_length=1)


class ExpectedPostStateAssetSpec(ScenarioAssetBase):
    kind: Literal["expected_post_state"]
    invariants: tuple[str, ...] = Field(min_length=1)


ScenarioAssetSpec: TypeAlias = Annotated[
    ResourceSnapshotAssetSpec
    | MemorySeedAssetSpec
    | HumanDecisionAssetSpec
    | FaultPlanAssetSpec
    | PressurePlanAssetSpec
    | ExpectedPostStateAssetSpec,
    Field(discriminator="kind"),
]


class FixtureManifestV2Spec(BenchmarkModel):
    fixture_id: StableId
    schema_: Literal["taichu.general_agent_benchmark.fixture@2"] = Field(
        alias="schema"
    )
    manifest_entries: tuple[FixtureEntry, ...] = Field(min_length=1)
    suite_manifest_entries: tuple[FixtureEntry, ...] = Field(min_length=1)
    manuscript_root: str
    knowledge_seed: str
    conversation_seed: str
    runtime_memory_seed: str
    external_source_manifest: str
    scenario_assets: tuple[ScenarioAssetSpec, ...] = Field(min_length=1)
    content_hash: Sha256
    snapshot_id: FixtureSnapshotId

    @model_validator(mode="after")
    def _identity_and_asset_paths_are_valid(self) -> FixtureManifestV2Spec:
        entry_paths = {item.path for item in self.manifest_entries}
        suite_entry_paths = [
            item.path for item in self.suite_manifest_entries
        ]
        if (
            suite_entry_paths != sorted(suite_entry_paths)
            or len(suite_entry_paths) != len(set(suite_entry_paths))
        ):
            raise ValueError(
                "suite_manifest_entries 必须按路径排序且不得重复。"
            )
        if suite_entry_paths != ["claim-catalog.json"]:
            raise ValueError(
                "Suite@2 必须把唯一根级 claim-catalog.json 纳入内容身份。"
            )
        asset_ids = [item.asset_id for item in self.scenario_assets]
        if asset_ids != sorted(asset_ids) or len(asset_ids) != len(set(asset_ids)):
            raise ValueError("scenario_assets 必须按 asset_id 排序且不得重复。")
        referenced_paths: list[str] = []
        for asset in self.scenario_assets:
            if isinstance(asset, ResourceSnapshotAssetSpec):
                referenced_paths.extend(asset.manifest_paths)
            elif isinstance(asset, MemorySeedAssetSpec):
                referenced_paths.append(asset.manifest_path)
        missing_paths = sorted(set(referenced_paths) - entry_paths)
        if missing_paths:
            raise ValueError("scenario asset 引用未知夹具文件：" + ", ".join(missing_paths))
        if self.snapshot_id != f"fixture_{self.content_hash}":
            raise ValueError("fixture snapshot_id 必须由 manifest content_hash 唯一派生。")
        return self


def load_authored_suite(
    path: Path,
    *,
    expected_capability_catalog_hash: str,
    fixture_manifest_path: Path | None = None,
) -> AuthoredSuiteSpec:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("suite.json 根节点必须是对象。")
    declared_hash = payload.get("content_hash")
    calculated_hash = canonical_sha256(
        {key: value for key, value in payload.items() if key != "content_hash"}
    )
    if declared_hash != calculated_hash:
        raise ValueError("suite content_hash 与规范化内容不一致。")
    suite = AuthoredSuiteSpec.model_validate(payload)
    if suite.capability_catalog_hash != expected_capability_catalog_hash:
        raise ValueError("suite capability catalog hash 已漂移。")
    manifest_path = fixture_manifest_path or (
        path.parent
        / "fixtures"
        / suite.fixture.fixture_id
        / "fixture-manifest.json"
    )
    manifest = load_fixture_manifest(manifest_path)
    if suite.fixture.snapshot_id != manifest.snapshot_id:
        raise ValueError("suite fixture snapshot_id 与夹具清单不一致。")
    _validate_fixture_references(suite, manifest)
    return suite


def load_fixture_manifest(path: Path) -> FixtureManifestV2Spec:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fixture-manifest.json 根节点必须是对象。")
    declared_hash = payload.get("content_hash")
    calculated_hash = canonical_sha256(
        {
            key: value
            for key, value in payload.items()
            if key not in {"content_hash", "snapshot_id"}
        }
    )
    if declared_hash != calculated_hash:
        raise ValueError("fixture manifest content_hash 与规范化内容不一致。")
    manifest = FixtureManifestV2Spec.model_validate(payload)
    root = path.parent
    for entry in manifest.manifest_entries:
        target = root / Path(entry.path)
        _verify_manifest_entry(target, entry=entry, scope="夹具")
    suite_root = root.parent.parent
    for entry in manifest.suite_manifest_entries:
        target = suite_root / Path(entry.path)
        _verify_manifest_entry(target, entry=entry, scope="Suite")
    return manifest


def _verify_manifest_entry(
    target: Path,
    *,
    entry: FixtureEntry,
    scope: str,
) -> None:
    content = target.read_bytes()
    if len(content) != entry.size_bytes:
        raise ValueError(f"{scope}文件大小漂移：{entry.path}")
    if hashlib.sha256(content).hexdigest() != entry.sha256:
        raise ValueError(f"{scope}文件哈希漂移：{entry.path}")


def _validate_fixture_references(
    suite: AuthoredSuiteSpec,
    manifest: FixtureManifestV2Spec,
) -> None:
    assets = {asset.asset_id: asset for asset in manifest.scenario_assets}
    expected_types: dict[str, type[ScenarioAssetBase]] = {
        "resource_snapshot_refs": ResourceSnapshotAssetSpec,
        "memory_seed_ref": MemorySeedAssetSpec,
        "human_decision_ref": HumanDecisionAssetSpec,
        "fault_plan_ref": FaultPlanAssetSpec,
        "pressure_plan_ref": PressurePlanAssetSpec,
        "expected_post_state_ref": ExpectedPostStateAssetSpec,
    }

    for case in suite.cases:
        references: list[tuple[str, type[ScenarioAssetBase]]] = [
            (item, ResourceSnapshotAssetSpec)
            for item in case.setup.resource_snapshot_refs
        ]
        for field_name in (
            "memory_seed_ref",
            "human_decision_ref",
            "fault_plan_ref",
            "pressure_plan_ref",
            "expected_post_state_ref",
        ):
            value = getattr(case.setup, field_name)
            if value is not None:
                references.append((value, expected_types[field_name]))
        for reference in case.scenario.fixture_refs:
            if reference not in assets:
                raise ValueError(
                    f"案例 {case.case_id} 的夹具引用不存在：{reference}"
                )
        for reference, expected_type in references:
            asset = assets.get(reference)
            if asset is None:
                raise ValueError(
                    f"案例 {case.case_id} 的夹具引用不存在：{reference}"
                )
            if not isinstance(asset, expected_type):
                raise ValueError(
                    f"案例 {case.case_id} 的夹具引用类型错误：{reference}"
                )
        _validate_assertion_asset_references(case, assets)


def _validate_assertion_asset_references(
    case: AuthoredCaseSpec,
    assets: dict[str, ScenarioAssetSpec],
) -> None:
    references: list[tuple[str, type[ScenarioAssetBase]]] = []
    for assertion in case.behavior_assertions:
        if isinstance(assertion, ResourceDiffAssertionSpec):
            references.append(
                (assertion.resource_snapshot_ref, ResourceSnapshotAssetSpec)
            )
        elif isinstance(assertion, AuthorizationEffectAssertionSpec):
            references.append((assertion.decision_ref, HumanDecisionAssetSpec))
        elif isinstance(assertion, MemoryCarrierAbsenceAssertionSpec):
            references.append((assertion.memory_seed_ref, MemorySeedAssetSpec))
        elif isinstance(
            assertion,
            (RecoveryReuseAssertionSpec, CheckpointAvailabilityAssertionSpec),
        ):
            references.append((assertion.fault_plan_ref, FaultPlanAssetSpec))
        elif isinstance(
            assertion,
            (
                ContextPreservationAssertionSpec,
                ResultContractEquivalenceAssertionSpec,
            ),
        ):
            references.append(
                (assertion.pressure_plan_ref, PressurePlanAssetSpec)
            )
    for reference, expected_type in references:
        asset = assets.get(reference)
        if asset is None:
            raise ValueError(
                f"案例 {case.case_id} 的 assertion 夹具引用不存在：{reference}"
            )
        if not isinstance(asset, expected_type):
            raise ValueError(
                f"案例 {case.case_id} 的 assertion 夹具引用类型错误：{reference}"
            )
