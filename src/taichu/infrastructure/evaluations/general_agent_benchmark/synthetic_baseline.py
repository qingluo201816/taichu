"""Synthetic 37 条准入基线的不可变冻结与活动目录发布。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.experiments import (
    ArtifactIdentity,
    CaseContractIdentity,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    CaseConclusion,
    GateKind,
    GateStatus,
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    ProviderExecutionState,
    SuiteArtifact,
    SuiteConclusion,
    SuiteRun,
    SuiteRunCounts,
    SuiteRunLifecycle,
)
from taichu.application.evaluations.general_agent_benchmark.suite_artifact_builder import (
    build_synthetic_suite_artifact,
    stable_suite_drift_paths,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredSuiteSpec,
)
from taichu.application.evaluations.general_agent_benchmark.synthetic_suite import (
    SyntheticSuiteBaselineResult,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.artifact_repository import (
    GeneralAgentBenchmarkArtifactRepository,
)

_CATALOG_ID = "benchmark-baseline-catalog"
_LEGACY_INDEX_ID = "synthetic-passed-baseline"
_BASELINE_SCHEMA = "taichu.general_agent_benchmark.synthetic-baseline@2"
_CATALOG_SCHEMA = "taichu.general_agent_benchmark.baseline-catalog@2"


class BaselineManifest(BenchmarkModel):
    """单次 Synthetic 准入的完整不可变清单。"""

    schema_: Literal[
        "taichu.general_agent_benchmark.synthetic-baseline@2"
    ] = Field(alias="schema")
    identity: ArtifactIdentity
    suite_run: SuiteRun
    suite_artifact: SuiteArtifact
    counts: SuiteRunCounts


class SyntheticBaselineFreezer:
    """仅发布两次隔离运行稳定且 37/37 六门禁通过的基线。"""

    def __init__(
        self,
        repository: GeneralAgentBenchmarkArtifactRepository,
    ) -> None:
        self._repository = repository

    def freeze(
        self,
        result: SyntheticSuiteBaselineResult,
        *,
        repeated_result: SyntheticSuiteBaselineResult,
        suite: AuthoredSuiteSpec,
        capability_catalog_hash: str,
        oracle_rule_set_hash: str,
        runtime_code_snapshot_hash: str,
        runner_protocol_hash: str,
    ) -> dict[str, Any]:
        self._validate_passed_result(
            result,
            repeated_result=repeated_result,
            suite=suite,
        )
        built = build_synthetic_suite_artifact(suite=suite, result=result)
        if (
            not built.complete_admission
            or built.counts.total != 37
            or built.counts.passed != 37
            or built.counts.failed
            or built.counts.invalid
        ):
            raise ValueError("Synthetic 工件没有达到完整 37/37 准入条件。")

        selected_case_ids = built.expected_case_ids
        baseline_id = (
            "synthetic_baseline_"
            + canonical_sha256(
                {
                    "suite_content_hash": suite.content_hash,
                    "runtime_config_hash": result.runtime_config_identity,
                    "stable_result_hash": result.stable_result_hash,
                }
            )[:32]
        )
        artifact_ref = f"runs/{baseline_id}.json"
        run_id = (
            "benchmark_run_19700101T000000Z_"
            + result.stable_result_hash[:12]
        )
        artifact_content = {
            **built.artifact.model_dump(
                mode="python",
                exclude={"artifact_hash", "run_id"},
            ),
            "run_id": run_id,
        }
        artifact = SuiteArtifact(
            **artifact_content,
            artifact_hash=canonical_sha256(artifact_content),
        )
        run = SuiteRun(
            run_id=run_id,
            revision=37,
            lifecycle=SuiteRunLifecycle.COMPLETED,
            conclusion=SuiteConclusion.PASSED,
            suite_content_hash=suite.content_hash,
            selected_case_ids=selected_case_ids,
            track=TrackKind.SYNTHETIC,
            provider_state=ProviderExecutionState.NOT_APPLICABLE,
            case_row_refs=tuple(
                f"{artifact.artifact_id}#/case_rows/{position}"
                for position in range(len(artifact.case_rows))
            ),
            pending_case_ids=(),
            terminal_artifact_ref=artifact.artifact_id,
        )
        identity = ArtifactIdentity.create(
            selected_case_ids=selected_case_ids,
            case_contracts=tuple(
                CaseContractIdentity(
                    case_id=case.case_id,
                    contract_hash=canonical_sha256(case),
                )
                for case in suite.cases
                if TrackKind.SYNTHETIC in case.applicable_tracks
            ),
            artifact_schema=_BASELINE_SCHEMA,
            artifact_kind="synthetic_baseline",
            artifact_ref=artifact_ref,
            artifact_content_hash=artifact.artifact_hash,
            suite_content_hash=suite.content_hash,
            track=TrackKind.SYNTHETIC,
            fixture_snapshot_hash=suite.fixture.snapshot_id.removeprefix(
                "fixture_"
            ),
            capability_catalog_hash=capability_catalog_hash,
            oracle_rule_set_hash=oracle_rule_set_hash,
            runtime_config_hash=result.runtime_config_identity,
            runtime_code_snapshot_hash=runtime_code_snapshot_hash,
            runner_protocol_hash=runner_protocol_hash,
            synthetic_script_identity=canonical_sha256(
                [
                    {
                        "case_id": case.case_id,
                        "scripted_steps": [
                            step.model_dump(mode="json")
                            for step in case.scripted_steps
                        ],
                    }
                    for case in suite.cases
                    if TrackKind.SYNTHETIC in case.applicable_tracks
                ]
            ),
            synthetic_admission_passed=True,
            result_hash=result.stable_result_hash,
        )
        manifest = BaselineManifest(
            schema=_BASELINE_SCHEMA,
            identity=identity,
            suite_run=run,
            suite_artifact=artifact,
            counts=built.counts,
        )
        content = manifest.model_dump(mode="json", by_alias=True)
        try:
            existing = self._repository.read("runs", baseline_id)
        except FileNotFoundError:
            existing = None
        if existing is not None and _same_stable_freeze_identity(
            existing,
            content,
        ):
            self._publish_catalog(artifact_ref)
            return existing
        frozen = self._repository.append_immutable(
            collection="runs",
            object_id=baseline_id,
            payload={
                **content,
                "manifest_hash": canonical_sha256(content),
            },
        )
        self._publish_catalog(artifact_ref)
        return frozen

    def _publish_catalog(self, new_active_ref: str) -> None:
        history_refs: list[str] = []
        try:
            current = self._repository.read("indexes", _CATALOG_ID)
        except FileNotFoundError:
            current = None
        if current is not None:
            if current.get("schema") != _CATALOG_SCHEMA:
                raise ValueError("已有 Benchmark 基线目录 schema 不受支持。")
            current_hash = current.get("catalog_hash")
            if canonical_sha256(
                {
                    key: value
                    for key, value in current.items()
                    if key != "catalog_hash"
                }
            ) != current_hash:
                raise ValueError("已有 Benchmark 基线目录内容哈希不一致。")
            old_active = current.get("active_synthetic_ref")
            raw_history = current.get("history_refs")
            if not isinstance(old_active, str) or not isinstance(
                raw_history,
                list,
            ):
                raise ValueError("已有 Benchmark 基线目录结构非法。")
            history_refs.extend(
                ref for ref in (old_active, *raw_history) if ref != new_active_ref
            )
        else:
            try:
                legacy = self._repository.read("indexes", _LEGACY_INDEX_ID)
            except FileNotFoundError:
                legacy = None
            if legacy is not None:
                legacy_ref = legacy.get("baseline_ref")
                if not isinstance(legacy_ref, str) or not legacy_ref:
                    raise ValueError("历史 23 条基线索引缺少 baseline_ref。")
                history_refs.append(legacy_ref)

        history_refs = list(dict.fromkeys(history_refs))
        catalog_content = {
            "schema": _CATALOG_SCHEMA,
            "active_synthetic_ref": new_active_ref,
            "history_refs": history_refs,
        }
        self._repository.replace_index(
            _CATALOG_ID,
            {
                **catalog_content,
                "catalog_hash": canonical_sha256(catalog_content),
            },
        )

    @staticmethod
    def _validate_passed_result(
        result: SyntheticSuiteBaselineResult,
        *,
        repeated_result: SyntheticSuiteBaselineResult,
        suite: AuthoredSuiteSpec,
    ) -> None:
        expected_case_ids = tuple(
            case.case_id
            for case in suite.cases
            if TrackKind.SYNTHETIC in case.applicable_tracks
        )
        if len(expected_case_ids) != 37:
            raise ValueError("活动 Suite 的 Synthetic 适用集必须精确为 37 条。")
        for label, candidate in (
            ("首次", result),
            ("复跑", repeated_result),
        ):
            problems = _admission_problems(
                candidate,
                suite=suite,
                expected_case_ids=expected_case_ids,
            )
            if problems:
                raise ValueError(
                    f"{label} Synthetic 结果不满足 37/37 准入："
                    + "；".join(problems)
                )
        if result.runtime_config_identity != repeated_result.runtime_config_identity:
            raise ValueError("两次隔离运行的 Runtime 配置身份不一致。")
        drift_paths = stable_suite_drift_paths(result, repeated_result)
        if drift_paths:
            raise ValueError(
                "两次隔离运行存在稳定结果漂移：" + "、".join(drift_paths)
            )


def _same_stable_freeze_identity(
    existing: dict[str, Any],
    candidate: dict[str, Any],
) -> bool:
    declared_manifest_hash = existing.get("manifest_hash")
    calculated_manifest_hash = canonical_sha256(
        {
            key: value
            for key, value in existing.items()
            if key != "manifest_hash"
        }
    )
    if declared_manifest_hash != calculated_manifest_hash:
        raise ValueError("已冻结 Synthetic 基线的 manifest_hash 不一致。")
    existing_identity = existing.get("identity")
    candidate_identity = candidate.get("identity")
    if not isinstance(existing_identity, dict) or not isinstance(
        candidate_identity,
        dict,
    ):
        return False
    stable_existing_identity = {
        key: value
        for key, value in existing_identity.items()
        if key != "artifact_content_hash"
    }
    stable_candidate_identity = {
        key: value
        for key, value in candidate_identity.items()
        if key != "artifact_content_hash"
    }
    existing_run = existing.get("suite_run")
    candidate_run = candidate.get("suite_run")
    return (
        existing.get("schema") == candidate.get("schema")
        and existing.get("counts") == candidate.get("counts")
        and isinstance(existing_run, dict)
        and isinstance(candidate_run, dict)
        and existing_run.get("selected_case_ids")
        == candidate_run.get("selected_case_ids")
        and canonical_sha256(stable_existing_identity)
        == canonical_sha256(stable_candidate_identity)
    )


def _admission_problems(
    candidate: SyntheticSuiteBaselineResult,
    *,
    suite: AuthoredSuiteSpec,
    expected_case_ids: tuple[str, ...],
) -> tuple[str, ...]:
    problems: list[str] = []
    if not candidate.complete:
        problems.append("complete=false")
    if candidate.suite_id != suite.suite_id:
        problems.append("suite_id 不一致")
    if candidate.suite_content_hash != suite.content_hash:
        problems.append("suite_content_hash 不一致")
    if tuple(case.case_id for case in candidate.cases) != expected_case_ids:
        problems.append("案例集合或顺序不一致")
    if (
        candidate.case_count != 37
        or candidate.passed_case_count != 37
        or candidate.failed_case_count != 0
        or len(candidate.cases) != 37
    ):
        problems.append(
            "计数="
            f"{candidate.passed_case_count}/{candidate.case_count}"
            f"，failed={candidate.failed_case_count}"
        )
    for case in candidate.cases:
        case_problems: list[str] = []
        if case.conclusion is not CaseConclusion.PASSED:
            case_problems.append(f"结论={case.conclusion.value}")
        if case.case_observation is None:
            case_problems.append("缺少观察")
        if case.normalization_artifact is None:
            case_problems.append("缺少规范化工件")
        if not case.evidence_ids:
            case_problems.append("缺少证据引用")
        if (
            len(case.gates) != len(GateKind)
            or {gate.gate_kind for gate in case.gates} != set(GateKind)
        ):
            case_problems.append(f"门禁种类数={len(case.gates)}")
        failed_gates = tuple(
            gate.gate_kind.value
            for gate in case.gates
            if gate.status is not GateStatus.PASSED
        )
        if failed_gates:
            case_problems.append("未通过门禁=" + ",".join(failed_gates))
        if case_problems:
            problems.append(f"{case.case_id}({','.join(case_problems)})")
    return tuple(problems)
