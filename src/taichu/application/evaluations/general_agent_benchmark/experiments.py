"""需求 8.1-8.31：受控实验、确定性可比性与模型比较准入。"""

from __future__ import annotations

import re
from collections.abc import Iterable
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    Sha256,
    StableId,
    TrackKind,
)

_RUN_ID_PATTERN = r"^benchmark_run_\d{8}T\d{6}Z_[a-f0-9]{12}$"
_SYNTHETIC_ADMISSION_CASE_COUNT = 37
_LIVE_PROVIDER_CASE_COUNT = 21


class ArtifactRelationKind(StrEnum):
    """关系类型决定必须相等的字段与唯一合法差异集合。"""

    SYNTHETIC_TO_LIVE = "synthetic_to_live"
    SYNTHETIC37_TO_LIVE21 = "synthetic_to_live"
    LIVE_MODEL_COMPARISON = "live_model_comparison"


class DifferenceKind(StrEnum):
    """固定、不可由调用方扩展的身份差异种类。"""

    ARTIFACT = "artifact"
    ARTIFACT_IDENTITY = "artifact"
    PROVIDER = "provider"
    MODEL = "model"
    DECODE_CONFIGURATION = "decode_configuration"
    DECODE_CONFIG = "decode_configuration"
    PROVIDER_REQUEST = "provider_request"
    PROVIDER_RUN = "provider_run"
    USAGE = "usage"
    LATENCY = "latency"
    OUTPUT = "output"
    RESULT = "result"
    TRACK = "track"
    SELECTED_CASE_SET = "selected_case_set"
    CASE_SET = "selected_case_set"
    EXECUTION_IDENTITY = "execution_identity"
    MODEL_GATEWAY = "execution_identity"
    RUNNER_PROTOCOL = "runner_protocol"
    ARTIFACT_SCHEMA = "artifact_schema"
    ARTIFACT_KIND = "artifact_kind"


class IdentityFailureCode(StrEnum):
    """关系校验失败的稳定机器语义。"""

    NOT_QUALIFIED = "NOT_QUALIFIED"
    NOT_QUALIFIED_SYNTHETIC = "NOT_QUALIFIED"
    CASE_SET_MISMATCH = "CASE_SET_MISMATCH"
    CASE_PROJECTION_MISMATCH = "CASE_PROJECTION_MISMATCH"
    INCOMPATIBLE_SUITE = "INCOMPATIBLE_SUITE"
    INCOMPATIBLE_FIXTURE = "INCOMPATIBLE_FIXTURE"
    INCOMPATIBLE_CATALOG = "INCOMPATIBLE_CATALOG"
    INCOMPATIBLE_ORACLE = "INCOMPATIBLE_ORACLE"
    INCOMPATIBLE_RUNTIME = "INCOMPATIBLE_RUNTIME"
    INCOMPATIBLE_TRACK = "INCOMPATIBLE_TRACK"
    IDENTITY_INCOMPLETE = "IDENTITY_INCOMPLETE"
    UNDECLARED_DIFFERENCE = "UNDECLARED_DIFFERENCE"


class IdentityRelationStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    COMPARABLE = "COMPARABLE"
    REJECTED = "REJECTED"


_RELATION_ALLOWED_DIFFERENCES: dict[
    ArtifactRelationKind,
    frozenset[DifferenceKind],
] = {
    ArtifactRelationKind.SYNTHETIC_TO_LIVE: frozenset(
        {
            DifferenceKind.TRACK,
            DifferenceKind.SELECTED_CASE_SET,
            DifferenceKind.EXECUTION_IDENTITY,
        }
    ),
    ArtifactRelationKind.LIVE_MODEL_COMPARISON: frozenset(
        {
            DifferenceKind.ARTIFACT,
            DifferenceKind.PROVIDER,
            DifferenceKind.MODEL,
            DifferenceKind.DECODE_CONFIGURATION,
            DifferenceKind.PROVIDER_REQUEST,
            DifferenceKind.PROVIDER_RUN,
            DifferenceKind.USAGE,
            DifferenceKind.LATENCY,
            DifferenceKind.OUTPUT,
            DifferenceKind.RESULT,
        }
    ),
}


class CaseContractIdentity(BenchmarkModel):
    """单案例合同的关系无关内容身份。"""

    case_id: StableId
    contract_hash: Sha256


