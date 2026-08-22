"""需求 1.8、12.7、12.8：三层工件身份与关系专属比较。"""

from __future__ import annotations

from collections.abc import Iterable

import pytest
from pydantic import ValidationError

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.experiments import (
    ArtifactIdentity,
    ArtifactRelationKind,
    CaseContractIdentity,
    DeclaredDifferences,
    DifferenceKind,
    IdentityFailureCode,
    IdentityRelationStatus,
    compare_live_model_artifacts,
    qualify_synthetic_for_live,
)

_SYNTHETIC_CASE_IDS = tuple(f"case_{index:02d}" for index in range(1, 38))
_LIVE_CASE_IDS = _SYNTHETIC_CASE_IDS[:21]


def _hash(value: object) -> str:
    return canonical_sha256(value)


def _case_contracts(
    case_ids: Iterable[str],
    *,
    changed_case_id: str | None = None,
) -> tuple[CaseContractIdentity, ...]:
    return tuple(
        CaseContractIdentity(
            case_id=case_id,
            contract_hash=_hash(
                {
                    "case_id": case_id,
                    "contract": ("changed" if case_id == changed_case_id else "stable"),
                }
            ),
        )
        for case_id in case_ids
    )


def _synthetic_identity(
    *,
    case_ids: tuple[str, ...] = _SYNTHETIC_CASE_IDS,
    admission_passed: bool = True,
    **updates: object,
) -> ArtifactIdentity:
    values: dict[str, object] = {
        "artifact_schema": "taichu.general_agent_benchmark.baseline@2",
        "artifact_kind": "synthetic_baseline",
        "artifact_ref": "baselines/synthetic-37.json",
        "artifact_content_hash": _hash("synthetic-artifact"),
        "suite_content_hash": _hash("suite"),
        "selected_case_ids": case_ids,
        "case_contracts": _case_contracts(case_ids),
        "track": "synthetic",
        "fixture_snapshot_hash": _hash("fixture"),
        "capability_catalog_hash": _hash("catalog"),
        "oracle_rule_set_hash": _hash("oracle"),
        "runtime_config_hash": _hash("runtime-config"),
        "runtime_code_snapshot_hash": _hash("runtime-code"),
        "runner_protocol_hash": _hash("runner"),
        "synthetic_script_identity": _hash("script"),
        "synthetic_admission_passed": admission_passed,
    }
    values.update(updates)
    return ArtifactIdentity.create(**values)


def _live_identity(
    *,
    artifact_ref: str = "runs/provider-a-model-a.json",
    artifact_marker: str = "artifact-a",
    case_ids: tuple[str, ...] = _LIVE_CASE_IDS,
    changed_case_id: str | None = None,
    provider_id: str = "provider_a",
    model_id: str = "model-a",
    decode_marker: str = "decode-a",
    request_id: str = "provider-request-a",
    run_id: str = "provider-run-a",
    observation_marker: str = "a",
    **updates: object,
) -> ArtifactIdentity:
    values: dict[str, object] = {
        "artifact_schema": "taichu.general_agent_benchmark.live_run@2",
        "artifact_kind": "live_run",
        "artifact_ref": artifact_ref,
        "artifact_content_hash": _hash(artifact_marker),
        "suite_content_hash": _hash("suite"),
        "selected_case_ids": case_ids,
        "case_contracts": _case_contracts(
            case_ids,
            changed_case_id=changed_case_id,
        ),
        "track": "live_provider",
        "fixture_snapshot_hash": _hash("fixture"),
        "capability_catalog_hash": _hash("catalog"),
        "oracle_rule_set_hash": _hash("oracle"),
        "runtime_config_hash": _hash("runtime-config"),
        "runtime_code_snapshot_hash": _hash("runtime-code"),
        "runner_protocol_hash": _hash("runner"),
        "provider_id": provider_id,
        "model_id": model_id,
        "decode_configuration_hash": _hash(decode_marker),
        "provider_request_id": request_id,
        "provider_run_id": run_id,
        "usage_hash": _hash(f"usage-{observation_marker}"),
        "latency_hash": _hash(f"latency-{observation_marker}"),
        "output_hash": _hash(f"output-{observation_marker}"),
        "result_hash": _hash(f"result-{observation_marker}"),
    }
    values.update(updates)
    return ArtifactIdentity.create(**values)


