"""从统一 runner 结果派生案例行、证据包、真实计数与套件结论。"""

from __future__ import annotations

from pydantic import Field, model_validator

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    CaseConclusion,
    FailureCategory,
    GateKind,
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
    SuiteRunCounts,
    aggregate_case_rows,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredSuiteSpec,
)
from taichu.application.evaluations.general_agent_benchmark.synthetic_suite import (
    SyntheticCaseBaselineResult,
    SyntheticSuiteBaselineResult,
)

_REQUIRED_EVIDENCE_SLOTS = (
    "input",
    "assertions",
    "gates",
    "invocations",
    "artifacts",
    "resources",
    "terminal",
    "runtime_refs",
)


class BuiltSuiteArtifact(BenchmarkModel):
    artifact: SuiteArtifact
    counts: SuiteRunCounts
    complete_admission: bool
    expected_case_ids: tuple[str, ...] = Field(min_length=1)
    observed_case_ids: tuple[str, ...]
    problems: tuple[str, ...]

    @model_validator(mode="after")
    def _admission_requires_exact_complete_pass(self) -> BuiltSuiteArtifact:
        expected = (
            not self.problems
            and self.observed_case_ids == self.expected_case_ids
            and self.counts.total == len(self.expected_case_ids)
            and self.counts.passed == self.counts.total
            and self.artifact.conclusion is SuiteConclusion.PASSED
        )
        if self.complete_admission is not expected:
            raise ValueError("完整准入必须由精确案例集、真实计数和完整证据共同派生。")
        return self


def build_synthetic_suite_artifact(
    *,
    suite: AuthoredSuiteSpec,
    result: SyntheticSuiteBaselineResult,
) -> BuiltSuiteArtifact:
    expected_case_ids = tuple(
        case.case_id
        for case in suite.cases
        if TrackKind.SYNTHETIC in case.applicable_tracks
    )
    observed_case_ids = tuple(case.case_id for case in result.cases)
    suite_problems: list[str] = []
    identity_invalid = False
    if result.suite_id != suite.suite_id:
        suite_problems.append("suite_id 与权威套件不一致")
        identity_invalid = True
    if result.suite_content_hash != suite.content_hash:
        suite_problems.append("suite_content_hash 与权威套件不一致")
        identity_invalid = True
    if (
        result.case_count != len(result.cases)
        or result.passed_case_count
        != sum(
            case.conclusion is CaseConclusion.PASSED for case in result.cases
        )
        or result.failed_case_count
        != result.case_count - result.passed_case_count
    ):
        suite_problems.append("套件计数与实际案例结果不一致")
        identity_invalid = True
    if observed_case_ids != expected_case_ids:
        suite_problems.append("实际案例集不是完整且有序的 Synthetic 权威案例集")

    rows: list[CaseResultRow] = []
    bundles: list[EvidenceBundle] = []
    for case_result in result.cases:
        row, bundle, problems = _build_case_row_and_bundle(
            suite=suite,
            result=case_result,
        )
        rows.append(row)
        bundles.append(bundle)
        suite_problems.extend(
            f"{case_result.case_id}:{problem}" for problem in problems
        )

    frozen_rows = tuple(rows)
    counts = aggregate_case_rows(frozen_rows)
    conclusion = _suite_conclusion(
        rows=frozen_rows,
        exact_case_set=observed_case_ids == expected_case_ids,
        has_integrity_problems=identity_invalid
        or any(row.evidence_availability is not EvidenceAvailability.AVAILABLE for row in rows),
    )
    artifact_content = {
        "artifact_id": f"synthetic_detail_{result.result_hash}",
        "run_id": f"synthetic_suite_{result.result_hash[:32]}",
        "conclusion": conclusion,
        "case_rows": frozen_rows,
        "evidence_bundles": tuple(bundles),
        "provider_state": ProviderExecutionState.NOT_APPLICABLE,
    }
    artifact = SuiteArtifact(
        **artifact_content,
        artifact_hash=canonical_sha256(artifact_content),
    )
    return BuiltSuiteArtifact(
        artifact=artifact,
        counts=counts,
        complete_admission=(
            conclusion is SuiteConclusion.PASSED
            and not suite_problems
            and observed_case_ids == expected_case_ids
        ),
        expected_case_ids=expected_case_ids,
        observed_case_ids=observed_case_ids,
        problems=tuple(suite_problems),
    )