class ArtifactIdentity(BenchmarkModel):
    """单个不可变 Benchmark 工件的完整身份投影。

    字段允许为 ``None``，仅用于只读历史或损坏工件的 fail-closed
    Hydration。任何可比关系都会在构造 ComparabilityKey 前把缺失或
    自相矛盾的身份返回为 ``IDENTITY_INCOMPLETE``。
    """

    artifact_schema: str | None = Field(
        default=None,
        min_length=1,
        max_length=300,
    )
    artifact_kind: StableId | None = None
    artifact_ref: str | None = Field(
        default=None,
        min_length=1,
        max_length=1_000,
    )
    artifact_content_hash: Sha256 | None = None
    suite_content_hash: Sha256 | None = None
    selected_case_ids: tuple[StableId, ...] = ()
    selected_case_set_hash: Sha256 | None = None
    case_contracts: tuple[CaseContractIdentity, ...] = ()
    selected_case_contract_hash: Sha256 | None = None
    track: TrackKind | None = None
    fixture_snapshot_hash: Sha256 | None = None
    capability_catalog_hash: Sha256 | None = None
    oracle_rule_set_hash: Sha256 | None = None
    runtime_config_hash: Sha256 | None = None
    runtime_code_snapshot_hash: Sha256 | None = None
    runner_protocol_hash: Sha256 | None = None
    synthetic_script_identity: Sha256 | None = None
    synthetic_admission_passed: bool | None = None
    provider_id: StableId | None = None
    model_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=300,
    )
    decode_configuration_hash: Sha256 | None = None
    provider_request_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
    )
    provider_run_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
    )
    usage_hash: Sha256 | None = None
    latency_hash: Sha256 | None = None
    output_hash: Sha256 | None = None
    result_hash: Sha256 | None = None

    @field_validator("selected_case_ids")
    @classmethod
    def _selected_case_ids_are_unique(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("工件身份中的 selected_case_ids 不得重复。")
        return value

    @field_validator("case_contracts")
    @classmethod
    def _case_contract_ids_are_unique(
        cls,
        value: tuple[CaseContractIdentity, ...],
    ) -> tuple[CaseContractIdentity, ...]:
        case_ids = tuple(item.case_id for item in value)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("工件身份中的案例合同不得重复。")
        return value

    @classmethod
    def create(
        cls,
        *,
        selected_case_ids: tuple[str, ...],
        case_contracts: tuple[CaseContractIdentity, ...],
        **identity_values: object,
    ) -> ArtifactIdentity:
        """由有序案例与逐案例合同确定性构造单工件身份。"""

        return cls(
            **identity_values,
            selected_case_ids=selected_case_ids,
            selected_case_set_hash=canonical_sha256(selected_case_ids),
            case_contracts=case_contracts,
            selected_case_contract_hash=canonical_sha256(case_contracts),
        )


class IdentityDifference(BenchmarkModel):
    """声明或实测差异，只保存双方规范化值的内容哈希。"""

    kind: DifferenceKind
    baseline_value_sha256: Sha256
    candidate_value_sha256: Sha256


class DeclaredDifferences(BenchmarkModel):
    """关系固定 allowlist 内、由双方实际值绑定的差异声明。"""

    relation_kind: ArtifactRelationKind
    baseline_artifact_ref: str = Field(min_length=1, max_length=1_000)
    candidate_artifact_ref: str = Field(min_length=1, max_length=1_000)
    differences: tuple[IdentityDifference, ...] = ()

    @model_validator(mode="after")
    def _differences_are_unique_and_allowed(self) -> DeclaredDifferences:
        kinds = tuple(item.kind for item in self.differences)
        if len(kinds) != len(set(kinds)):
            raise ValueError("DeclaredDifferences 的 DifferenceKind 不得重复。")
        allowed = _RELATION_ALLOWED_DIFFERENCES[self.relation_kind]
        forbidden = sorted(set(kinds) - allowed, key=lambda item: item.value)
        if forbidden:
            values = "、".join(item.value for item in forbidden)
            raise ValueError(
                f"{self.relation_kind.value} 关系不允许声明差异：{values}。"
            )
        return self

    @classmethod
    def create(
        cls,
        *,
        relation_kind: ArtifactRelationKind | str,
        baseline: ArtifactIdentity,
        candidate: ArtifactIdentity,
        difference_kinds: Iterable[DifferenceKind | str],
    ) -> DeclaredDifferences:
        """绑定调用方声明的 kind 与双方当前实际值，禁止伪造差异值。"""

        relation = ArtifactRelationKind(relation_kind)
        differences = tuple(
            _identity_difference(
                kind=DifferenceKind(kind),
                baseline=baseline,
                candidate=candidate,
                relation_kind=relation,
            )
            for kind in difference_kinds
        )
        return cls(
            relation_kind=relation,
            baseline_artifact_ref=baseline.artifact_ref or "",
            candidate_artifact_ref=candidate.artifact_ref or "",
            differences=differences,
        )


class ComparabilityKey(BenchmarkModel):
    """只包含某一关系必须相等的身份字段。"""

    relation_kind: ArtifactRelationKind
    suite_content_hash: Sha256
    comparable_case_ids: tuple[StableId, ...] = Field(min_length=1)
    projected_case_contract_hash: Sha256
    fixture_snapshot_hash: Sha256
    capability_catalog_hash: Sha256
    oracle_rule_set_hash: Sha256
    runtime_config_hash: Sha256
    runtime_code_snapshot_hash: Sha256
    runner_protocol_hash: Sha256
    comparability_key_sha256: Sha256

    @field_validator("comparable_case_ids")
    @classmethod
    def _comparable_case_ids_are_unique(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("ComparabilityKey 的案例不得重复。")
        return value

    @model_validator(mode="after")
    def _key_hash_matches_fields(self) -> ComparabilityKey:
        expected = canonical_sha256(
            self.model_dump(
                mode="json",
                exclude={"comparability_key_sha256"},
            )
        )
        if self.comparability_key_sha256 != expected:
            raise ValueError("ComparabilityKey 内容身份不一致。")
        return self

    @classmethod
    def create(
        cls,
        *,
        relation_kind: ArtifactRelationKind,
        suite_content_hash: str,
        comparable_case_ids: tuple[str, ...],
        projected_case_contract_hash: str,
        fixture_snapshot_hash: str,
        capability_catalog_hash: str,
        oracle_rule_set_hash: str,
        runtime_config_hash: str,
        runtime_code_snapshot_hash: str,
        runner_protocol_hash: str,
    ) -> ComparabilityKey:
        payload = {
            "relation_kind": relation_kind,
            "suite_content_hash": suite_content_hash,
            "comparable_case_ids": comparable_case_ids,
            "projected_case_contract_hash": projected_case_contract_hash,
            "fixture_snapshot_hash": fixture_snapshot_hash,
            "capability_catalog_hash": capability_catalog_hash,
            "oracle_rule_set_hash": oracle_rule_set_hash,
            "runtime_config_hash": runtime_config_hash,
            "runtime_code_snapshot_hash": runtime_code_snapshot_hash,
            "runner_protocol_hash": runner_protocol_hash,
        }
        return cls(
            **payload,
            comparability_key_sha256=canonical_sha256(payload),
        )


class ArtifactRelationResult(BenchmarkModel):
    """成功才携带可比键；失败只返回 typed 原因，不产生拼接对象。"""

    relation_kind: ArtifactRelationKind
    status: IdentityRelationStatus
    baseline_artifact_ref: str | None
    candidate_artifact_ref: str | None
    comparability_key: ComparabilityKey | None
    declared_differences: DeclaredDifferences
    actual_differences: tuple[IdentityDifference, ...]
    failure_code: IdentityFailureCode | None
    message: str = Field(min_length=1, max_length=4_000)
    identity_problems: tuple[str, ...] = ()
    undeclared_difference_kinds: tuple[DifferenceKind, ...] = ()
    overdeclared_difference_kinds: tuple[DifferenceKind, ...] = ()
    value_mismatch_difference_kinds: tuple[DifferenceKind, ...] = ()
    qualified_by_synthetic_ref: str | None = None

    @model_validator(mode="after")
    def _status_matches_payload(self) -> ArtifactRelationResult:
        successful = self.status in {
            IdentityRelationStatus.ELIGIBLE,
            IdentityRelationStatus.COMPARABLE,
        }
        if successful:
            if self.failure_code is not None or self.comparability_key is None:
                raise ValueError("成功身份关系必须包含可比键且不得包含失败码。")
        elif self.failure_code is None or self.comparability_key is not None:
            raise ValueError("失败身份关系必须包含失败码且不得返回可比键。")
        if (
            self.status is IdentityRelationStatus.ELIGIBLE
            and self.relation_kind is not ArtifactRelationKind.SYNTHETIC_TO_LIVE
        ):
            raise ValueError("只有 Synthetic→Live 关系可以返回 ELIGIBLE。")
        if (
            self.status is IdentityRelationStatus.COMPARABLE
            and self.relation_kind is not ArtifactRelationKind.LIVE_MODEL_COMPARISON
        ):
            raise ValueError("只有 Live 多模型关系可以返回 COMPARABLE。")
        return self

    @property
    def actual_difference_kinds(self) -> tuple[DifferenceKind, ...]:
        return tuple(item.kind for item in self.actual_differences)

    @property
    def eligible(self) -> bool:
        return self.status is IdentityRelationStatus.ELIGIBLE

    @property
    def comparable(self) -> bool:
        return self.status is IdentityRelationStatus.COMPARABLE


ComparabilityRelationResult = ArtifactRelationResult


def qualify_synthetic_for_live(
    synthetic: ArtifactIdentity,
    live: ArtifactIdentity,
    declared_differences: DeclaredDifferences,
) -> ArtifactRelationResult:
    """校验完整 Synthetic 37 基线是否有资格启动同套件 Live 21。"""

    relation = ArtifactRelationKind.SYNTHETIC_TO_LIVE
    problems = _identity_problems(
        synthetic,
        label="baseline",
        require_live_observations=False,
    ) + _identity_problems(
        live,
        label="candidate",
        require_live_observations=False,
    )
    if problems:
        return _rejected_relation(
            relation_kind=relation,
            baseline=synthetic,
            candidate=live,
            declared_differences=declared_differences,
            failure_code=IdentityFailureCode.IDENTITY_INCOMPLETE,
            message="工件身份缺失或内部内容身份不一致，不能建立资格关系。",
            identity_problems=problems,
        )
    if (
        synthetic.track is not TrackKind.SYNTHETIC
        or live.track is not TrackKind.LIVE_PROVIDER
    ):
        return _rejected_relation(
            relation_kind=relation,
            baseline=synthetic,
            candidate=live,
            declared_differences=declared_differences,
            failure_code=IdentityFailureCode.INCOMPATIBLE_TRACK,
            message="Synthetic→Live 资格必须由 synthetic 工件连接 live_provider 工件。",
        )
    if (
        synthetic.synthetic_admission_passed is not True
        or len(synthetic.selected_case_ids) != _SYNTHETIC_ADMISSION_CASE_COUNT
    ):
        return _rejected_relation(
            relation_kind=relation,
            baseline=synthetic,
            candidate=live,
            declared_differences=declared_differences,
            failure_code=IdentityFailureCode.NOT_QUALIFIED,
            message="Synthetic 工件尚未形成完整 37/37 六门禁准入通过。",
        )
    frozen_failure = _frozen_identity_failure(synthetic, live)
    if frozen_failure is not None:
        code, message = frozen_failure
        return _rejected_relation(
            relation_kind=relation,
            baseline=synthetic,
            candidate=live,
            declared_differences=declared_differences,
            failure_code=code,
            message=message,
        )
    if (
        len(live.selected_case_ids) != _LIVE_PROVIDER_CASE_COUNT
        or live.selected_case_ids
        != synthetic.selected_case_ids[:_LIVE_PROVIDER_CASE_COUNT]
    ):
        return _rejected_relation(
            relation_kind=relation,
            baseline=synthetic,
            candidate=live,
            declared_differences=declared_differences,
            failure_code=IdentityFailureCode.CASE_SET_MISMATCH,
            message="Live 资格选择必须精确等于同一 Synthetic 套件的前 21 条。",
        )

    synthetic_projection = _project_case_contracts(
        synthetic,
        live.selected_case_ids,
    )
    live_projection = _project_case_contracts(live, live.selected_case_ids)
    if synthetic_projection != live_projection:
        return _rejected_relation(
            relation_kind=relation,
            baseline=synthetic,
            candidate=live,
            declared_differences=declared_differences,
            failure_code=IdentityFailureCode.CASE_PROJECTION_MISMATCH,
            message="Synthetic 与 Live 的共同 21 条案例合同投影不一致。",
        )

    key = _build_comparability_key(
        relation_kind=relation,
        baseline=synthetic,
        comparable_case_ids=live.selected_case_ids,
        projected_case_contract_hash=synthetic_projection,
    )
    return _evaluate_declared_differences(
        relation_kind=relation,
        success_status=IdentityRelationStatus.ELIGIBLE,
        baseline=synthetic,
        candidate=live,
        declared_differences=declared_differences,
        comparability_key=key,
        qualified_by_synthetic_ref=synthetic.artifact_ref,
    )


def compare_live_model_artifacts(
    baseline: ArtifactIdentity,
    candidate: ArtifactIdentity,
    declared_differences: DeclaredDifferences,
) -> ArtifactRelationResult:
    """只按 Live 多模型关系的冻结键与固定差异集合建立比较。"""

    relation = ArtifactRelationKind.LIVE_MODEL_COMPARISON
    problems = _identity_problems(
        baseline,
        label="baseline",
        require_live_observations=True,
    ) + _identity_problems(
        candidate,
        label="candidate",
        require_live_observations=True,
    )
    if problems:
        return _rejected_relation(
            relation_kind=relation,
            baseline=baseline,
            candidate=candidate,
            declared_differences=declared_differences,
            failure_code=IdentityFailureCode.IDENTITY_INCOMPLETE,
            message="Live 工件身份缺失或内部内容身份不一致，不能进行模型比较。",
            identity_problems=problems,
        )
    if (
        baseline.track is not TrackKind.LIVE_PROVIDER
        or candidate.track is not TrackKind.LIVE_PROVIDER
    ):
        return _rejected_relation(
            relation_kind=relation,
            baseline=baseline,
            candidate=candidate,
            declared_differences=declared_differences,
            failure_code=IdentityFailureCode.INCOMPATIBLE_TRACK,
            message="Live 多模型比较的双方都必须是 live_provider 工件。",
        )
    frozen_failure = _frozen_identity_failure(baseline, candidate)
    if frozen_failure is not None:
        code, message = frozen_failure
        return _rejected_relation(
            relation_kind=relation,
            baseline=baseline,
            candidate=candidate,
            declared_differences=declared_differences,
            failure_code=code,
            message=message,
        )
    if (
        baseline.selected_case_ids != candidate.selected_case_ids
        or baseline.selected_case_set_hash != candidate.selected_case_set_hash
    ):
        return _rejected_relation(
            relation_kind=relation,
            baseline=baseline,
            candidate=candidate,
            declared_differences=declared_differences,
            failure_code=IdentityFailureCode.CASE_SET_MISMATCH,
            message="Live 多模型比较必须使用完全相同的有序案例集合。",
        )
    baseline_projection = _project_case_contracts(
        baseline,
        baseline.selected_case_ids,
    )
    candidate_projection = _project_case_contracts(
        candidate,
        candidate.selected_case_ids,
    )
    if baseline_projection != candidate_projection:
        return _rejected_relation(
            relation_kind=relation,
            baseline=baseline,
            candidate=candidate,
            declared_differences=declared_differences,
            failure_code=IdentityFailureCode.CASE_PROJECTION_MISMATCH,
            message="Live 多模型比较的案例合同投影不一致。",
        )

    key = _build_comparability_key(
        relation_kind=relation,
        baseline=baseline,
        comparable_case_ids=baseline.selected_case_ids,
        projected_case_contract_hash=baseline_projection,
    )
    return _evaluate_declared_differences(
        relation_kind=relation,
        success_status=IdentityRelationStatus.COMPARABLE,
        baseline=baseline,
        candidate=candidate,
        declared_differences=declared_differences,
        comparability_key=key,
    )


def compare_live_models(
    baseline: ArtifactIdentity,
    candidate: ArtifactIdentity,
    declared_differences: DeclaredDifferences,
) -> ArtifactRelationResult:
    """``compare_live_model_artifacts`` 的语义化兼容别名。"""

    return compare_live_model_artifacts(
        baseline,
        candidate,
        declared_differences,
    )


def validate_artifact_relation(
    baseline: ArtifactIdentity,
    candidate: ArtifactIdentity,
    declared_differences: DeclaredDifferences,
) -> ArtifactRelationResult:
    """按声明的固定 relation kind 分派，调用方不能提供忽略字段。"""

    if declared_differences.relation_kind is ArtifactRelationKind.SYNTHETIC_TO_LIVE:
        return qualify_synthetic_for_live(
            baseline,
            candidate,
            declared_differences,
        )
    return compare_live_model_artifacts(
        baseline,
        candidate,
        declared_differences,
    )


class BenchmarkIdentityJoiner:
    """无状态关系校验入口；失败时绝不返回拼接/聚合键。"""

    @staticmethod
    def qualify_synthetic_for_live(
        synthetic: ArtifactIdentity,
        live: ArtifactIdentity,
        declared_differences: DeclaredDifferences,
    ) -> ArtifactRelationResult:
        return qualify_synthetic_for_live(
            synthetic,
            live,
            declared_differences,
        )

    @staticmethod
    def compare_live_models(
        baseline: ArtifactIdentity,
        candidate: ArtifactIdentity,
        declared_differences: DeclaredDifferences,
    ) -> ArtifactRelationResult:
        return compare_live_model_artifacts(
            baseline,
            candidate,
            declared_differences,
        )

    @staticmethod
    def join(
        baseline: ArtifactIdentity,
        candidate: ArtifactIdentity,
        declared_differences: DeclaredDifferences,
    ) -> ArtifactRelationResult:
        return validate_artifact_relation(
            baseline,
            candidate,
            declared_differences,
        )


def _identity_problems(
    identity: ArtifactIdentity,
    *,
    label: str,
    require_live_observations: bool,
) -> tuple[str, ...]:
    required_fields = (
        "artifact_schema",
        "artifact_kind",
        "artifact_ref",
        "artifact_content_hash",
        "suite_content_hash",
        "selected_case_set_hash",
        "selected_case_contract_hash",
        "track",
        "fixture_snapshot_hash",
        "capability_catalog_hash",
        "oracle_rule_set_hash",
        "runtime_config_hash",
        "runtime_code_snapshot_hash",
        "runner_protocol_hash",
    )
    problems = [
        f"{label}.{field}"
        for field in required_fields
        if getattr(identity, field) is None
    ]
    if not identity.selected_case_ids:
        problems.append(f"{label}.selected_case_ids")
    if not identity.case_contracts:
        problems.append(f"{label}.case_contracts")
    if (
        identity.selected_case_ids
        and identity.selected_case_set_hash is not None
        and identity.selected_case_set_hash
        != canonical_sha256(identity.selected_case_ids)
    ):
        problems.append(f"{label}.selected_case_set_hash")
    contract_ids = tuple(item.case_id for item in identity.case_contracts)
    if identity.case_contracts and contract_ids != identity.selected_case_ids:
        problems.append(f"{label}.case_contracts")
    if (
        identity.case_contracts
        and identity.selected_case_contract_hash is not None
        and identity.selected_case_contract_hash
        != canonical_sha256(identity.case_contracts)
    ):
        problems.append(f"{label}.selected_case_contract_hash")

    if identity.track is TrackKind.SYNTHETIC:
        if identity.synthetic_script_identity is None:
            problems.append(f"{label}.synthetic_script_identity")
        if identity.synthetic_admission_passed is None:
            problems.append(f"{label}.synthetic_admission_passed")
        unexpected_live = (
            "provider_id",
            "model_id",
            "decode_configuration_hash",
            "provider_request_id",
            "provider_run_id",
            "usage_hash",
            "latency_hash",
            "output_hash",
            "result_hash",
        )
        problems.extend(
            f"{label}.{field}"
            for field in unexpected_live
            if getattr(identity, field) is not None
        )
    elif identity.track is TrackKind.LIVE_PROVIDER:
        for field in (
            "provider_id",
            "model_id",
            "decode_configuration_hash",
        ):
            if getattr(identity, field) is None:
                problems.append(f"{label}.{field}")
        if identity.synthetic_script_identity is not None:
            problems.append(f"{label}.synthetic_script_identity")
        if identity.synthetic_admission_passed is not None:
            problems.append(f"{label}.synthetic_admission_passed")
        if require_live_observations:
            for field in (
                "provider_request_id",
                "provider_run_id",
                "usage_hash",
                "latency_hash",
                "output_hash",
                "result_hash",
            ):
                if getattr(identity, field) is None:
                    problems.append(f"{label}.{field}")
    return tuple(dict.fromkeys(problems))


def _frozen_identity_failure(
    baseline: ArtifactIdentity,
    candidate: ArtifactIdentity,
) -> tuple[IdentityFailureCode, str] | None:
    checks = (
        (
            "suite_content_hash",
            IdentityFailureCode.INCOMPATIBLE_SUITE,
            "双方 Suite 内容身份不一致。",
        ),
        (
            "fixture_snapshot_hash",
            IdentityFailureCode.INCOMPATIBLE_FIXTURE,
            "双方夹具快照身份不一致。",
        ),
        (
            "capability_catalog_hash",
            IdentityFailureCode.INCOMPATIBLE_CATALOG,
            "双方派生能力目录身份不一致。",
        ),
        (
            "oracle_rule_set_hash",
            IdentityFailureCode.INCOMPATIBLE_ORACLE,
            "双方 Oracle 规则集身份不一致。",
        ),
    )
    for field, code, message in checks:
        if getattr(baseline, field) != getattr(candidate, field):
            return code, message
    if (
        baseline.runtime_config_hash != candidate.runtime_config_hash
        or baseline.runtime_code_snapshot_hash != candidate.runtime_code_snapshot_hash
    ):
        return (
            IdentityFailureCode.INCOMPATIBLE_RUNTIME,
            "双方 Runtime 配置或代码快照身份不一致。",
        )
    return None


def _project_case_contracts(
    identity: ArtifactIdentity,
    case_ids: tuple[str, ...],
) -> str:
    by_id = {item.case_id: item for item in identity.case_contracts}
    return canonical_sha256(tuple(by_id[case_id] for case_id in case_ids))


def _build_comparability_key(
    *,
    relation_kind: ArtifactRelationKind,
    baseline: ArtifactIdentity,
    comparable_case_ids: tuple[str, ...],
    projected_case_contract_hash: str,
) -> ComparabilityKey:
    required = (
        baseline.suite_content_hash,
        baseline.fixture_snapshot_hash,
        baseline.capability_catalog_hash,
        baseline.oracle_rule_set_hash,
        baseline.runtime_config_hash,
        baseline.runtime_code_snapshot_hash,
        baseline.runner_protocol_hash,
    )
    if any(value is None for value in required):
        raise ValueError("构造 ComparabilityKey 前必须完成身份完整性校验。")
    return ComparabilityKey.create(
        relation_kind=relation_kind,
        suite_content_hash=baseline.suite_content_hash,
        comparable_case_ids=comparable_case_ids,
        projected_case_contract_hash=projected_case_contract_hash,
        fixture_snapshot_hash=baseline.fixture_snapshot_hash,
        capability_catalog_hash=baseline.capability_catalog_hash,
        oracle_rule_set_hash=baseline.oracle_rule_set_hash,
        runtime_config_hash=baseline.runtime_config_hash,
        runtime_code_snapshot_hash=baseline.runtime_code_snapshot_hash,
        runner_protocol_hash=baseline.runner_protocol_hash,
    )


def _difference_values(
    *,
    kind: DifferenceKind,
    baseline: ArtifactIdentity,
    candidate: ArtifactIdentity,
    relation_kind: ArtifactRelationKind,
) -> tuple[object, object]:
    if kind is DifferenceKind.ARTIFACT:
        return (
            {
                "artifact_ref": baseline.artifact_ref,
                "artifact_content_hash": baseline.artifact_content_hash,
            },
            {
                "artifact_ref": candidate.artifact_ref,
                "artifact_content_hash": candidate.artifact_content_hash,
            },
        )
    if kind is DifferenceKind.PROVIDER:
        return baseline.provider_id, candidate.provider_id
    if kind is DifferenceKind.MODEL:
        return baseline.model_id, candidate.model_id
    if kind is DifferenceKind.DECODE_CONFIGURATION:
        return (
            baseline.decode_configuration_hash,
            candidate.decode_configuration_hash,
        )
    if kind is DifferenceKind.PROVIDER_REQUEST:
        return baseline.provider_request_id, candidate.provider_request_id
    if kind is DifferenceKind.PROVIDER_RUN:
        return baseline.provider_run_id, candidate.provider_run_id
    if kind is DifferenceKind.USAGE:
        return baseline.usage_hash, candidate.usage_hash
    if kind is DifferenceKind.LATENCY:
        return baseline.latency_hash, candidate.latency_hash
    if kind is DifferenceKind.OUTPUT:
        return baseline.output_hash, candidate.output_hash
    if kind is DifferenceKind.RESULT:
        return baseline.result_hash, candidate.result_hash
    if kind is DifferenceKind.TRACK:
        return baseline.track, candidate.track
    if kind is DifferenceKind.SELECTED_CASE_SET:
        return (
            {
                "selected_case_ids": baseline.selected_case_ids,
                "selected_case_set_hash": baseline.selected_case_set_hash,
            },
            {
                "selected_case_ids": candidate.selected_case_ids,
                "selected_case_set_hash": candidate.selected_case_set_hash,
            },
        )
    if kind is DifferenceKind.EXECUTION_IDENTITY:
        if relation_kind is ArtifactRelationKind.SYNTHETIC_TO_LIVE:
            return (
                {
                    "synthetic_script_identity": (baseline.synthetic_script_identity),
                },
                {
                    "provider_id": candidate.provider_id,
                    "model_id": candidate.model_id,
                    "decode_configuration_hash": (candidate.decode_configuration_hash),
                },
            )
        return (
            {
                "provider_id": baseline.provider_id,
                "model_id": baseline.model_id,
                "decode_configuration_hash": (baseline.decode_configuration_hash),
            },
            {
                "provider_id": candidate.provider_id,
                "model_id": candidate.model_id,
                "decode_configuration_hash": (candidate.decode_configuration_hash),
            },
        )
    if kind is DifferenceKind.RUNNER_PROTOCOL:
        return baseline.runner_protocol_hash, candidate.runner_protocol_hash
    if kind is DifferenceKind.ARTIFACT_SCHEMA:
        return baseline.artifact_schema, candidate.artifact_schema
    if kind is DifferenceKind.ARTIFACT_KIND:
        return baseline.artifact_kind, candidate.artifact_kind
    raise AssertionError(f"未处理 DifferenceKind：{kind.value}")


def _identity_difference(
    *,
    kind: DifferenceKind,
    baseline: ArtifactIdentity,
    candidate: ArtifactIdentity,
    relation_kind: ArtifactRelationKind,
) -> IdentityDifference:
    baseline_value, candidate_value = _difference_values(
        kind=kind,
        baseline=baseline,
        candidate=candidate,
        relation_kind=relation_kind,
    )
    return IdentityDifference(
        kind=kind,
        baseline_value_sha256=canonical_sha256(baseline_value),
        candidate_value_sha256=canonical_sha256(candidate_value),
    )


def _actual_differences(
    *,
    relation_kind: ArtifactRelationKind,
    baseline: ArtifactIdentity,
    candidate: ArtifactIdentity,
) -> tuple[IdentityDifference, ...]:
    if relation_kind is ArtifactRelationKind.SYNTHETIC_TO_LIVE:
        kinds = (
            DifferenceKind.EXECUTION_IDENTITY,
            DifferenceKind.SELECTED_CASE_SET,
            DifferenceKind.TRACK,
            DifferenceKind.RUNNER_PROTOCOL,
        )
    else:
        kinds = (
            DifferenceKind.ARTIFACT,
            DifferenceKind.ARTIFACT_KIND,
            DifferenceKind.ARTIFACT_SCHEMA,
            DifferenceKind.DECODE_CONFIGURATION,
            DifferenceKind.LATENCY,
            DifferenceKind.MODEL,
            DifferenceKind.OUTPUT,
            DifferenceKind.PROVIDER,
            DifferenceKind.PROVIDER_REQUEST,
            DifferenceKind.PROVIDER_RUN,
            DifferenceKind.RESULT,
            DifferenceKind.RUNNER_PROTOCOL,
            DifferenceKind.TRACK,
            DifferenceKind.USAGE,
        )
    differences = tuple(
        _identity_difference(
            kind=kind,
            baseline=baseline,
            candidate=candidate,
            relation_kind=relation_kind,
        )
        for kind in kinds
    )
    return tuple(
        item
        for item in sorted(differences, key=lambda value: value.kind.value)
        if item.baseline_value_sha256 != item.candidate_value_sha256
    )


def _evaluate_declared_differences(
    *,
    relation_kind: ArtifactRelationKind,
    success_status: IdentityRelationStatus,
    baseline: ArtifactIdentity,
    candidate: ArtifactIdentity,
    declared_differences: DeclaredDifferences,
    comparability_key: ComparabilityKey,
    qualified_by_synthetic_ref: str | None = None,
) -> ArtifactRelationResult:
    actual = _actual_differences(
        relation_kind=relation_kind,
        baseline=baseline,
        candidate=candidate,
    )
    actual_by_kind = {item.kind: item for item in actual}
    declared_by_kind = {item.kind: item for item in declared_differences.differences}
    allowed_kinds = _RELATION_ALLOWED_DIFFERENCES[relation_kind]
    identity_problems: list[str] = []
    if declared_differences.relation_kind is not relation_kind:
        identity_problems.append("declared_differences.relation_kind")
    if declared_differences.baseline_artifact_ref != baseline.artifact_ref:
        identity_problems.append("declared_differences.baseline_artifact_ref")
    if declared_differences.candidate_artifact_ref != candidate.artifact_ref:
        identity_problems.append("declared_differences.candidate_artifact_ref")

    actual_kinds = set(actual_by_kind)
    declared_kinds = set(declared_by_kind)
    undeclared = tuple(
        sorted(actual_kinds - declared_kinds, key=lambda item: item.value)
    )
    overdeclared = tuple(
        sorted(
            (declared_kinds - actual_kinds) | (declared_kinds - allowed_kinds),
            key=lambda item: item.value,
        )
    )
    value_mismatch = tuple(
        sorted(
            (
                kind
                for kind in actual_kinds & declared_kinds
                if actual_by_kind[kind] != declared_by_kind[kind]
            ),
            key=lambda item: item.value,
        )
    )
    if identity_problems or undeclared or overdeclared or value_mismatch:
        return ArtifactRelationResult(
            relation_kind=relation_kind,
            status=IdentityRelationStatus.REJECTED,
            baseline_artifact_ref=baseline.artifact_ref,
            candidate_artifact_ref=candidate.artifact_ref,
            comparability_key=None,
            declared_differences=declared_differences,
            actual_differences=actual,
            failure_code=IdentityFailureCode.UNDECLARED_DIFFERENCE,
            message="实际差异必须与固定 allowlist 内的声明差异恰好相等。",
            identity_problems=tuple(identity_problems),
            undeclared_difference_kinds=undeclared,
            overdeclared_difference_kinds=overdeclared,
            value_mismatch_difference_kinds=value_mismatch,
        )
    return ArtifactRelationResult(
        relation_kind=relation_kind,
        status=success_status,
        baseline_artifact_ref=baseline.artifact_ref,
        candidate_artifact_ref=candidate.artifact_ref,
        comparability_key=comparability_key,
        declared_differences=declared_differences,
        actual_differences=actual,
        failure_code=None,
        message=(
            "Synthetic 37 已通过同套件前 21 条合同的 Live 执行资格。"
            if success_status is IdentityRelationStatus.ELIGIBLE
            else "两份 Live 工件满足冻结身份与声明差异合同，可以比较。"
        ),
        qualified_by_synthetic_ref=qualified_by_synthetic_ref,
    )


def _rejected_relation(
    *,
    relation_kind: ArtifactRelationKind,
    baseline: ArtifactIdentity,
    candidate: ArtifactIdentity,
    declared_differences: DeclaredDifferences,
    failure_code: IdentityFailureCode,
    message: str,
    identity_problems: tuple[str, ...] = (),
) -> ArtifactRelationResult:
    return ArtifactRelationResult(
        relation_kind=relation_kind,
        status=IdentityRelationStatus.REJECTED,
        baseline_artifact_ref=baseline.artifact_ref,
        candidate_artifact_ref=candidate.artifact_ref,
        comparability_key=None,
        declared_differences=declared_differences,
        actual_differences=(),
        failure_code=failure_code,
        message=message,
        identity_problems=identity_problems,
    )


class ExperimentMechanism(StrEnum):
    CONTEXT = "context"
    MEMORY = "memory"
    SECURITY = "security"
    RECOVERY = "recovery"
    PROVIDER = "provider"


class ComparabilityStatus(StrEnum):
    COMPARABLE = "comparable"
    INCOMPARABLE = "incomparable"
    INVALID = "invalid"


class AdmissionStatus(StrEnum):
    ADMITTED = "admitted"
    BLOCKED = "blocked"


_ALLOWED_DIFFERENCE_PATHS: dict[ExperimentMechanism, frozenset[str]] = {
    ExperimentMechanism.CONTEXT: frozenset(
        {
            "declared_settings.context_projection_policy_identity",
            "declared_settings.context_compression_policy_identity",
        }
    ),
    ExperimentMechanism.MEMORY: frozenset(
        {"declared_settings.runtime_memory_policy_identity"}
    ),
    ExperimentMechanism.SECURITY: frozenset(
        {
            "declared_settings.authorization_policy_identity",
            "declared_settings.capability_exposure_profile_identity",
        }
    ),
    ExperimentMechanism.RECOVERY: frozenset(
        {
            "declared_settings.fault_injection_policy_identity",
            "declared_settings.recovery_policy_identity",
        }
    ),
    ExperimentMechanism.PROVIDER: frozenset(
        {
            "provider_id",
            "model_id",
            "decode_configuration_hash",
        }
    ),
}


class ExperimentArm(BenchmarkModel):
    arm_id: StableId
    track: TrackKind
    suite_content_hash: Sha256
    fixture_hash: Sha256
    selected_case_ids: tuple[StableId, ...] = Field(min_length=1)
    user_input_hash: Sha256
    conditions_hash: Sha256
    capability_catalog_hash: Sha256
    authorization_policy_hash: Sha256
    verifier_registry_hash: Sha256
    gate_policy_hash: Sha256
    decode_configuration_hash: Sha256
    environment_hash: Sha256
    provider_id: StableId | None = None
    model_id: StableId | None = None
    repetition_count: int = Field(gt=0)
    declared_settings: dict[StableId, str]

    @field_validator("selected_case_ids")
    @classmethod
    def _case_ids_are_unique(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("实验组案例不得重复。")
        return value

    @model_validator(mode="after")
    def _provider_identity_matches_track(self) -> ExperimentArm:
        identities = (self.provider_id, self.model_id)
        if self.track is TrackKind.LIVE_PROVIDER and any(
            value is None for value in identities
        ):
            raise ValueError("live provider 实验组必须保存实际 provider/model 身份。")
        if self.track is TrackKind.SYNTHETIC and any(
            value is not None for value in identities
        ):
            raise ValueError("synthetic 实验组不得伪装 provider/model 身份。")
        return self


class ExperimentSpec(BenchmarkModel):
    experiment_id: StableId
    name: str = Field(min_length=1, max_length=200)
    mechanism: ExperimentMechanism
    control: ExperimentArm
    treatment: ExperimentArm
    declared_differences: tuple[str, ...] = Field(min_length=1)
    stability_threshold_profile: StableId
    idempotency_key: str = Field(min_length=1, max_length=300)
    evidence_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_mechanism_switch(self) -> ExperimentSpec:
        if self.control.arm_id == self.treatment.arm_id:
            raise ValueError("控制组与实验组必须使用不同 arm_id。")
        if len(self.declared_differences) != len(set(self.declared_differences)):
            raise ValueError("declared_differences 不得重复。")
        allowed = _ALLOWED_DIFFERENCE_PATHS[self.mechanism]
        unknown = sorted(set(self.declared_differences) - allowed)
        if unknown:
            raise ValueError(
                f"{self.mechanism.value} 机制不允许差异路径：{', '.join(unknown)}。"
            )
        if self.mechanism is ExperimentMechanism.PROVIDER and (
            self.control.track is not TrackKind.LIVE_PROVIDER
            or self.treatment.track is not TrackKind.LIVE_PROVIDER
        ):
            raise ValueError("provider 机制比较的两组都必须是 live provider。")
        return self


class IdentityComparison(BenchmarkModel):
    path: str = Field(min_length=1)
    control_value_sha256: Sha256
    treatment_value_sha256: Sha256
    matches: bool


class ComparabilityResult(BenchmarkModel):
    experiment_id: StableId
    status: ComparabilityStatus
    identity_comparisons: tuple[IdentityComparison, ...]
    declared_differences: tuple[str, ...]
    actual_differences: tuple[str, ...]
    undeclared_differences: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    reason_key: str = Field(min_length=1)
    relative_delta_allowed: bool


_COMPARISON_FIELDS = (
    "suite_content_hash",
    "fixture_hash",
    "selected_case_ids",
    "user_input_hash",
    "conditions_hash",
    "track",
    "provider_id",
    "model_id",
    "decode_configuration_hash",
    "capability_catalog_hash",
    "authorization_policy_hash",
    "verifier_registry_hash",
    "gate_policy_hash",
    "environment_hash",
    "repetition_count",
)


def _comparable_values(arm: ExperimentArm) -> dict[str, object]:
    values = {field: getattr(arm, field) for field in _COMPARISON_FIELDS}
    values.update(
        {
            f"declared_settings.{key}": value
            for key, value in arm.declared_settings.items()
        }
    )
    return values


def compare_experiment(spec: ExperimentSpec) -> ComparabilityResult:
    """以确定性纯函数计算可比性，不允许客户端重解释展示字段。"""

    control = _comparable_values(spec.control)
    treatment = _comparable_values(spec.treatment)
    paths = tuple(sorted(set(control) | set(treatment)))
    comparisons = tuple(
        IdentityComparison(
            path=path,
            control_value_sha256=canonical_sha256(control.get(path)),
            treatment_value_sha256=canonical_sha256(treatment.get(path)),
            matches=control.get(path) == treatment.get(path),
        )
        for path in paths
    )
    actual = tuple(item.path for item in comparisons if not item.matches)
    undeclared = tuple(path for path in actual if path not in spec.declared_differences)
    missing_declared = tuple(
        path for path in spec.declared_differences if path not in actual
    )

    if missing_declared:
        status = ComparabilityStatus.INVALID
        reason = "声明的机制开关没有形成真实差异。"
    elif undeclared:
        status = ComparabilityStatus.INCOMPARABLE
        reason = "实验组存在未声明或被冻结条件漂移。"
    else:
        status = ComparabilityStatus.COMPARABLE
        reason = "实验条件一致，可以进行机制比较。"
    return ComparabilityResult(
        experiment_id=spec.experiment_id,
        status=status,
        identity_comparisons=comparisons,
        declared_differences=spec.declared_differences,
        actual_differences=actual,
        undeclared_differences=undeclared,
        evidence_refs=spec.evidence_refs,
        reason_key=reason,
        relative_delta_allowed=status is ComparabilityStatus.COMPARABLE,
    )


class ExperimentRecord(BenchmarkModel):
    spec: ExperimentSpec
    comparability: ComparabilityResult
    control_run_ids: tuple[str, ...] = ()
    treatment_run_ids: tuple[str, ...] = ()


class ExperimentService:
    """实验创建与运行绑定的幂等应用服务。"""

    def __init__(self) -> None:
        self._records: dict[str, ExperimentRecord] = {}
        self._claims: dict[str, tuple[Sha256, str]] = {}

    def create(self, spec: ExperimentSpec) -> ExperimentRecord:
        spec_hash = canonical_sha256(
            spec.model_dump(mode="json", exclude={"idempotency_key"})
        )
        claim = self._claims.get(spec.idempotency_key)
        if claim is not None:
            claimed_hash, experiment_id = claim
            if claimed_hash != spec_hash:
                raise ValueError("幂等键已经绑定不同实验。")
            return self._records[experiment_id]
        existing = self._records.get(spec.experiment_id)
        if existing is not None:
            raise ValueError("实验标识已经由其他幂等键绑定。")
        record = ExperimentRecord(
            spec=spec,
            comparability=compare_experiment(spec),
        )
        self._records[spec.experiment_id] = record
        self._claims[spec.idempotency_key] = (spec_hash, spec.experiment_id)
        return record

    def bind_run(
        self,
        *,
        experiment_id: str,
        arm_id: str,
        run_id: str,
    ) -> ExperimentRecord:
        record = self._records[experiment_id]
        if arm_id == record.spec.control.arm_id:
            control = _append_unique_run(record.control_run_ids, run_id)
            treatment = record.treatment_run_ids
        elif arm_id == record.spec.treatment.arm_id:
            control = record.control_run_ids
            treatment = _append_unique_run(record.treatment_run_ids, run_id)
        else:
            raise ValueError(f"实验不存在 arm：{arm_id}。")
        updated = record.model_copy(
            update={
                "control_run_ids": control,
                "treatment_run_ids": treatment,
            }
        )
        self._records[experiment_id] = updated
        return updated

    def get(self, experiment_id: str) -> ExperimentRecord:
        return self._records[experiment_id]

    def list(self) -> tuple[ExperimentRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))


def _append_unique_run(run_ids: tuple[str, ...], run_id: str) -> tuple[str, ...]:
    if re.fullmatch(_RUN_ID_PATTERN, run_id) is None:
        raise ValueError("实验运行 ID 格式非法。")
    if run_id in run_ids:
        return run_ids
    return (*run_ids, run_id)


class ModelCandidateEvidence(BenchmarkModel):
    candidate_id: StableId
    requested_model_ref: str = Field(min_length=1, max_length=300)
    probe_succeeded: bool
    actual_provider_id: StableId | None
    actual_model_id: str | None = Field(default=None, min_length=1, max_length=300)
    fallback_used: bool
    replay_available: bool
    usage_available: bool
    cost_available: bool
    error_code: str | None = Field(default=None, min_length=1, max_length=300)


class ComparisonAdmissionInput(BenchmarkModel):
    iteration_state: StableId
    code_hash: Sha256
    suite_hash: Sha256
    fixture_hash: Sha256
    case_set_hash: Sha256
    per_case_budgets_hash: Sha256
    capability_catalog_hash: Sha256
    authorization_policy_hash: Sha256
    decode_configuration_hash: Sha256
    environment_hash: Sha256
    all_system_defects_processed: bool
    symmetry_gates_passed: bool
    benchmark_verifier_defects_closed: bool
    core_gates_passed: bool
    candidates: tuple[ModelCandidateEvidence, ...] = Field(min_length=1)

    @field_validator("candidates")
    @classmethod
    def _candidate_ids_are_unique(
        cls,
        value: tuple[ModelCandidateEvidence, ...],
    ) -> tuple[ModelCandidateEvidence, ...]:
        ids = [item.candidate_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("模型比较候选不得重复。")
        return value


class ModelComparisonAdmission(BenchmarkModel):
    status: AdmissionStatus
    admitted: bool
    code_hash: Sha256
    suite_hash: Sha256
    fixture_hash: Sha256
    case_set_hash: Sha256
    per_case_budgets_hash: Sha256
    capability_catalog_hash: Sha256
    authorization_policy_hash: Sha256
    decode_configuration_hash: Sha256
    environment_hash: Sha256
    candidates: tuple[ModelCandidateEvidence, ...]
    blocked_reasons: tuple[str, ...]
    ranking_candidate_ids: tuple[StableId, ...]


def evaluate_model_comparison_admission(
    request: ComparisonAdmissionInput,
) -> ModelComparisonAdmission:
    """按冻结条件、闭环门禁和候选污染证据决定比较准入。"""

    reasons: list[str] = []
    if request.iteration_state != "ready_for_comparison":
        reasons.append("首轮迭代尚未达到可比较状态。")
    if not request.all_system_defects_processed:
        reasons.append("仍有系统缺陷未确认关闭。")
    if not request.symmetry_gates_passed:
        reasons.append("问题关联对称性门禁未通过。")
    if not request.benchmark_verifier_defects_closed:
        reasons.append("仍有当前套件下的基准或校验器缺陷未闭环。")
    if not request.core_gates_passed:
        reasons.append("核心硬门禁未通过。")
    for candidate in request.candidates:
        prefix = f"候选 {candidate.candidate_id}"
        if not candidate.probe_succeeded:
            reasons.append(f"{prefix} 的提供商探测失败。")
        if candidate.actual_provider_id is None or candidate.actual_model_id is None:
            reasons.append(f"{prefix} 缺少实际 provider/model 身份。")
        if candidate.fallback_used:
            reasons.append(f"{prefix} 发生 fallback 污染。")
        if not candidate.replay_available:
            reasons.append(f"{prefix} 缺少回放证据。")
        if not candidate.usage_available:
            reasons.append(f"{prefix} 缺少用量证据。")
        if not candidate.cost_available:
            reasons.append(f"{prefix} 缺少费用证据。")
        if candidate.error_code is not None:
            reasons.append(f"{prefix} 存在执行错误：{candidate.error_code}。")
    admitted = not reasons
    return ModelComparisonAdmission(
        status=AdmissionStatus.ADMITTED if admitted else AdmissionStatus.BLOCKED,
        admitted=admitted,
        code_hash=request.code_hash,
        suite_hash=request.suite_hash,
        fixture_hash=request.fixture_hash,
        case_set_hash=request.case_set_hash,
        per_case_budgets_hash=request.per_case_budgets_hash,
        capability_catalog_hash=request.capability_catalog_hash,
        authorization_policy_hash=request.authorization_policy_hash,
        decode_configuration_hash=request.decode_configuration_hash,
        environment_hash=request.environment_hash,
        candidates=request.candidates,
        blocked_reasons=tuple(reasons),
        ranking_candidate_ids=(
            tuple(item.candidate_id for item in request.candidates) if admitted else ()
        ),
    )
