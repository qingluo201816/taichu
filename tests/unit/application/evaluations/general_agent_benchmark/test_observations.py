"""需求 2.5、10.4—10.8、11.4、12.1：案例观察与证据身份。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.observations import (
    CaseObservation,
    EvidenceIntegrityStatus,
    EvidenceOwner,
    EvidenceRecord,
    EvidenceRef,
    ObservedBudgetUsage,
    ObservedFinalAnswer,
    ObservedTerminalState,
    build_case_observation,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredCaseSpec,
    load_authored_suite,
)

_ROOT = Path("tests/fixtures/evaluations/general_writing_agent_benchmark")
_SUITE_PATH = _ROOT / "suite.json"
_MANIFEST_PATH = _ROOT / "fixtures" / "core_novel" / "fixture-manifest.json"


@pytest.fixture(scope="module")
def case_and_owner() -> tuple[AuthoredCaseSpec, EvidenceOwner]:
    raw = json.loads(_SUITE_PATH.read_text(encoding="utf-8"))
    suite = load_authored_suite(
        _SUITE_PATH,
        expected_capability_catalog_hash=raw["capability_catalog_hash"],
        fixture_manifest_path=_MANIFEST_PATH,
    )
    case = suite.cases[0]
    owner = EvidenceOwner(
        suite_id=suite.suite_id,
        suite_content_hash=suite.content_hash,
        case_id=case.case_id,
        case_execution_id=f"benchmark_case_{'a' * 32}",
        run_id="general_run_20260730_120000_abc123",
        track=TrackKind.SYNTHETIC,
        fixture_snapshot_id=suite.fixture.snapshot_id,
    )
    return case, owner


def _records(
    case: AuthoredCaseSpec,
    owner: EvidenceOwner,
) -> tuple[EvidenceRecord, ...]:
    records: list[EvidenceRecord] = []
    for requirement in case.required_evidence:
        payload = {
            "evidence_id": requirement.evidence_id,
            "observed": True,
        }
        records.append(
            EvidenceRecord(
                ref=EvidenceRef(
                    evidence_id=requirement.evidence_id,
                    kind=requirement.probe.kind,
                    selector=requirement.probe.selector,
                    owner=owner,
                    record_id=f"record_{requirement.evidence_id}",
                    content_sha256=canonical_sha256(payload),
                ),
                payload=payload,
            )
        )
    return tuple(records)


def _observation(
    case: AuthoredCaseSpec,
    owner: EvidenceOwner,
    records: tuple[EvidenceRecord, ...],
) -> CaseObservation:
    return build_case_observation(
        case=case,
        owner=owner,
        user_request_raw=case.user_request_raw,
        plan={"route": "direct", "nodes": []},
        nodes=(),
        invocations=(),
        final_answer=ObservedFinalAnswer.create(
            text="这是当前请求的直接回答。",
            source_refs=(),
        ),
        artifacts=(),
        resource_snapshots=(),
        recovery_decisions=(),
        terminal=ObservedTerminalState(
            run_status="completed",
            stop_reason="direct_answer",
            resumable=False,
            pending_human_kind=None,
        ),
        budget=ObservedBudgetUsage(
            node_executions=0,
            capability_calls=0,
            model_calls=2,
            total_tokens=128,
            runtime_ms=20,
            context_tokens=64,
        ),
        script_protocol_deviations=(),
        evidence_records=records,
    )


def test_valid_observation_resolves_all_six_evidence_refs(
    case_and_owner: tuple[AuthoredCaseSpec, EvidenceOwner],
) -> None:
    case, owner = case_and_owner
    observation = _observation(case, owner, _records(case, owner))

    assert observation.evidence_integrity is EvidenceIntegrityStatus.VALID
    assert len(observation.evidence_resolutions) == 6
    assert all(
        item.status is EvidenceIntegrityStatus.VALID
        for item in observation.evidence_resolutions
    )
    assert observation.user_request_sha256 == canonical_sha256(
        case.user_request_raw
    )
    assert observation.observation_sha256 == canonical_sha256(
        observation.model_dump(
            mode="json",
            exclude={"observation_sha256"},
        )
    )


def test_missing_evidence_is_typed_invalid_and_never_becomes_empty_success(
    case_and_owner: tuple[AuthoredCaseSpec, EvidenceOwner],
) -> None:
    case, owner = case_and_owner
    records = _records(case, owner)[:-1]

    observation = _observation(case, owner, records)

    assert observation.evidence_integrity is EvidenceIntegrityStatus.INVALID
    assert any(
        problem.code == "evidence_missing"
        for problem in observation.evidence_problems
    )
    assert any(
        resolution.status is EvidenceIntegrityStatus.INVALID
        for resolution in observation.evidence_resolutions
    )


def test_corrupt_content_hash_is_typed_invalid(
    case_and_owner: tuple[AuthoredCaseSpec, EvidenceOwner],
) -> None:
    case, owner = case_and_owner
    records = list(_records(case, owner))
    records[0] = records[0].model_copy(
        update={
            "ref": records[0].ref.model_copy(
                update={"content_sha256": "f" * 64}
            )
        }
    )

    observation = _observation(case, owner, tuple(records))

    assert observation.evidence_integrity is EvidenceIntegrityStatus.INVALID
    assert any(
        problem.code == "evidence_content_hash_mismatch"
        for problem in observation.evidence_problems
    )


@pytest.mark.parametrize(
    "owner_update",
    [
        {"suite_content_hash": "f" * 64},
        {"case_id": "single_manuscript_search"},
        {"case_execution_id": f"benchmark_case_{'b' * 32}"},
        {"run_id": "general_run_20260730_120001_def456"},
        {"track": TrackKind.LIVE_PROVIDER},
    ],
)
def test_cross_identity_evidence_is_typed_invalid(
    case_and_owner: tuple[AuthoredCaseSpec, EvidenceOwner],
    owner_update: dict[str, object],
) -> None:
    case, owner = case_and_owner
    records = list(_records(case, owner))
    foreign_owner = owner.model_copy(update=owner_update)
    records[0] = records[0].model_copy(
        update={"ref": records[0].ref.model_copy(update={"owner": foreign_owner})}
    )

    observation = _observation(case, owner, tuple(records))

    assert observation.evidence_integrity is EvidenceIntegrityStatus.INVALID
    assert any(
        problem.code == "evidence_owner_mismatch"
        for problem in observation.evidence_problems
    )


def test_duplicate_evidence_id_is_conflict_not_last_write_wins(
    case_and_owner: tuple[AuthoredCaseSpec, EvidenceOwner],
) -> None:
    case, owner = case_and_owner
    records = _records(case, owner)

    observation = _observation(case, owner, (*records, records[0]))

    assert observation.evidence_integrity is EvidenceIntegrityStatus.INVALID
    assert any(
        problem.code == "evidence_id_conflict"
        for problem in observation.evidence_problems
    )


def test_wrong_probe_kind_or_selector_is_typed_invalid(
    case_and_owner: tuple[AuthoredCaseSpec, EvidenceOwner],
) -> None:
    case, owner = case_and_owner
    records = list(_records(case, owner))
    original = records[0]
    records[0] = records[0].model_copy(
        update={
            "ref": EvidenceRef(
                evidence_id=original.ref.evidence_id,
                kind="invocation",
                selector="count",
                owner=original.ref.owner,
                record_id=original.ref.record_id,
                content_sha256=original.ref.content_sha256,
            )
        }
    )

    observation = _observation(case, owner, tuple(records))

    assert observation.evidence_integrity is EvidenceIntegrityStatus.INVALID
    assert any(
        problem.code == "evidence_probe_mismatch"
        for problem in observation.evidence_problems
    )


def test_evidence_ref_rejects_dynamic_selector_and_executable_fields(
    case_and_owner: tuple[AuthoredCaseSpec, EvidenceOwner],
) -> None:
    case, owner = case_and_owner
    requirement = case.required_evidence[0]
    payload = {"observed": True}
    base = {
        "evidence_id": requirement.evidence_id,
        "kind": requirement.probe.kind,
        "selector": requirement.probe.selector,
        "owner": owner.model_dump(mode="json"),
        "record_id": "record_001",
        "content_sha256": canonical_sha256(payload),
    }

    with pytest.raises(ValidationError):
        EvidenceRef.model_validate({**base, "selector": "$.run.status"})
    with pytest.raises(ValidationError):
        EvidenceRef.model_validate({**base, "python_module": "os"})
    with pytest.raises(ValidationError):
        EvidenceRef.model_validate({**base, "shell": "echo unsafe"})


def test_observation_detects_post_build_tampering(
    case_and_owner: tuple[AuthoredCaseSpec, EvidenceOwner],
) -> None:
    case, owner = case_and_owner
    observation = _observation(case, owner, _records(case, owner))
    payload = observation.model_dump(mode="json")
    payload["user_request_raw"] = "被篡改的请求"

    with pytest.raises(ValidationError, match="请求|观察"):
        CaseObservation.model_validate(payload)
