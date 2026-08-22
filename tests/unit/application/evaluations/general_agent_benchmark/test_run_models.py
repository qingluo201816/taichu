"""需求 5.5、5.6、5.8、5.9、5.21、6.9：运行状态与证据合同。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from taichu.application.evaluations.general_agent_benchmark.models import (
    CaseConclusion,
    GateConditionResult,
    GateStatus,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    CaseExecutionState,
    CaseResultRow,
    EvidenceAvailability,
    EvidenceBundle,
    EvidenceBundleIdentity,
    EvidenceItem,
    MechanismConclusion,
    MechanismDecisionSource,
    MechanismGateResult,
    ProviderExecutionState,
    SuiteArtifact,
    SuiteConclusion,
    SuiteRun,
    SuiteRunCounts,
    SuiteRunLifecycle,
    aggregate_case_rows,
)


def _run(**overrides: object) -> SuiteRun:
    values: dict[str, object] = {
        "run_id": "benchmark_run_20260727T000000Z_abcdef123456",
        "revision": 0,
        "lifecycle": SuiteRunLifecycle.QUEUED,
        "conclusion": None,
        "suite_content_hash": "a" * 64,
        "selected_case_ids": ("fact_lookup",),
        "track": "synthetic",
        "provider_state": ProviderExecutionState.NOT_APPLICABLE,
        "case_row_refs": (),
        "pending_case_ids": ("fact_lookup",),
        "terminal_artifact_ref": None,
    }
    values.update(overrides)
    return SuiteRun.model_validate(values)


@pytest.mark.parametrize(
    "lifecycle",
    [
        SuiteRunLifecycle.QUEUED,
        SuiteRunLifecycle.RUNNING,
        SuiteRunLifecycle.CANCELLING,
        SuiteRunLifecycle.FINALIZING,
        SuiteRunLifecycle.UNFINISHED,
        SuiteRunLifecycle.CANCELLED,
    ],
)
def test_non_completed_suite_lifecycle_never_has_business_conclusion(
    lifecycle: SuiteRunLifecycle,
) -> None:
    _run(lifecycle=lifecycle, conclusion=None)
    with pytest.raises(ValidationError):
        _run(lifecycle=lifecycle, conclusion=SuiteConclusion.FAILED)


@pytest.mark.parametrize(
    "conclusion",
    [
        SuiteConclusion.PASSED,
        SuiteConclusion.FAILED,
        SuiteConclusion.INVALID,
        SuiteConclusion.NOT_EVALUATED,
    ],
)
def test_completed_suite_requires_conclusion_and_terminal_artifact(
    conclusion: SuiteConclusion,
) -> None:
    completed = _run(
        lifecycle=SuiteRunLifecycle.COMPLETED,
        conclusion=conclusion,
        terminal_artifact_ref="benchmark_artifact_benchmark_run_20260727",
    )
    assert completed.conclusion is conclusion

    with pytest.raises(ValidationError):
        _run(
            lifecycle=SuiteRunLifecycle.COMPLETED,
            conclusion=conclusion,
            terminal_artifact_ref=None,
        )


def test_evidence_item_does_not_disguise_missing_or_conflicting_data() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem[str](
            availability=EvidenceAvailability.MISSING,
            value="伪造证据",
            problems=(),
            locators=(),
        )

    with pytest.raises(ValidationError):
        EvidenceItem[str](
            availability=EvidenceAvailability.AVAILABLE,
            value=None,
            problems=("缺少内容",),
            locators=(),
        )


def test_case_row_keeps_execution_state_separate_from_case_conclusion() -> None:
    row = CaseResultRow(
        suite_id="general_writing_agent_core",
        case_id="fact_lookup",
        case_execution_id="benchmark_case_" + "b" * 32,
        attempt_number=1,
        execution_state=CaseExecutionState.COMPLETED,
        conclusion=CaseConclusion.FAILED,
        failure_category="verifier_failed",
        failure_categories=("verifier_failed",),
        evidence_bundle_id="evidence_" + "c" * 64,
        evidence_availability=EvidenceAvailability.AVAILABLE,
    )
    assert row.conclusion is CaseConclusion.FAILED

    blocked = row.model_copy(
        update={
            "execution_state": CaseExecutionState.BLOCKED,
            "conclusion": None,
            "failure_category": None,
            "failure_categories": (),
            "evidence_availability": EvidenceAvailability.MISSING,
        }
    )
    assert CaseResultRow.model_validate(blocked.model_dump()).conclusion is None
    with pytest.raises(ValidationError):
        CaseResultRow.model_validate(
            blocked.model_copy(
                update={"conclusion": CaseConclusion.FAILED}
            ).model_dump()
        )


def test_mechanism_decision_source_and_provider_state_are_closed() -> None:
    result = MechanismGateResult(
        mechanism_id="memory",
        status=GateStatus.PASSED,
        conditions=(
            GateConditionResult(
                condition_id="active_projection",
                status=GateStatus.PASSED,
                expected="仅 ACTIVE",
                observed="仅 ACTIVE",
                evidence_refs=("context_snapshot",),
            ),
        ),
        evidence_refs=("context_snapshot",),
        conclusion=MechanismConclusion.MET,
        decision_source=MechanismDecisionSource.HARD_GATE,
    )
    assert result.decision_source is MechanismDecisionSource.HARD_GATE
    assert ProviderExecutionState("blocked") is ProviderExecutionState.BLOCKED
    assert ProviderExecutionState("error") is ProviderExecutionState.ERROR


def test_suite_artifact_requires_available_evidence_bundle_identity() -> None:
    bundle = EvidenceBundle(
        identity=EvidenceBundleIdentity(
            bundle_id="evidence_" + "d" * 64,
            bundle_hash="d" * 64,
            suite_id="general_writing_agent_core",
            case_id="fact_lookup",
            run_id="benchmark_run_20260727T000000Z_abcdef123456",
            case_execution_id="benchmark_case_" + "e" * 32,
            track="synthetic",
            fixture_snapshot_id="fixture_" + "f" * 64,
        ),
        availability={
            "run": EvidenceAvailability.AVAILABLE,
            "invocation": EvidenceAvailability.AVAILABLE,
        },
        problems=(),
    )
    artifact = SuiteArtifact(
        artifact_id="benchmark_artifact_benchmark_run_20260727T000000Z_abcdef123456",
        run_id="benchmark_run_20260727T000000Z_abcdef123456",
        conclusion=SuiteConclusion.PASSED,
        case_rows=(
            CaseResultRow(
                suite_id="general_writing_agent_core",
                case_id="fact_lookup",
                case_execution_id="benchmark_case_" + "e" * 32,
                attempt_number=1,
                execution_state=CaseExecutionState.COMPLETED,
                conclusion=CaseConclusion.PASSED,
                failure_category=None,
                failure_categories=(),
                evidence_bundle_id="evidence_" + "d" * 64,
                evidence_availability=EvidenceAvailability.AVAILABLE,
            ),
        ),
        evidence_bundles=(bundle,),
        provider_state=ProviderExecutionState.NOT_APPLICABLE,
        artifact_hash="1" * 64,
    )
    assert artifact.conclusion is SuiteConclusion.PASSED


def test_case_row_counts_are_derived_from_mutually_exclusive_actual_states() -> None:
    base = CaseResultRow(
        suite_id="general_writing_agent_core",
        case_id="fact_lookup",
        case_execution_id="benchmark_case_" + "a" * 32,
        attempt_number=1,
        execution_state=CaseExecutionState.COMPLETED,
        conclusion=CaseConclusion.PASSED,
        failure_category=None,
        failure_categories=(),
        evidence_bundle_id="evidence_" + "b" * 64,
        evidence_availability=EvidenceAvailability.AVAILABLE,
    )
    pending = base.model_copy(
        update={
            "case_id": "pending_case",
            "case_execution_id": "benchmark_case_" + "c" * 32,
            "execution_state": CaseExecutionState.PENDING,
            "conclusion": None,
            "evidence_bundle_id": "evidence_" + "d" * 64,
            "evidence_availability": EvidenceAvailability.MISSING,
        }
    )
    invalid = base.model_copy(
        update={
            "case_id": "invalid_case",
            "case_execution_id": "benchmark_case_" + "e" * 32,
            "conclusion": CaseConclusion.INVALID,
            "failure_category": "evidence_incomplete",
            "failure_categories": ("evidence_incomplete",),
            "evidence_bundle_id": "evidence_" + "f" * 64,
            "evidence_availability": EvidenceAvailability.CORRUPT,
        }
    )

    counts = aggregate_case_rows((base, pending, invalid))

    assert counts == SuiteRunCounts(
        total=3,
        pending=1,
        running=0,
        blocked=0,
        error=0,
        passed=1,
        failed=0,
        invalid=1,
        unfinished=0,
        cancelled=0,
    )