def _build_case_row_and_bundle(
    *,
    suite: AuthoredSuiteSpec,
    result: SyntheticCaseBaselineResult,
) -> tuple[CaseResultRow, EvidenceBundle, tuple[str, ...]]:
    observation = result.case_observation
    normalization = result.normalization_artifact
    problems: list[str] = []
    availability = EvidenceAvailability.AVAILABLE
    if observation is None or normalization is None:
        availability = EvidenceAvailability.MISSING
        problems.append("缺少完整 CaseObservation 或规范化工件")
    elif (
        observation.owner.suite_id != suite.suite_id
        or observation.owner.suite_content_hash != suite.content_hash
        or observation.owner.case_id != result.case_id
        or observation.owner.track is not TrackKind.SYNTHETIC
        or observation.owner.fixture_snapshot_id != suite.fixture.snapshot_id
    ):
        availability = EvidenceAvailability.CONFLICTING
        problems.append("案例观察 owner 与权威套件身份冲突")
    elif observation.evidence_problems:
        availability = EvidenceAvailability.CORRUPT
        problems.append("案例观察包含损坏或冲突的证据引用")

    if (
        len(result.gates) != len(GateKind)
        or {gate.gate_kind for gate in result.gates} != set(GateKind)
    ):
        availability = EvidenceAvailability.MISSING
        problems.append("案例没有完整六类门禁")
    if not result.evidence_ids:
        availability = EvidenceAvailability.MISSING
        problems.append("案例没有运行证据引用")

    if observation is not None:
        owner = observation.owner
        run_id = owner.run_id
        case_execution_id = owner.case_execution_id
        fixture_snapshot_id = owner.fixture_snapshot_id
    else:
        case_execution_hash = canonical_sha256(
            {
                "suite_content_hash": suite.content_hash,
                "case_id": result.case_id,
                "state": "owner_unavailable",
            }
        )
        run_id = f"unavailable:{result.case_id}"
        case_execution_id = f"benchmark_case_{case_execution_hash[:32]}"
        fixture_snapshot_id = suite.fixture.snapshot_id

    details = (
        _frozen_details(result)
        if observation is not None and normalization is not None
        else None
    )
    bundle_payload = {
        "suite_id": suite.suite_id,
        "case_id": result.case_id,
        "run_id": run_id,
        "case_execution_id": case_execution_id,
        "track": TrackKind.SYNTHETIC,
        "fixture_snapshot_id": fixture_snapshot_id,
        "availability": availability,
        "details": details,
        "problems": tuple(problems),
    }
    bundle_hash = canonical_sha256(bundle_payload)
    bundle_id = f"evidence_{bundle_hash}"
    bundle = EvidenceBundle(
        identity=EvidenceBundleIdentity(
            bundle_id=bundle_id,
            bundle_hash=bundle_hash,
            suite_id=suite.suite_id,
            case_id=result.case_id,
            run_id=run_id,
            case_execution_id=case_execution_id,
            track=TrackKind.SYNTHETIC,
            fixture_snapshot_id=fixture_snapshot_id,
        ),
        availability={
            slot: availability for slot in _REQUIRED_EVIDENCE_SLOTS
        },
        problems=tuple(problems),
        details=details,
    )

    conclusion = result.conclusion
    categories = _failure_categories(result)
    if availability is not EvidenceAvailability.AVAILABLE:
        conclusion = CaseConclusion.INVALID
        if FailureCategory.EVIDENCE_INCOMPLETE not in categories:
            categories = (*categories, FailureCategory.EVIDENCE_INCOMPLETE)
    row = CaseResultRow(
        suite_id=suite.suite_id,
        case_id=result.case_id,
        case_execution_id=case_execution_id,
        attempt_number=1,
        execution_state=CaseExecutionState.COMPLETED,
        conclusion=conclusion,
        failure_category=categories[0] if categories else None,
        failure_categories=categories,
        evidence_bundle_id=bundle_id,
        evidence_availability=availability,
    )
    return row, bundle, tuple(problems)