def _declare(
    relation: ArtifactRelationKind,
    baseline: ArtifactIdentity,
    candidate: ArtifactIdentity,
    kinds: Iterable[DifferenceKind],
) -> DeclaredDifferences:
    return DeclaredDifferences.create(
        relation_kind=relation,
        baseline=baseline,
        candidate=candidate,
        difference_kinds=tuple(kinds),
    )


def _synthetic_live_declaration(
    synthetic: ArtifactIdentity,
    live: ArtifactIdentity,
) -> DeclaredDifferences:
    return _declare(
        ArtifactRelationKind.SYNTHETIC_TO_LIVE,
        synthetic,
        live,
        (
            DifferenceKind.TRACK,
            DifferenceKind.SELECTED_CASE_SET,
            DifferenceKind.EXECUTION_IDENTITY,
        ),
    )


def _live_pair() -> tuple[ArtifactIdentity, ArtifactIdentity]:
    baseline = _live_identity()
    candidate = _live_identity(
        artifact_ref="runs/provider-b-model-b.json",
        artifact_marker="artifact-b",
        provider_id="provider_b",
        model_id="model-b",
        decode_marker="decode-b",
        request_id="provider-request-b",
        run_id="provider-run-b",
        observation_marker="b",
    )
    return baseline, candidate


def _live_pair_declaration(
    baseline: ArtifactIdentity,
    candidate: ArtifactIdentity,
) -> DeclaredDifferences:
    return _declare(
        ArtifactRelationKind.LIVE_MODEL_COMPARISON,
        baseline,
        candidate,
        (
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
        ),
    )


def test_synthetic_37_qualifies_matching_live_21() -> None:
    synthetic = _synthetic_identity()
    live = _live_identity()

    result = qualify_synthetic_for_live(
        synthetic,
        live,
        _synthetic_live_declaration(synthetic, live),
    )

    assert result.status is IdentityRelationStatus.ELIGIBLE
    assert result.failure_code is None
    assert result.comparability_key is not None
    assert result.comparability_key.comparable_case_ids == _LIVE_CASE_IDS
    assert result.qualified_by_synthetic_ref == synthetic.artifact_ref
    assert result.actual_difference_kinds == (
        DifferenceKind.EXECUTION_IDENTITY,
        DifferenceKind.SELECTED_CASE_SET,
        DifferenceKind.TRACK,
    )


def test_synthetic_must_be_complete_and_passed_before_live_qualification() -> None:
    live = _live_identity()
    for synthetic in (
        _synthetic_identity(admission_passed=False),
        _synthetic_identity(case_ids=_SYNTHETIC_CASE_IDS[:-1]),
    ):
        result = qualify_synthetic_for_live(
            synthetic,
            live,
            _synthetic_live_declaration(synthetic, live),
        )

        assert result.status is IdentityRelationStatus.REJECTED
        assert result.failure_code is IdentityFailureCode.NOT_QUALIFIED
        assert result.comparability_key is None


