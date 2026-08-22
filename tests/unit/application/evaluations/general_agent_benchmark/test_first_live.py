"""需求 15.1、15.2、15.3、15.16、15.18、15.23：首轮冻结。"""

from __future__ import annotations

import pytest

from taichu.application.evaluations.general_agent_benchmark.first_live import (
    FirstLiveIterationManifest,
    FirstLiveIterationService,
    FirstLiveRevisionConflict,
    FirstLiveStateError,
)


def _service_and_iteration(
    *,
    iteration_id: str = "deepseek_first_live",
) -> tuple[FirstLiveIterationService, FirstLiveIterationManifest]:
    service = FirstLiveIterationService()
    manifest = service.create_iteration(
        iteration_id=iteration_id,
        code_hash="a" * 64,
        suite_hash="b" * 64,
        fixture_hash="c" * 64,
        capability_catalog_hash="d" * 64,
        selected_case_ids=("case_a", "case_b"),
        synthetic_qualification_artifact_refs=("synthetic_artifact_a",),
        synthetic_suite_passed=True,
        core_gates_passed=True,
        memory_gates_passed=True,
        mechanism_gates_passed=True,
    )
    return service, manifest


def test_only_deepseek_v4_pro_can_start_before_first_live_closure() -> None:
    service, manifest = _service_and_iteration()

    assert manifest.state == "ready_for_deepseek"
    with pytest.raises(FirstLiveStateError, match="DeepSeek V4 Pro"):
        service.start(
            "deepseek_first_live",
            expected_revision=0,
            requested_model_ref="gpt-5.6",
        )
    running = service.start(
        "deepseek_first_live",
        expected_revision=0,
        requested_model_ref="deepseek-v4-pro",
    )
    with pytest.raises(FirstLiveStateError, match="多模型比较"):
        service.require_comparison_ready("deepseek_first_live")

    assert running.state == "deepseek_running"
    assert running.revision == 1


def test_complete_first_live_is_frozen_and_cannot_be_overwritten() -> None:
    service, _ = _service_and_iteration()
    service.start(
        "deepseek_first_live",
        expected_revision=0,
        requested_model_ref="deepseek-v4-pro",
    )

    artifact, manifest = service.freeze(
        "deepseek_first_live",
        expected_revision=1,
        provider_state="completed",
        completed_case_ids=("case_a", "case_b"),
        suite_artifact_ref="suite_artifact_a",
        actual_provider_id="deepseek",
        actual_model_id="deepseek-v4-pro",
        probe_succeeded=True,
        fallback_used=False,
        replay_available=True,
        usage_available=True,
        cost_available=True,
        error_code=None,
        failure_record_refs=(),
    )

    assert artifact.complete is True
    assert artifact.requested_model_ref == "deepseek-v4-pro"
    assert manifest.first_live_artifact_ref == artifact.artifact_id
    assert manifest.state == "classifying"
    with pytest.raises(FirstLiveStateError, match="已经冻结"):
        service.freeze(
            "deepseek_first_live",
            expected_revision=manifest.revision,
            provider_state="completed",
            completed_case_ids=("case_a", "case_b"),
            suite_artifact_ref="suite_artifact_overwrite",
            actual_provider_id="deepseek",
            actual_model_id="deepseek-v4-pro",
            probe_succeeded=True,
            fallback_used=False,
            replay_available=True,
            usage_available=True,
            cost_available=True,
            error_code=None,
            failure_record_refs=(),
        )
    assert service.get_artifact(artifact.artifact_id) == artifact


def test_incomplete_completed_run_is_rejected() -> None:
    service, _ = _service_and_iteration()
    service.start(
        "deepseek_first_live",
        expected_revision=0,
        requested_model_ref="deepseek-v4-pro",
    )

    with pytest.raises(FirstLiveStateError, match="完整案例集合"):
        service.freeze(
            "deepseek_first_live",
            expected_revision=1,
            provider_state="completed",
            completed_case_ids=("case_a",),
            suite_artifact_ref="suite_artifact_a",
            actual_provider_id="deepseek",
            actual_model_id="deepseek-v4-pro",
            probe_succeeded=True,
            fallback_used=False,
            replay_available=True,
            usage_available=True,
            cost_available=True,
            error_code=None,
            failure_record_refs=(),
        )


@pytest.mark.parametrize("provider_state", ["blocked", "error"])
def test_blocked_and_error_attempts_preserve_state_without_fake_completion(
    provider_state: str,
) -> None:
    service, _ = _service_and_iteration()
    service.start(
        "deepseek_first_live",
        expected_revision=0,
        requested_model_ref="deepseek-v4-pro",
    )

    artifact, manifest = service.freeze(
        "deepseek_first_live",
        expected_revision=1,
        provider_state=provider_state,
        completed_case_ids=("case_a",),
        suite_artifact_ref=None,
        actual_provider_id="deepseek",
        actual_model_id="deepseek-v4-pro",
        probe_succeeded=provider_state == "error",
        fallback_used=False,
        replay_available=False,
        usage_available=False,
        cost_available=False,
        error_code="PROVIDER_FAILURE",
        failure_record_refs=("failure_a",),
    )

    assert artifact.provider_state == provider_state
    assert artifact.complete is False
    assert manifest.state == "blocked"
    assert manifest.problems


def test_new_iteration_appends_without_rewriting_previous_artifact_and_uses_cas() -> None:
    service, _ = _service_and_iteration()
    service.start(
        "deepseek_first_live",
        expected_revision=0,
        requested_model_ref="deepseek-v4-pro",
    )
    first, _ = service.freeze(
        "deepseek_first_live",
        expected_revision=1,
        provider_state="error",
        completed_case_ids=(),
        suite_artifact_ref=None,
        actual_provider_id="deepseek",
        actual_model_id="deepseek-v4-pro",
        probe_succeeded=True,
        fallback_used=False,
        replay_available=False,
        usage_available=False,
        cost_available=False,
        error_code="UPSTREAM_ERROR",
        failure_record_refs=("failure_a",),
    )

    second_manifest = service.create_iteration(
        iteration_id="deepseek_first_live_retry",
        code_hash="a" * 64,
        suite_hash="b" * 64,
        fixture_hash="c" * 64,
        capability_catalog_hash="d" * 64,
        selected_case_ids=("case_a", "case_b"),
        synthetic_qualification_artifact_refs=("synthetic_artifact_a",),
        synthetic_suite_passed=True,
        core_gates_passed=True,
        memory_gates_passed=True,
        mechanism_gates_passed=True,
        prior_iteration_ids=("deepseek_first_live",),
    )
    assert second_manifest.prior_iteration_ids == ("deepseek_first_live",)
    assert service.list_iterations() == (
        service.get_manifest("deepseek_first_live"),
        second_manifest,
    )
    with pytest.raises(FirstLiveRevisionConflict):
        service.start(
            "deepseek_first_live",
            expected_revision=0,
            requested_model_ref="deepseek-v4-pro",
        )
    assert service.get_artifact(first.artifact_id) == first
