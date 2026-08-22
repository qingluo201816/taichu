"""需求 16.1-16.3：从固定权威索引只读恢复评测查询视图。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.closure import (
    ModelComparisonRecord,
)
from taichu.application.evaluations.general_agent_benchmark.experiments import (
    AdmissionStatus,
    ArtifactIdentity,
    ModelCandidateEvidence,
    ModelComparisonAdmission,
)
from taichu.application.evaluations.general_agent_benchmark.first_live import (
    FirstLiveArtifact,
    FirstLiveIterationManifest,
    FirstLiveIterationState,
)
from taichu.application.evaluations.general_agent_benchmark.hydration import (
    ArtifactHydrationStatus,
    BenchmarkQueryHydration,
    HydratedSuiteLineage,
    HydratedSyntheticArtifact,
    QueryHydrationStatus,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    CaseConclusion,
    GateKind,
    GateStatus,
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    CaseExecutionState,
    CaseResultRow,
    EvidenceAvailability,
    EvidenceBundle,
    EvidenceBundleIdentity,
    FrozenCapabilityInvocationEvidence,
    FrozenCaseEvidenceDetails,
    FrozenNormalizationActionEvidence,
    ProviderExecutionState,
    SuiteArtifact,
    SuiteConclusion,
    SuiteRun,
    SuiteRunLifecycle,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.artifact_repository import (
    GeneralAgentBenchmarkArtifactRepository,
)

_INDEX_IDS = (
    "synthetic-passed-baseline",
    "deepseek-first-live",
    "deepseek-first-live-classification",
)
_COMPARISON_INDEX_ID = "model-comparison-latest"
_BASELINE_CATALOG_INDEX_ID = "benchmark-baseline-catalog"
_REF_PATTERN = re.compile(
    r"^(runs|iterations|comparisons)/([a-z][a-z0-9_]{2,127})\.json$"
)


def load_frozen_benchmark_query_snapshot(
    repository: GeneralAgentBenchmarkArtifactRepository,
) -> BenchmarkQueryHydration:
    """只读取固定索引及其直接引用；各工件独立失败，不扫描目录补历史。"""
    source_refs = tuple(f"indexes/{item}.json" for item in _INDEX_IDS)
    baseline_catalog_path = (
        repository.root / "indexes" / f"{_BASELINE_CATALOG_INDEX_ID}.json"
    )
    if baseline_catalog_path.exists():
        source_refs += (f"indexes/{_BASELINE_CATALOG_INDEX_ID}.json",)
    if (repository.root / "indexes" / f"{_COMPARISON_INDEX_ID}.json").exists():
        source_refs += (f"indexes/{_COMPARISON_INDEX_ID}.json",)

    problems: list[str] = []
    synthetic_entries: tuple[HydratedSyntheticArtifact, ...] = ()
    suite_run: SuiteRun | None = None
    suite_artifact: SuiteArtifact | None = None
    try:
        synthetic_entries = _load_synthetic_entries(repository.root)
        primary = next(
            (
                entry
                for entry in synthetic_entries
                if entry.lineage is HydratedSuiteLineage.CURRENT
                and entry.status is ArtifactHydrationStatus.HYDRATED
            ),
            next(
                (
                    entry
                    for entry in synthetic_entries
                    if entry.suite_run is not None
                    and entry.suite_artifact is not None
                ),
                None,
            ),
        )
        if primary is not None:
            suite_run = primary.suite_run
            suite_artifact = primary.suite_artifact
        problems.extend(
            problem
            for entry in synthetic_entries
            if entry.suite_run is None or entry.suite_artifact is None
            for problem in entry.problems
        )
    except (KeyError, OSError, TypeError, ValueError) as error:
        problems.append(
            f"Synthetic 工件不可用：{type(error).__name__}：{error}"
        )

    manifest: FirstLiveIterationManifest | None = None
    artifact: FirstLiveArtifact | None = None
    comparison: ModelComparisonRecord | None = None
    try:
        live_index = _read_json(
            repository.root / "indexes" / f"{_INDEX_IDS[1]}.json"
        )
        classification_index = _read_json(
            repository.root / "indexes" / f"{_INDEX_IDS[2]}.json"
        )
        manifest, artifact, comparison = _load_first_live(
            repository.root,
            live_index,
            classification_index,
        )
        comparison = _load_frozen_model_comparison(
            repository.root,
            artifact,
            manifest,
        ) or comparison
    except (KeyError, OSError, TypeError, ValueError) as error:
        problems.append(
            f"Live/比较工件不可用：{type(error).__name__}：{error}"
        )

    has_current = any(
        entry.lineage is HydratedSuiteLineage.CURRENT
        and entry.status is ArtifactHydrationStatus.HYDRATED
        for entry in synthetic_entries
    )
    any_available = (
        any(
            entry.suite_run is not None and entry.suite_artifact is not None
            for entry in synthetic_entries
        )
        or manifest is not None
    )
    status = (
        QueryHydrationStatus.AVAILABLE
        if has_current and manifest is not None and not problems
        else (
            QueryHydrationStatus.PARTIAL
            if any_available
            else QueryHydrationStatus.UNAVAILABLE
        )
    )
    return BenchmarkQueryHydration(
        status=status,
        source_refs=source_refs,
        problems=tuple(problems),
        suite_run=suite_run,
        suite_artifact=suite_artifact,
        first_live_iteration=manifest,
        first_live_artifact=artifact,
        blocked_comparison=comparison,
        synthetic_entries=synthetic_entries,
    )


def _load_frozen_model_comparison(
    root: Path,
    artifact: FirstLiveArtifact,
    manifest: FirstLiveIterationManifest,
) -> ModelComparisonRecord | None:
    index_path = root / "indexes" / f"{_COMPARISON_INDEX_ID}.json"
    if not index_path.exists():
        return None
    index = _read_json(index_path)
    if (
        index.get("schema")
        != "taichu.general_agent_benchmark.model-comparison-index@1"
    ):
        raise ValueError("多模型比较权威索引 schema 不受支持。")
    comparison_ref = _required_string(index, "comparison_ref")
    envelope = _read_indexed_ref(root, comparison_ref, "comparisons")
    if (
        envelope.get("schema")
        != "taichu.general_agent_benchmark.model-comparison@1"
    ):
        raise ValueError("多模型比较工件 schema 不受支持。")
    record_payload = _without(envelope, "schema")
    record_hash = _required_string(record_payload, "record_hash")
    if canonical_sha256(_without(record_payload, "record_hash")) != record_hash:
        raise ValueError("多模型比较工件哈希不一致。")
    if index.get("record_hash") != record_hash:
        raise ValueError("多模型比较索引与工件哈希不一致。")
    record = ModelComparisonRecord.model_validate(record_payload)
    if not record.admitted or record.first_live_artifact_ref != artifact.artifact_id:
        raise ValueError("多模型比较未通过正式准入或首轮引用不一致。")
    if (
        record.admission.code_hash != manifest.code_hash
        or record.admission.suite_hash != manifest.suite_hash
        or record.admission.fixture_hash != manifest.fixture_hash
        or record.admission.capability_catalog_hash
        != manifest.capability_catalog_hash
    ):
        raise ValueError("多模型比较身份与首轮冻结身份不一致。")
    ranked = tuple(
        item.candidate_id
        for item in record.candidate_results
        if item.eligible_for_ranking
    )
    if len(ranked) < 2 or set(ranked) != set(record.ranking_candidate_ids):
        raise ValueError("多模型比较缺少至少两个有效候选或排名引用不一致。")
    if (
        record.catalog_model_count <= 0
        or record.covered_model_count != record.catalog_model_count
        or record.covered_model_count != len(record.candidate_results)
        or record.full_suite_model_count != len(ranked)
        or record.blocked_model_count
        != sum(
            item.qualification.value == "blocked"
            for item in record.candidate_results
        )
    ):
        raise ValueError("多模型比较没有完整覆盖模型目录或覆盖统计不一致。")
    return record


def _load_synthetic_entries(
    root: Path,
) -> tuple[HydratedSyntheticArtifact, ...]:
    catalog_path = root / "indexes" / f"{_BASELINE_CATALOG_INDEX_ID}.json"
    if not catalog_path.exists():
        index = _read_json(root / "indexes" / f"{_INDEX_IDS[0]}.json")
        return (_hydrate_historical_v1(root, index),)

    catalog = _read_json(catalog_path)
    if (
        catalog.get("schema")
        != "taichu.general_agent_benchmark.baseline-catalog@2"
    ):
        raise ValueError("Benchmark 基线目录 schema 不受支持。")
    catalog_hash = _required_string(catalog, "catalog_hash")
    if canonical_sha256(_without(catalog, "catalog_hash")) != catalog_hash:
        raise ValueError("Benchmark 基线目录内容哈希不一致。")
    active_ref = _required_string(catalog, "active_synthetic_ref")
    history_refs_raw = catalog.get("history_refs")
    if not isinstance(history_refs_raw, list):
        raise ValueError("Benchmark 基线目录 history_refs 格式非法。")
    history_refs = tuple(
        _require_non_empty_string(item, "history_refs")
        for item in history_refs_raw
    )
    if active_ref in history_refs or len(history_refs) != len(set(history_refs)):
        raise ValueError("Benchmark 基线目录引用不得重复。")
    return (
        _hydrate_synthetic_ref(
            root,
            active_ref,
            lineage=HydratedSuiteLineage.CURRENT,
        ),
        *(
            _hydrate_synthetic_ref(
                root,
                history_ref,
                lineage=HydratedSuiteLineage.HISTORICAL,
            )
            for history_ref in history_refs
        ),
    )


def _hydrate_synthetic_ref(
    root: Path,
    artifact_ref: str,
    *,
    lineage: HydratedSuiteLineage,
) -> HydratedSyntheticArtifact:
    try:
        if lineage is HydratedSuiteLineage.CURRENT:
            envelope = _read_indexed_ref(root, artifact_ref, "runs")
            if (
                envelope.get("schema")
                == "taichu.general_agent_benchmark.synthetic-baseline@1"
            ):
                return _current_identity_substitution_forbidden(
                    artifact_ref,
                    envelope,
                )
        return (
            _hydrate_current_v2(root, artifact_ref)
            if lineage is HydratedSuiteLineage.CURRENT
            else _hydrate_historical_ref(root, artifact_ref)
        )
    except (KeyError, OSError, TypeError, ValueError) as error:
        return HydratedSyntheticArtifact(
            lineage=lineage,
            status=(
                ArtifactHydrationStatus.UNAVAILABLE_ARTIFACT_IDENTITY_MISMATCH
            ),
            source_ref=artifact_ref,
            identity=ArtifactIdentity(artifact_ref=artifact_ref),
            problems=(
                f"{lineage.value} Synthetic 工件身份不可用："
                f"{type(error).__name__}：{error}",
            ),
        )


def _current_identity_substitution_forbidden(
    artifact_ref: str,
    envelope: dict[str, Any],
) -> HydratedSyntheticArtifact:
    """保留历史工件自身可证明的身份，不用当前身份字段冒充 @2。"""

    identity = ArtifactIdentity(
        artifact_schema=(
            envelope.get("schema")
            if isinstance(envelope.get("schema"), str)
            else None
        ),
        artifact_kind="synthetic_baseline",
        artifact_ref=artifact_ref,
        artifact_content_hash=(
            envelope.get("artifact_hash")
            if isinstance(envelope.get("artifact_hash"), str)
            else None
        ),
        suite_content_hash=(
            envelope.get("suite_content_hash")
            if isinstance(envelope.get("suite_content_hash"), str)
            else None
        ),
        track=TrackKind.SYNTHETIC,
    )
    return HydratedSyntheticArtifact(
        lineage=HydratedSuiteLineage.CURRENT,
        status=(
            ArtifactHydrationStatus.UNAVAILABLE_IDENTITY_SUBSTITUTION_FORBIDDEN
        ),
        source_ref=artifact_ref,
        identity=identity,
        problems=(
            "活动 Synthetic 引用指向历史 @1 工件；禁止使用当前 @2 "
            "身份字段补齐或替代历史身份。",
        ),
    )


def _hydrate_current_v2(
    root: Path,
    artifact_ref: str,
) -> HydratedSyntheticArtifact:
    envelope = _read_indexed_ref(root, artifact_ref, "runs")
    if (
        envelope.get("schema")
        != "taichu.general_agent_benchmark.synthetic-baseline@2"
    ):
        raise ValueError("活动 Synthetic 基线不是 @2 工件。")
    manifest_hash = _required_string(envelope, "manifest_hash")
    if canonical_sha256(_without(envelope, "manifest_hash")) != manifest_hash:
        raise ValueError("活动 Synthetic 基线 Manifest 哈希不一致。")
    identity = ArtifactIdentity.model_validate(envelope.get("identity"))
    run = SuiteRun.model_validate(envelope.get("suite_run"))
    artifact = SuiteArtifact.model_validate(envelope.get("suite_artifact"))
    missing = _missing_current_identity_fields(identity)
    if missing:
        raise ValueError(
            "活动 Synthetic 基线身份不完整：" + "、".join(missing)
        )
    if (
        identity.artifact_ref != artifact_ref
        or identity.artifact_content_hash != artifact.artifact_hash
        or identity.suite_content_hash != run.suite_content_hash
        or identity.selected_case_ids != run.selected_case_ids
        or identity.selected_case_ids
        != tuple(row.case_id for row in artifact.case_rows)
        or identity.selected_case_set_hash
        != canonical_sha256(identity.selected_case_ids)
        or identity.selected_case_contract_hash
        != canonical_sha256(identity.case_contracts)
        or identity.track is not TrackKind.SYNTHETIC
        or identity.synthetic_admission_passed is not True
        or artifact.conclusion is not SuiteConclusion.PASSED
    ):
        raise ValueError("活动 Synthetic 基线身份与子工件不一致。")
    return HydratedSyntheticArtifact(
        lineage=HydratedSuiteLineage.CURRENT,
        status=ArtifactHydrationStatus.HYDRATED,
        source_ref=artifact_ref,
        identity=identity,
        suite_run=run,
        suite_artifact=artifact,
    )


def _hydrate_historical_ref(
    root: Path,
    artifact_ref: str,
) -> HydratedSyntheticArtifact:
    envelope = _read_indexed_ref(root, artifact_ref, "runs")
    if (
        envelope.get("schema")
        == "taichu.general_agent_benchmark.synthetic-baseline@2"
    ):
        hydrated = _hydrate_current_v2(root, artifact_ref)
        return hydrated.model_copy(
            update={"lineage": HydratedSuiteLineage.HISTORICAL}
        )
    if (
        envelope.get("schema")
        == "taichu.general_agent_benchmark.synthetic-baseline@1"
    ):
        index = {
            "schema": "taichu.general_agent_benchmark.synthetic-baseline-index@1",
            "baseline_ref": artifact_ref,
            "artifact_hash": envelope.get("artifact_hash"),
            "stable_result_hash": envelope.get("stable_result_hash"),
            "suite_content_hash": envelope.get("suite_content_hash"),
        }
        return _hydrate_historical_v1(root, index)
    raise ValueError("历史 Synthetic 引用不是受支持的只读 @1 工件。")


def _hydrate_historical_v1(
    root: Path,
    index: dict[str, Any],
) -> HydratedSyntheticArtifact:
    run, artifact = _load_synthetic_run(root, index)
    baseline_ref = _required_string(index, "baseline_ref")
    baseline = _read_indexed_ref(root, baseline_ref, "runs")
    identity = ArtifactIdentity(
        artifact_schema=_required_string(baseline, "schema"),
        artifact_kind="synthetic_baseline",
        artifact_ref=baseline_ref,
        artifact_content_hash=_required_string(baseline, "artifact_hash"),
        suite_content_hash=_required_string(baseline, "suite_content_hash"),
        selected_case_ids=run.selected_case_ids,
        selected_case_set_hash=canonical_sha256(run.selected_case_ids),
        track=TrackKind.SYNTHETIC,
        fixture_snapshot_hash=_required_string(
            baseline,
            "fixture_snapshot_id",
        ).removeprefix("fixture_"),
        capability_catalog_hash=_required_string(
            baseline,
            "capability_catalog_hash",
        ),
        runtime_config_hash=_required_string(
            baseline,
            "runtime_config_identity",
        ),
        result_hash=_required_string(baseline, "run_result_hash"),
        synthetic_admission_passed=True,
    )
    missing = (
        "case_contracts",
        "selected_case_contract_hash",
        "oracle_rule_set_hash",
        "runtime_code_snapshot_hash",
        "runner_protocol_hash",
        "synthetic_script_identity",
    )
    return HydratedSyntheticArtifact.historical_incomplete(
        source_ref=baseline_ref,
        identity=identity,
        missing_identity_fields=missing,
        suite_run=run,
        suite_artifact=artifact,
    )


def _missing_current_identity_fields(identity: ArtifactIdentity) -> tuple[str, ...]:
    required = (
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
        "synthetic_script_identity",
        "synthetic_admission_passed",
        "result_hash",
    )
    missing = tuple(
        field
        for field in required
        if getattr(identity, field) is None
    )
    if not identity.selected_case_ids:
        missing += ("selected_case_ids",)
    if not identity.case_contracts:
        missing += ("case_contracts",)
    return missing


def _load_synthetic_run(
    root: Path,
    index: dict[str, Any],
) -> tuple[SuiteRun, SuiteArtifact]:
    if (
        index.get("schema")
        != "taichu.general_agent_benchmark.synthetic-baseline-index@1"
    ):
        raise ValueError("synthetic 权威索引 schema 不受支持。")
    baseline_ref = _required_string(index, "baseline_ref")
    baseline = _read_indexed_ref(root, baseline_ref, "runs")
    if (
        baseline.get("schema")
        != "taichu.general_agent_benchmark.synthetic-baseline@1"
        or baseline.get("frozen") is not True
    ):
        raise ValueError("synthetic 基线不是受支持的冻结工件。")
    artifact_hash = _required_string(baseline, "artifact_hash")
    if canonical_sha256(_without(baseline, "artifact_hash")) != artifact_hash:
        raise ValueError("synthetic 基线工件哈希不一致。")
    for field in ("artifact_hash", "stable_result_hash", "suite_content_hash"):
        if baseline.get(field) != index.get(field):
            raise ValueError(f"synthetic 索引字段不一致：{field}。")
    summaries = baseline.get("case_summaries")
    if not isinstance(summaries, list) or not summaries:
        raise ValueError("synthetic 基线缺少案例摘要。")
    if any(not isinstance(item, dict) for item in summaries):
        raise ValueError("synthetic 案例摘要格式非法。")
    case_ids = tuple(_required_string(item, "case_id") for item in summaries)
    if (
        len(case_ids) != len(set(case_ids))
        or baseline.get("case_count") != len(case_ids)
        or baseline.get("passed_case_count") != len(case_ids)
        or any(item.get("conclusion") != "passed" for item in summaries)
    ):
        raise ValueError("synthetic 基线不是完整通过结果。")
    stable_hash = _required_string(baseline, "stable_result_hash")
    run = SuiteRun(
        run_id=f"benchmark_run_19700101T000000Z_{stable_hash[:12]}",
        revision=0,
        lifecycle=SuiteRunLifecycle.COMPLETED,
        conclusion=SuiteConclusion.PASSED,
        suite_content_hash=_required_string(baseline, "suite_content_hash"),
        selected_case_ids=case_ids,
        track=TrackKind.SYNTHETIC,
        provider_state=ProviderExecutionState.NOT_APPLICABLE,
        case_row_refs=tuple(
            f"{baseline_ref}#/case_summaries/{position}"
            for position in range(len(case_ids))
        ),
        pending_case_ids=(),
        terminal_artifact_ref=baseline_ref,
    )
    artifact = _build_synthetic_suite_artifact(
        baseline=baseline,
        baseline_ref=baseline_ref,
        run=run,
    )
    return run, artifact


def _build_synthetic_suite_artifact(
    *,
    baseline: dict[str, Any],
    baseline_ref: str,
    run: SuiteRun,
) -> SuiteArtifact:
    suite_id = _required_string(baseline, "suite_id")
    fixture_snapshot_id = _required_string(
        baseline,
        "fixture_snapshot_id",
    )
    summaries = baseline["case_summaries"]
    rows: list[CaseResultRow] = []
    bundles: list[EvidenceBundle] = []
    for summary in summaries:
        case_id = _required_string(summary, "case_id")
        raw_gates = summary.get("gates")
        raw_invocations = summary.get("invocations")
        normalization = summary.get("normalization_artifact")
        runtime_refs = summary.get("runtime_evidence_refs")
        if (
            not isinstance(raw_gates, list)
            or not raw_gates
            or not isinstance(raw_invocations, list)
            or not isinstance(normalization, dict)
            or not isinstance(normalization.get("consumption_trace"), list)
            or not normalization["consumption_trace"]
            or not isinstance(runtime_refs, list)
            or not runtime_refs
        ):
            raise ValueError(
                f"synthetic 案例缺少详情证据：{case_id}。"
            )
        details = FrozenCaseEvidenceDetails(
            gates=tuple(raw_gates),
            capability_invocations=tuple(
                FrozenCapabilityInvocationEvidence.model_validate(item)
                for item in raw_invocations
            ),
            normalization_actions=tuple(
                FrozenNormalizationActionEvidence.model_validate(item)
                for item in normalization["consumption_trace"]
            ),
            normalization_hash=_required_string(
                normalization,
                "normalization_hash",
            ),
            runtime_evidence_refs=tuple(
                _require_non_empty_string(item, "runtime_evidence_refs")
                for item in runtime_refs
            ),
        )
        if not any(
            gate.gate_kind is GateKind.BUDGET
            and gate.status is GateStatus.PASSED
            for gate in details.gates
        ):
            raise ValueError(
                f"synthetic 案例缺少通过的预算门禁：{case_id}。"
            )
        mechanism_conditions = tuple(
            condition
            for gate in details.gates
            for condition in gate.conditions
            if condition.condition_id.endswith("_mechanism")
        )
        if not mechanism_conditions or any(
            condition.status is not GateStatus.PASSED
            for condition in mechanism_conditions
        ):
            raise ValueError(
                f"synthetic 案例缺少通过的机制门禁：{case_id}。"
            )
        case_execution_hash = canonical_sha256(
            {"run_id": run.run_id, "case_id": case_id}
        )
        case_execution_id = f"benchmark_case_{case_execution_hash[:32]}"
        bundle_payload = {
            "suite_id": suite_id,
            "case_id": case_id,
            "run_id": run.run_id,
            "case_execution_id": case_execution_id,
            "track": run.track,
            "fixture_snapshot_id": fixture_snapshot_id,
            "details": details,
            "source_ref": baseline_ref,
        }
        bundle_hash = canonical_sha256(bundle_payload)
        bundle_id = f"evidence_{bundle_hash}"
        bundle = EvidenceBundle(
            identity=EvidenceBundleIdentity(
                bundle_id=bundle_id,
                bundle_hash=bundle_hash,
                suite_id=suite_id,
                case_id=case_id,
                run_id=run.run_id,
                case_execution_id=case_execution_id,
                track=run.track,
                fixture_snapshot_id=fixture_snapshot_id,
            ),
            availability={
                "normalization": EvidenceAvailability.AVAILABLE,
                "gates": EvidenceAvailability.AVAILABLE,
                "invocations": EvidenceAvailability.AVAILABLE,
                "budget": EvidenceAvailability.AVAILABLE,
            },
            problems=(),
            details=details,
        )
        row = CaseResultRow(
            suite_id=suite_id,
            case_id=case_id,
            case_execution_id=case_execution_id,
            attempt_number=1,
            execution_state=CaseExecutionState.COMPLETED,
            conclusion=CaseConclusion.PASSED,
            failure_category=None,
            failure_categories=(),
            evidence_bundle_id=bundle_id,
            evidence_availability=EvidenceAvailability.AVAILABLE,
        )
        rows.append(row)
        bundles.append(bundle)
    content = {
        "artifact_id": (
            "synthetic_detail_"
            + _required_string(baseline, "artifact_hash")
        ),
        "run_id": run.run_id,
        "conclusion": SuiteConclusion.PASSED,
        "case_rows": tuple(rows),
        "evidence_bundles": tuple(bundles),
        "provider_state": ProviderExecutionState.NOT_APPLICABLE,
    }
    return SuiteArtifact(
        **content,
        artifact_hash=canonical_sha256(content),
    )


def _load_first_live(
    root: Path,
    index: dict[str, Any],
    classification_index: dict[str, Any],
) -> tuple[
    FirstLiveIterationManifest,
    FirstLiveArtifact,
    ModelComparisonRecord,
]:
    if index.get("provider_state") == "completed":
        return _load_completed_first_live(
            root,
            index,
            classification_index,
        )
    if index.get("provider_state") != "error":
        raise ValueError("首轮索引不得把提供商错误恢复为成功。")
    if index.get("comparison_admission") != "blocked":
        raise ValueError("首轮索引不得绕过模型比较准入。")
    envelope_ref = _required_string(index, "iteration_ref")
    envelope = _read_indexed_ref(root, envelope_ref, "iterations")
    if (
        envelope.get("schema")
        != "taichu.general_agent_benchmark.first-live-envelope@1"
    ):
        raise ValueError("首轮冻结信封 schema 不受支持。")
    manifest = FirstLiveIterationManifest.model_validate(
        envelope.get("iteration")
    )
    artifact = FirstLiveArtifact.model_validate(envelope.get("artifact"))
    if (
        manifest.state is not FirstLiveIterationState.BLOCKED
        or artifact.provider_state is not ProviderExecutionState.ERROR
        or artifact.complete
        or artifact.probe_succeeded
        or artifact.fallback_used
    ):
        raise ValueError("首轮冻结信封错误边界不成立。")
    if (
        artifact.artifact_id != index.get("artifact_id")
        or artifact.artifact_hash != index.get("artifact_hash")
        or manifest.first_live_artifact_ref != artifact.artifact_id
        or envelope.get("comparison_admission") != "blocked"
    ):
        raise ValueError("首轮索引、清单与工件身份不一致。")
    artifact_content = artifact.model_dump(mode="json", exclude={"artifact_hash"})
    if canonical_sha256(artifact_content) != artifact.artifact_hash:
        raise ValueError("首轮工件哈希不一致。")
    probe_ref = _required_string(index, "probe_evidence_ref")
    probe = _read_indexed_ref(root, probe_ref, "iterations")
    attempts = probe.get("attempts")
    if (
        probe.get("schema")
        != "taichu.general_agent_benchmark.provider-probe@1"
        or probe.get("requested_model_id") != artifact.actual_model_id
        or probe.get("fallback_allowed") is not False
        or probe.get("all_unavailable") is not True
        or not isinstance(attempts, list)
        or not attempts
        or any(
            attempt.get("provider") != artifact.actual_provider_id
            or attempt.get("model_id") != artifact.actual_model_id
            or attempt.get("error_code") != artifact.error_code
            or attempt.get("status") != "failed"
            for attempt in attempts
        )
    ):
        raise ValueError("首轮探测证据与错误工件不一致。")
    _validate_classification(
        root,
        classification_index,
        artifact,
        manifest,
    )
    comparison = _blocked_comparison_projection(artifact, manifest)
    return manifest, artifact, comparison


def _load_completed_first_live(
    root: Path,
    index: dict[str, Any],
    classification_index: dict[str, Any],
) -> tuple[
    FirstLiveIterationManifest,
    FirstLiveArtifact,
    ModelComparisonRecord,
]:
    if index.get("comparison_admission") != "blocked":
        raise ValueError("首轮完成后仍须等待多模型比较准入。")
    envelope_ref = _required_string(index, "iteration_ref")
    envelope = _read_indexed_ref(root, envelope_ref, "iterations")
    if (
        envelope.get("schema")
        != "taichu.general_agent_benchmark.first-live-envelope@1"
    ):
        raise ValueError("首轮完成信封 schema 不受支持。")
    manifest = FirstLiveIterationManifest.model_validate(
        envelope.get("iteration")
    )
    artifact = FirstLiveArtifact.model_validate(envelope.get("artifact"))
    if (
        manifest.state is not FirstLiveIterationState.READY_FOR_COMPARISON
        or artifact.provider_state is not ProviderExecutionState.COMPLETED
        or not artifact.complete
        or not artifact.probe_succeeded
        or artifact.fallback_used
        or not artifact.replay_available
        or not artifact.usage_available
        or not artifact.cost_available
        or artifact.error_code is not None
    ):
        raise ValueError("首轮完成信封缺少完整 Provider 审计证据。")
    if (
        artifact.artifact_id != index.get("artifact_id")
        or artifact.artifact_hash != index.get("artifact_hash")
        or manifest.first_live_artifact_ref != artifact.artifact_id
        or envelope.get("comparison_admission") != "blocked"
    ):
        raise ValueError("首轮完成索引、清单与工件身份不一致。")
    artifact_content = artifact.model_dump(mode="json", exclude={"artifact_hash"})
    if canonical_sha256(artifact_content) != artifact.artifact_hash:
        raise ValueError("首轮完成工件哈希不一致。")
    raw_ref = _required_string(index, "suite_raw_ref")
    raw = _read_indexed_ref(root, raw_ref, "iterations")
    suite_result = raw.get("suite_result")
    provider_audits = raw.get("provider_audits")
    if (
        raw.get("schema")
        != "taichu.general_agent_benchmark.live-suite-raw@1"
        or canonical_sha256(_without(raw, "artifact_hash"))
        != raw.get("artifact_hash")
        or raw.get("requested_provider") != artifact.actual_provider_id
        or raw.get("requested_model_id") != artifact.actual_model_id
        or raw.get("fallback_allowed") is not False
        or not isinstance(suite_result, dict)
        or suite_result.get("complete") is not True
        or suite_result.get("passed_case_count")
        != len(manifest.selected_case_ids)
        or suite_result.get("case_count") != len(manifest.selected_case_ids)
        or suite_result.get("suite_content_hash") != manifest.suite_hash
        or not isinstance(provider_audits, dict)
        or set(provider_audits) != set(manifest.selected_case_ids)
        or any(
            not isinstance(audit, dict)
            or not isinstance(audit.get("gateway_failures"), list)
            or not audit.get("usage_records")
            or not audit.get("replay_records")
            for audit in provider_audits.values()
        )
    ):
        raise ValueError("首轮完成原始套件证据不完整或身份漂移。")
    expected_failure_refs = tuple(
        f"{raw_ref}#/provider_audits/{case_id}/gateway_failures/{position}"
        for case_id, audit in provider_audits.items()
        for position, _failure in enumerate(audit["gateway_failures"])
    )
    if artifact.failure_record_refs != expected_failure_refs:
        raise ValueError("首轮已恢复 Provider 错误与原始审计引用不对称。")
    classification_ref = _required_string(
        classification_index,
        "classification_ref",
    )
    classification = _read_indexed_ref(
        root,
        classification_ref,
        "iterations",
    )
    if (
        classification_index.get("provider_state") != "completed"
        or classification.get("provider_state") != "completed"
        or classification.get("first_live_artifact_ref")
        != artifact.artifact_id
        or classification.get("first_live_artifact_hash")
        != artifact.artifact_hash
        or classification.get("failed_case_count") != 0
        or canonical_sha256(_without(classification, "classification_hash"))
        != classification.get("classification_hash")
    ):
        raise ValueError("首轮完成分类工件不完整。")
    return manifest, artifact, _pending_comparison_projection(artifact, manifest)


def _validate_classification(
    root: Path,
    index: dict[str, Any],
    artifact: FirstLiveArtifact,
    manifest: FirstLiveIterationManifest,
) -> None:
    if (
        index.get("origin") != "provider_environment"
        or index.get("primary_category") != "execution_error"
        or index.get("system_issue_candidate_count") != 0
    ):
        raise ValueError("首轮分类索引未保持提供商环境错误边界。")
    ref = _required_string(index, "classification_ref")
    classification = _read_indexed_ref(root, ref, "iterations")
    classification_hash = _required_string(
        classification,
        "classification_hash",
    )
    if (
        classification_hash != index.get("classification_hash")
        or canonical_sha256(_without(classification, "classification_hash"))
        != classification_hash
        or classification.get("provider_state") != "error"
        or classification.get("first_live_artifact_ref")
        != artifact.artifact_id
        or classification.get("first_live_artifact_hash")
        != artifact.artifact_hash
        or classification.get("system_issue_candidates") != []
    ):
        raise ValueError("首轮分类工件与权威索引不一致。")
    dispositions = classification.get("case_dispositions")
    if not isinstance(dispositions, list):
        raise ValueError("首轮分类工件缺少案例处置。")
    if {item.get("case_id") for item in dispositions} != set(
        manifest.selected_case_ids
    ):
        raise ValueError("首轮分类案例集合不完整。")


def _blocked_comparison_projection(
    artifact: FirstLiveArtifact,
    manifest: FirstLiveIterationManifest,
) -> ModelComparisonRecord:
    unavailable_hash = canonical_sha256(
        {
            "state": "unavailable",
            "source": artifact.artifact_id,
        }
    )
    candidate = ModelCandidateEvidence(
        candidate_id="deepseek_v4_pro",
        requested_model_ref=artifact.requested_model_ref,
        probe_succeeded=artifact.probe_succeeded,
        actual_provider_id=artifact.actual_provider_id,
        actual_model_id=artifact.actual_model_id,
        fallback_used=artifact.fallback_used,
        replay_available=artifact.replay_available,
        usage_available=artifact.usage_available,
        cost_available=artifact.cost_available,
        error_code=artifact.error_code,
    )
    reasons = (
        "首轮迭代尚未达到可比较状态。",
        "DeepSeek V4 Pro 提供商探测失败，比较准入保持阻断。",
    )
    admission = ModelComparisonAdmission(
        status=AdmissionStatus.BLOCKED,
        admitted=False,
        code_hash=manifest.code_hash,
        suite_hash=manifest.suite_hash,
        fixture_hash=manifest.fixture_hash,
        case_set_hash=canonical_sha256(manifest.selected_case_ids),
        per_case_budgets_hash=unavailable_hash,
        capability_catalog_hash=manifest.capability_catalog_hash,
        authorization_policy_hash=unavailable_hash,
        decode_configuration_hash=unavailable_hash,
        environment_hash=unavailable_hash,
        candidates=(candidate,),
        blocked_reasons=reasons,
        ranking_candidate_ids=(),
    )
    payload = {
        "comparison_id": "deepseek_first_live_blocked",
        "admitted": False,
        "first_live_artifact_ref": artifact.artifact_id,
        "admission": admission,
        "closure_ids": (),
        "blocked_reasons": reasons,
        "ranking_candidate_ids": (),
    }
    return ModelComparisonRecord(
        **payload,
        record_hash=canonical_sha256(payload),
    )


def _pending_comparison_projection(
    artifact: FirstLiveArtifact,
    manifest: FirstLiveIterationManifest,
) -> ModelComparisonRecord:
    pending_hash = canonical_sha256(
        {"state": "pending_multi_model", "source": artifact.artifact_id}
    )
    candidate = ModelCandidateEvidence(
        candidate_id="deepseek_v4_pro",
        requested_model_ref=artifact.requested_model_ref,
        probe_succeeded=artifact.probe_succeeded,
        actual_provider_id=artifact.actual_provider_id,
        actual_model_id=artifact.actual_model_id,
        fallback_used=artifact.fallback_used,
        replay_available=artifact.replay_available,
        usage_available=artifact.usage_available,
        cost_available=artifact.cost_available,
        error_code=artifact.error_code,
    )
    reasons = ("DeepSeek V4 Pro 首轮已通过，尚未完成其他模型的同条件运行。",)
    admission = ModelComparisonAdmission(
        status=AdmissionStatus.BLOCKED,
        admitted=False,
        code_hash=manifest.code_hash,
        suite_hash=manifest.suite_hash,
        fixture_hash=manifest.fixture_hash,
        case_set_hash=canonical_sha256(manifest.selected_case_ids),
        per_case_budgets_hash=pending_hash,
        capability_catalog_hash=manifest.capability_catalog_hash,
        authorization_policy_hash=pending_hash,
        decode_configuration_hash=pending_hash,
        environment_hash=pending_hash,
        candidates=(candidate,),
        blocked_reasons=reasons,
        ranking_candidate_ids=(),
    )
    payload = {
        "comparison_id": "deepseek_first_live_pending_multi_model",
        "admitted": False,
        "first_live_artifact_ref": artifact.artifact_id,
        "admission": admission,
        "closure_ids": (),
        "blocked_reasons": reasons,
        "ranking_candidate_ids": (),
    }
    return ModelComparisonRecord(
        **payload,
        record_hash=canonical_sha256(payload),
    )


def _read_indexed_ref(
    root: Path,
    ref: str,
    expected_collection: str,
) -> dict[str, Any]:
    matched = _REF_PATTERN.fullmatch(ref)
    if matched is None or matched.group(1) != expected_collection:
        raise ValueError(f"冻结索引引用越界：{ref}")
    target = (root / matched.group(1) / f"{matched.group(2)}.json").resolve()
    expected_root = (root / expected_collection).resolve()
    if not target.is_relative_to(expected_root):
        raise ValueError(f"冻结索引引用越界：{ref}")
    return _read_json(target)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"冻结评测工件必须是 JSON 对象：{path.name}")
    return value


def _required_string(value: dict[str, Any], field: str) -> str:
    result = value[field]
    return _require_non_empty_string(result, field)


def _require_non_empty_string(result: object, field: str) -> str:
    if not isinstance(result, str) or not result:
        raise ValueError(f"冻结评测字段非法：{field}")
    return result


def _without(value: dict[str, Any], field: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != field}