@pytest.mark.parametrize(
    ("field", "marker", "expected"),
    [
        ("suite_content_hash", "other-suite", "INCOMPATIBLE_SUITE"),
        ("fixture_snapshot_hash", "other-fixture", "INCOMPATIBLE_FIXTURE"),
        (
            "capability_catalog_hash",
            "other-catalog",
            "INCOMPATIBLE_CATALOG",
        ),
        ("oracle_rule_set_hash", "other-oracle", "INCOMPATIBLE_ORACLE"),
        ("runtime_config_hash", "other-runtime", "INCOMPATIBLE_RUNTIME"),
        (
            "runtime_code_snapshot_hash",
            "other-runtime-code",
            "INCOMPATIBLE_RUNTIME",
        ),
    ],
)
def test_synthetic_live_rejects_frozen_identity_drift(
    field: str,
    marker: str,
    expected: str,
) -> None:
    synthetic = _synthetic_identity()
    live = _live_identity(**{field: _hash(marker)})

    result = qualify_synthetic_for_live(
        synthetic,
        live,
        _synthetic_live_declaration(synthetic, live),
    )

    assert result.failure_code == expected
    assert result.comparability_key is None


def test_synthetic_live_rejects_case_set_and_projection_mismatch() -> None:
    synthetic = _synthetic_identity()
    wrong_set = _live_identity(case_ids=_LIVE_CASE_IDS[:-1])
    wrong_projection = _live_identity(changed_case_id=_LIVE_CASE_IDS[-1])

    case_set_result = qualify_synthetic_for_live(
        synthetic,
        wrong_set,
        _synthetic_live_declaration(synthetic, wrong_set),
    )
    projection_result = qualify_synthetic_for_live(
        synthetic,
        wrong_projection,
        _synthetic_live_declaration(synthetic, wrong_projection),
    )

    assert case_set_result.failure_code is IdentityFailureCode.CASE_SET_MISMATCH
    assert (
        projection_result.failure_code is IdentityFailureCode.CASE_PROJECTION_MISMATCH
    )