def _frozen_details(
    result: SyntheticCaseBaselineResult,
) -> FrozenCaseEvidenceDetails:
    observation = result.case_observation
    normalization = result.normalization_artifact
    assert observation is not None
    assert normalization is not None
    return FrozenCaseEvidenceDetails(
        gates=result.gates,
        capability_invocations=tuple(
            FrozenCapabilityInvocationEvidence(
                kind=invocation.kind.value,
                capability_name=invocation.capability_name,
                call_id=invocation.call_id,
                handler_identity=invocation.handler_identity,
                outcome=invocation.outcome,
            )
            for invocation in result.invocations
        ),
        normalization_actions=tuple(
            FrozenNormalizationActionEvidence.model_validate(item)
            for item in normalization.consumption_trace
        ),
        normalization_hash=normalization.normalization_hash,
        runtime_evidence_refs=result.evidence_ids,
        user_request_sha256=observation.user_request_sha256,
        track=observation.owner.track,
        assertions=tuple(
            assertion.model_dump(mode="json") for assertion in result.assertions
        ),
        observation_sha256=observation.observation_sha256,
        final_answer_sha256=(
            observation.final_answer.content_sha256
            if observation.final_answer is not None
            else None
        ),
        final_answer_text=(
            observation.final_answer.text
            if observation.final_answer is not None
            else None
        ),
        artifact_refs=tuple(
            f"{item.artifact_id}:{item.content_sha256}"
            for item in observation.artifacts
        ),
        runtime_failure=next(
            (
                item.payload
                for item in observation.artifacts
                if item.artifact_kind == "runtime_safe_failure"
            ),
            None,
        ),
        resource_after_refs=tuple(
            f"{item.snapshot_ref}:{item.content_sha256}"
            for item in observation.resource_snapshots
            if item.phase == "after"
        ),
        terminal=observation.terminal.model_dump(mode="json"),
        capability_result_refs=tuple(
            item.record_id for item in observation.capability_result_refs
        ),
        effect_refs=tuple(item.record_id for item in observation.effect_refs),
        checkpoint_refs=tuple(
            item.record_id for item in observation.checkpoint_refs
        ),
        context_snapshot_refs=tuple(
            item.record_id for item in observation.context_snapshot_refs
        ),
    )


def _failure_categories(
    result: SyntheticCaseBaselineResult,
) -> tuple[FailureCategory, ...]:
    return tuple(
        dict.fromkeys(
            category
            for gate in result.gates
            for category in gate.failure_categories
        )
    )


def _suite_conclusion(
    *,
    rows: tuple[CaseResultRow, ...],
    exact_case_set: bool,
    has_integrity_problems: bool,
) -> SuiteConclusion:
    if has_integrity_problems or any(
        row.conclusion is CaseConclusion.INVALID
        or row.evidence_availability is not EvidenceAvailability.AVAILABLE
        for row in rows
    ):
        return SuiteConclusion.INVALID
    if any(
        row.conclusion
        in {
            CaseConclusion.FAILED,
            CaseConclusion.CANCELLED,
            CaseConclusion.UNFINISHED,
        }
        for row in rows
    ):
        return SuiteConclusion.FAILED
    if exact_case_set and rows and all(
        row.execution_state is CaseExecutionState.COMPLETED
        and row.conclusion is CaseConclusion.PASSED
        for row in rows
    ):
        return SuiteConclusion.PASSED
    return SuiteConclusion.NOT_EVALUATED


def stable_suite_drift_paths(
    baseline: SyntheticSuiteBaselineResult,
    repeated: SyntheticSuiteBaselineResult,
) -> tuple[str, ...]:
    if baseline.stable_result_hash == repeated.stable_result_hash:
        return ()
    paths: list[str] = []
    if baseline.suite_id != repeated.suite_id:
        paths.append("/suite_id")
    if baseline.suite_content_hash != repeated.suite_content_hash:
        paths.append("/suite_content_hash")
    if baseline.runtime_config_identity != repeated.runtime_config_identity:
        paths.append("/runtime_config_identity")
    baseline_cases = {item.case_id: item for item in baseline.cases}
    repeated_cases = {item.case_id: item for item in repeated.cases}
    if tuple(baseline_cases) != tuple(repeated_cases):
        paths.append("/case_ids")
    for case_id in tuple(dict.fromkeys((*baseline_cases, *repeated_cases))):
        left = baseline_cases.get(case_id)
        right = repeated_cases.get(case_id)
        if left is None or right is None:
            paths.append(f"/cases/{case_id}")
            continue
        if left.conclusion != right.conclusion:
            paths.append(f"/cases/{case_id}/conclusion")
        if tuple(
            (gate.gate_kind, gate.status) for gate in left.gates
        ) != tuple((gate.gate_kind, gate.status) for gate in right.gates):
            paths.append(f"/cases/{case_id}/gates")
        if _evidence_contract(left) != _evidence_contract(right):
            paths.append(f"/cases/{case_id}/evidence_contract")
        left_hash = (
            left.normalization_artifact.normalization_hash
            if left.normalization_artifact is not None
            else None
        )
        right_hash = (
            right.normalization_artifact.normalization_hash
            if right.normalization_artifact is not None
            else None
        )
        if left_hash != right_hash:
            paths.append(f"/cases/{case_id}/normalization_hash")
    return tuple(paths or ("/stable_result_hash",))


def _evidence_contract(
    result: SyntheticCaseBaselineResult,
) -> tuple[tuple[str, str], ...]:
    if result.case_observation is None:
        return ()
    return tuple(
        sorted(
            (record.ref.kind.value, record.ref.selector.value)
            for record in result.case_observation.evidence_records
        )
    )
