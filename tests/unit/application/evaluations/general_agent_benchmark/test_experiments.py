"""需求 8.1-8.31：实验可比性与模型比较准入。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from taichu.application.evaluations.general_agent_benchmark.experiments import (
    ComparisonAdmissionInput,
    ExperimentArm,
    ExperimentService,
    ExperimentSpec,
    ModelCandidateEvidence,
    compare_experiment,
    evaluate_model_comparison_admission,
)


def _arm(
    arm_id: str,
    *,
    suite_hash: str = "a" * 64,
    fixture_hash: str = "b" * 64,
    catalog_hash: str = "c" * 64,
    provider_id: str | None = None,
    model_id: str | None = None,
    settings: dict[str, str] | None = None,
) -> ExperimentArm:
    if provider_id is not None and model_id is None:
        model_id = "model_a"
    return ExperimentArm(
        arm_id=arm_id,
        track="live_provider" if provider_id else "synthetic",
        suite_content_hash=suite_hash,
        fixture_hash=fixture_hash,
        selected_case_ids=("case_a", "case_b"),
        user_input_hash="d" * 64,
        conditions_hash="e" * 64,
        capability_catalog_hash=catalog_hash,
        authorization_policy_hash="f" * 64,
        verifier_registry_hash="1" * 64,
        gate_policy_hash="2" * 64,
        decode_configuration_hash="3" * 64,
        environment_hash="4" * 64,
        provider_id=provider_id,
        model_id=model_id,
        repetition_count=2,
        declared_settings=settings or {},
    )


def _memory_experiment(
    *,
    treatment: ExperimentArm | None = None,
    key: str = "memory-experiment",
) -> ExperimentSpec:
    return ExperimentSpec(
        experiment_id="memory_policy_experiment",
        name="运行记忆策略实验",
        mechanism="memory",
        control=_arm(
            "control",
            settings={"runtime_memory_policy_identity": "disabled"},
        ),
        treatment=treatment
        or _arm(
            "treatment",
            settings={"runtime_memory_policy_identity": "active_only"},
        ),
        declared_differences=(
            "declared_settings.runtime_memory_policy_identity",
        ),
        stability_threshold_profile="memory_stability",
        idempotency_key=key,
    )


def test_declared_single_mechanism_difference_is_comparable() -> None:
    result = compare_experiment(_memory_experiment())

    assert result.status == "comparable"
    assert result.actual_differences == (
        "declared_settings.runtime_memory_policy_identity",
    )
    assert result.undeclared_differences == ()
    assert result.reason_key == "实验条件一致，可以进行机制比较。"


@pytest.mark.parametrize(
    ("field", "value", "expected_path"),
    [
        ("suite_hash", "9" * 64, "suite_content_hash"),
        ("fixture_hash", "8" * 64, "fixture_hash"),
        ("catalog_hash", "7" * 64, "capability_catalog_hash"),
        ("provider_id", "provider_b", "provider_id"),
    ],
)
def test_frozen_condition_drift_is_incomparable(
    field: str,
    value: str,
    expected_path: str,
) -> None:
    kwargs: dict[str, object] = {
        "settings": {"runtime_memory_policy_identity": "active_only"},
    }
    kwargs[field] = value
    treatment = _arm("treatment", **kwargs)

    result = compare_experiment(_memory_experiment(treatment=treatment))

    assert result.status == "incomparable"
    assert expected_path in result.undeclared_differences
    assert result.relative_delta_allowed is False


def test_unknown_or_cross_mechanism_difference_path_is_rejected() -> None:
    with pytest.raises(ValidationError, match="memory"):
        ExperimentSpec(
            **{
                **_memory_experiment().model_dump(),
                "declared_differences": (
                    "declared_settings.context_projection_policy_identity",
                ),
            }
        )


def test_experiment_creation_and_run_binding_are_idempotent() -> None:
    service = ExperimentService()
    spec = _memory_experiment()

    first = service.create(spec)
    repeated = service.create(spec)
    bound = service.bind_run(
        experiment_id=spec.experiment_id,
        arm_id="control",
        run_id="benchmark_run_20260727T000001Z_abcdef123456",
    )

    assert repeated == first
    assert bound.control_run_ids == (
        "benchmark_run_20260727T000001Z_abcdef123456",
    )
    with pytest.raises(ValueError, match="幂等键"):
        service.create(_memory_experiment(key="another-key"))


def _candidate(**updates: object) -> ModelCandidateEvidence:
    values: dict[str, object] = {
        "candidate_id": "deepseek_v4_pro",
        "requested_model_ref": "deepseek-v4-pro",
        "probe_succeeded": True,
        "actual_provider_id": "deepseek",
        "actual_model_id": "deepseek-v4-pro",
        "fallback_used": False,
        "replay_available": True,
        "usage_available": True,
        "cost_available": True,
        "error_code": None,
    }
    values.update(updates)
    return ModelCandidateEvidence(**values)


def _admission_input(**updates: object) -> ComparisonAdmissionInput:
    values: dict[str, object] = {
        "iteration_state": "ready_for_comparison",
        "code_hash": "a" * 64,
        "suite_hash": "b" * 64,
        "fixture_hash": "c" * 64,
        "case_set_hash": "d" * 64,
        "per_case_budgets_hash": "e" * 64,
        "capability_catalog_hash": "f" * 64,
        "authorization_policy_hash": "1" * 64,
        "decode_configuration_hash": "2" * 64,
        "environment_hash": "3" * 64,
        "all_system_defects_processed": True,
        "symmetry_gates_passed": True,
        "benchmark_verifier_defects_closed": True,
        "core_gates_passed": True,
        "candidates": (_candidate(),),
    }
    values.update(updates)
    return ComparisonAdmissionInput(**values)


def test_model_comparison_requires_closed_first_live_and_clean_candidates() -> None:
    admitted = evaluate_model_comparison_admission(_admission_input())
    blocked = evaluate_model_comparison_admission(
        _admission_input(
            iteration_state="closing_system_defects",
            all_system_defects_processed=False,
            candidates=(_candidate(usage_available=False),),
        )
    )

    assert admitted.admitted is True
    assert admitted.blocked_reasons == ()
    assert admitted.ranking_candidate_ids == ("deepseek_v4_pro",)
    assert blocked.admitted is False
    assert blocked.status == "blocked"
    assert blocked.ranking_candidate_ids == ()
    assert blocked.blocked_reasons == (
        "首轮迭代尚未达到可比较状态。",
        "仍有系统缺陷未确认关闭。",
        "候选 deepseek_v4_pro 缺少用量证据。",
    )