def test_live_model_artifacts_are_comparable_only_through_live_relation() -> None:
    baseline, candidate = _live_pair()

    result = compare_live_model_artifacts(
        baseline,
        candidate,
        _live_pair_declaration(baseline, candidate),
    )

    assert result.status is IdentityRelationStatus.COMPARABLE
    assert result.failure_code is None
    assert result.comparability_key is not None
    assert result.comparability_key.comparable_case_ids == _LIVE_CASE_IDS
    assert set(result.actual_difference_kinds) == {
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


@pytest.mark.parametrize(
    ("field", "marker", "expected"),
    [
        ("suite_content_hash", "other-suite", "INCOMPATIBLE_SUITE"),
        ("fixture_snapshot_hash", "other-fixture", "INCOMPATIBLE_FIXTURE"),
        (
            "capability_catalog_hash",
            "other-catalog",
            "INCOMPATIBLE_CATALOG",
        ),
        ("oracle_rule_set_hash", "other-oracle", "INCOMPATIBLE_ORACLE"),
        ("runtime_config_hash", "other-runtime", "INCOMPATIBLE_RUNTIME"),
    ],
)
def test_live_model_comparison_rejects_frozen_identity_drift(
    field: str,
    marker: str,
    expected: str,
) -> None:
    baseline, candidate = _live_pair()
    candidate = _live_identity(
        artifact_ref=candidate.artifact_ref or "",
        artifact_marker="artifact-b",
        provider_id=candidate.provider_id or "provider_b",
        model_id=candidate.model_id or "model-b",
        decode_marker="decode-b",
        request_id=candidate.provider_request_id or "provider-request-b",
        run_id=candidate.provider_run_id or "provider-run-b",
        observation_marker="b",
        **{field: _hash(marker)},
    )

    result = compare_live_model_artifacts(
        baseline,
        candidate,
        _live_pair_declaration(baseline, candidate),
    )

    assert result.failure_code == expected


def test_live_model_comparison_rejects_case_set_and_projection_mismatch() -> None:
    baseline = _live_identity()
    wrong_set = _live_identity(
        case_ids=_LIVE_CASE_IDS[:-1],
        artifact_ref="runs/wrong-set.json",
        artifact_marker="wrong-set",
        request_id="wrong-set-request",
        run_id="wrong-set-run",
        observation_marker="wrong-set",
    )
    wrong_projection = _live_identity(
        changed_case_id=_LIVE_CASE_IDS[-1],
        artifact_ref="runs/wrong-projection.json",
        artifact_marker="wrong-projection",
        request_id="wrong-projection-request",
        run_id="wrong-projection-run",
        observation_marker="wrong-projection",
    )

    set_result = compare_live_model_artifacts(
        baseline,
        wrong_set,
        _declare(
            ArtifactRelationKind.LIVE_MODEL_COMPARISON,
            baseline,
            wrong_set,
            (),
        ),
    )
    projection_result = compare_live_model_artifacts(
        baseline,
        wrong_projection,
        _declare(
            ArtifactRelationKind.LIVE_MODEL_COMPARISON,
            baseline,
            wrong_projection,
            (),
        ),
    )

    assert set_result.failure_code is IdentityFailureCode.CASE_SET_MISMATCH
    assert (
        projection_result.failure_code is IdentityFailureCode.CASE_PROJECTION_MISMATCH
    )


def test_incomplete_identity_is_a_typed_failure() -> None:
    baseline, candidate = _live_pair()
    candidate = candidate.model_copy(update={"oracle_rule_set_hash": None})

    result = compare_live_model_artifacts(
        baseline,
        candidate,
        _live_pair_declaration(baseline, candidate),
    )

    assert result.failure_code is IdentityFailureCode.IDENTITY_INCOMPLETE
    assert "candidate.oracle_rule_set_hash" in result.identity_problems


def test_actual_differences_must_exactly_equal_declared_differences() -> None:
    baseline, candidate = _live_pair()
    complete = _live_pair_declaration(baseline, candidate)
    missing_model = complete.model_copy(
        update={
            "differences": tuple(
                item
                for item in complete.differences
                if item.kind is not DifferenceKind.MODEL
            )
        }
    )
    same_decode = _live_identity(
        artifact_ref="runs/provider-b-model-b.json",
        artifact_marker="artifact-b",
        provider_id="provider_b",
        model_id="model-b",
        decode_marker="decode-a",
        request_id="provider-request-b",
        run_id="provider-run-b",
        observation_marker="b",
    )
    overreported_decode = _declare(
        ArtifactRelationKind.LIVE_MODEL_COMPARISON,
        baseline,
        same_decode,
        (
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
        ),
    )

    missing_result = compare_live_model_artifacts(
        baseline,
        candidate,
        missing_model,
    )
    overreported_result = compare_live_model_artifacts(
        baseline,
        same_decode,
        overreported_decode,
    )

    assert missing_result.failure_code is IdentityFailureCode.UNDECLARED_DIFFERENCE
    assert missing_result.undeclared_difference_kinds == (DifferenceKind.MODEL,)
    assert overreported_result.failure_code is IdentityFailureCode.UNDECLARED_DIFFERENCE
    assert overreported_result.overdeclared_difference_kinds == (
        DifferenceKind.DECODE_CONFIGURATION,
    )


def test_relation_allowlist_is_fixed_and_caller_cannot_ignore_runner_drift() -> None:
    baseline, candidate = _live_pair()
    with pytest.raises(ValidationError, match="live_model_comparison"):
        _declare(
            ArtifactRelationKind.LIVE_MODEL_COMPARISON,
            baseline,
            candidate,
            (DifferenceKind.SELECTED_CASE_SET,),
        )

    runner_drift = candidate.model_copy(
        update={"runner_protocol_hash": _hash("other-runner")}
    )
    ordinary_declaration = _live_pair_declaration(baseline, runner_drift)
    result = compare_live_model_artifacts(
        baseline,
        runner_drift,
        ordinary_declaration,
    )

    assert result.failure_code is IdentityFailureCode.UNDECLARED_DIFFERENCE
    assert result.undeclared_difference_kinds == (DifferenceKind.RUNNER_PROTOCOL,)
