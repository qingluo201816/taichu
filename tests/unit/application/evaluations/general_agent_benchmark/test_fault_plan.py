"""需求 8.11、11.1—11.4、11.6—11.7：恢复故障计划与密封后态。"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.faults import (
    FaultPlan,
    FaultPlanStateCorruptError,
    FaultPlanStateIdentityMismatchError,
    FaultPoint,
    FaultPressureAdapter,
    FaultRunIdentity,
    FaultStep,
    JsonFaultTriggerStore,
    RecoveryExpectedState,
    RecoveryResource,
    RecoverySentinelMismatchError,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    load_fixture_manifest,
)
from taichu.application.general_agent.faults import (
    GeneralAgentFaultContext,
    InjectedProcessTermination,
)

_FIXTURE_ROOT = Path(
    "tests/fixtures/evaluations/general_writing_agent_benchmark/fixtures/core_novel"
)
_MANIFEST_PATH = _FIXTURE_ROOT / "fixture-manifest.json"
_RECOVERY_ROOT = _FIXTURE_ROOT / "recovery"
_RECOVERY_CASES = (
    (
        "22_recovery_after_plan_before_execution",
        "fault_after_plan",
        (FaultPoint.PLAN_CREATED,),
        "completed",
        "reuse_checkpoint",
    ),
    (
        "23_recovery_tool_result_before_consumption",
        "fault_after_tool_result",
        (FaultPoint.CAPABILITY_RESULT_COMMITTED,),
        "completed",
        "reuse_checkpoint",
    ),
    (
        "24_recovery_subagent_interrupted",
        "fault_during_subagent",
        (FaultPoint.SUBAGENT_STARTED,),
        "completed",
        "reuse_checkpoint",
    ),
    (
        "25_recovery_waiting_authorization",
        "fault_waiting_authorization",
        (FaultPoint.AUTHORIZATION_REQUEST_DURABLE,),
        "waiting_human",
        "resume",
    ),
    (
        "26_recovery_after_write_before_effect_success",
        "fault_after_write",
        (FaultPoint.RESOURCE_WRITE_APPLIED,),
        "completed",
        "reconcile_effect",
    ),
    (
        "27_recovery_verification_interruption",
        "fault_during_verification",
        (FaultPoint.VERIFICATION_STARTED,),
        "completed",
        "reuse_checkpoint",
    ),
    (
        "28_recovery_multiple_interruptions",
        "fault_multiple_interruptions",
        (
            FaultPoint.PLAN_CREATED,
            FaultPoint.RESOURCE_WRITE_APPLIED,
        ),
        "completed",
        "reuse_checkpoint",
    ),
    (
        "29_recovery_checkpoint_integrity_or_version",
        "fault_checkpoint_integrity",
        (FaultPoint.CHECKPOINT_REVISION_VALIDATION,),
        "failed",
        "stop",
    ),
)


def _identity(suffix: str = "a") -> FaultRunIdentity:
    return FaultRunIdentity(
        conversation_id=f"conversation_{suffix}",
        run_id=f"run_{suffix}",
    )


def _plan(
    *,
    identity: FaultRunIdentity | None = None,
    plan_id: str = "fault_test_plan",
    points: tuple[FaultPoint, ...] = (
        FaultPoint.PLAN_CREATED,
        FaultPoint.VERIFICATION_STARTED,
    ),
) -> FaultPlan:
    return FaultPlan.seal(
        plan_id=plan_id,
        run_identity=identity or _identity(),
        steps=tuple(
            FaultStep(ordinal=index, point=point, once=True)
            for index, point in enumerate(points, start=1)
        ),
    )


def _load_case_assets(
    directory_name: str,
) -> tuple[FaultPlan, RecoveryExpectedState]:
    root = _RECOVERY_ROOT / directory_name
    return (
        FaultPlan.model_validate_json(
            (root / "fault-plan.json").read_text(encoding="utf-8")
        ),
        RecoveryExpectedState.model_validate_json(
            (root / "expected-state.json").read_text(encoding="utf-8")
        ),
    )


def test_fault_point_enum_is_fixed_and_has_no_case_specific_identifier() -> None:
    assert tuple(point.value for point in FaultPoint) == (
        "plan_created",
        "capability_result_committed",
        "subagent_started",
        "authorization_request_durable",
        "resource_write_applied",
        "verification_started",
        "checkpoint_revision_validation",
    )
    hook_parameters = inspect.signature(FaultPressureAdapter.on_fault_point).parameters
    assert "case_id" not in hook_parameters


def test_unknown_fault_point_duplicate_ordinal_and_non_once_fail_closed() -> None:
    base = _plan().model_dump(mode="json", by_alias=True)

    unknown = {
        **base,
        "steps": [{"ordinal": 1, "point": "case_22_only", "once": True}],
    }
    unknown["content_hash"] = "0" * 64
    with pytest.raises(ValidationError):
        FaultPlan.model_validate(unknown)

    duplicate = {
        **base,
        "steps": [
            {"ordinal": 1, "point": "plan_created", "once": True},
            {"ordinal": 1, "point": "verification_started", "once": True},
        ],
    }
    duplicate["content_hash"] = "0" * 64
    with pytest.raises(ValidationError):
        FaultPlan.model_validate(duplicate)

    non_once = {
        **base,
        "steps": [
            {"ordinal": 1, "point": "plan_created", "once": False},
        ],
    }
    non_once["content_hash"] = "0" * 64
    with pytest.raises(ValidationError):
        FaultPlan.model_validate(non_once)


def test_same_run_triggers_declared_faults_once_and_in_order(
    tmp_path: Path,
) -> None:
    plan = _plan()
    adapter = FaultPressureAdapter(JsonFaultTriggerStore(tmp_path))

    first = adapter.on_fault_point(
        plan=plan,
        run_identity=plan.run_identity,
        point=FaultPoint.PLAN_CREATED,
        ordinal=1,
    )
    repeated = adapter.on_fault_point(
        plan=plan,
        run_identity=plan.run_identity,
        point=FaultPoint.PLAN_CREATED,
        ordinal=1,
    )
    second = adapter.on_fault_point(
        plan=plan,
        run_identity=plan.run_identity,
        point=FaultPoint.VERIFICATION_STARTED,
        ordinal=2,
    )

    assert first.should_interrupt is True
    assert repeated.should_interrupt is False
    assert repeated.already_triggered is True
    assert second.should_interrupt is True
    assert second.state.triggered_ordinals == (1, 2)
    assert adapter.store.load(plan).triggered_ordinals == (1, 2)


def test_undeclared_or_out_of_order_hook_call_is_a_strict_deviation(
    tmp_path: Path,
) -> None:
    plan = _plan()
    adapter = FaultPressureAdapter(JsonFaultTriggerStore(tmp_path))

    with pytest.raises(ValueError, match="顺序"):
        adapter.on_fault_point(
            plan=plan,
            run_identity=plan.run_identity,
            point=FaultPoint.VERIFICATION_STARTED,
            ordinal=2,
        )
    with pytest.raises(ValueError, match="不匹配"):
        adapter.on_fault_point(
            plan=plan,
            run_identity=plan.run_identity,
            point=FaultPoint.RESOURCE_WRITE_APPLIED,
            ordinal=1,
        )


def test_run_identity_isolation_and_plan_ownership_fail_closed(
    tmp_path: Path,
) -> None:
    store = JsonFaultTriggerStore(tmp_path)
    first = _plan(identity=_identity("a"), plan_id="fault_plan_a")
    second = _plan(identity=_identity("b"), plan_id="fault_plan_b")
    adapter = FaultPressureAdapter(store)

    adapter.on_fault_point(
        plan=first,
        run_identity=first.run_identity,
        point=FaultPoint.PLAN_CREATED,
        ordinal=1,
    )
    assert store.load(second).triggered_ordinals == ()

    with pytest.raises(FaultPlanStateIdentityMismatchError):
        adapter.on_fault_point(
            plan=first,
            run_identity=second.run_identity,
            point=FaultPoint.PLAN_CREATED,
            ordinal=1,
        )

    conflicting_plan = _plan(
        identity=first.run_identity,
        plan_id="fault_plan_conflict",
    )
    with pytest.raises(FaultPlanStateIdentityMismatchError):
        store.load(conflicting_plan)


def test_corrupt_persisted_trigger_state_fails_closed(tmp_path: Path) -> None:
    plan = _plan()
    store = JsonFaultTriggerStore(tmp_path)
    adapter = FaultPressureAdapter(store)
    adapter.on_fault_point(
        plan=plan,
        run_identity=plan.run_identity,
        point=FaultPoint.PLAN_CREATED,
        ordinal=1,
    )

    state_path = store.state_path(plan.run_identity)
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    state_payload["triggered_ordinals"] = [2]
    state_payload["state_hash"] = canonical_sha256(
        {key: value for key, value in state_payload.items() if key != "state_hash"}
    )
    state_path.write_text(
        json.dumps(state_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(FaultPlanStateCorruptError):
        store.load(plan)

    state_path.write_text('{"schema": "broken"', encoding="utf-8")

    with pytest.raises(FaultPlanStateCorruptError):
        store.load(plan)


def test_recovery_22_to_29_assets_are_sealed_and_case_scoped() -> None:
    manifest = load_fixture_manifest(_MANIFEST_PATH)
    manifest_assets = {asset.asset_id: asset for asset in manifest.scenario_assets}
    run_identities: set[tuple[str, str]] = set()

    for (
        directory_name,
        asset_id,
        expected_points,
        terminal_status,
        recovery_action,
    ) in _RECOVERY_CASES:
        plan, expected = _load_case_assets(directory_name)
        identity_key = (
            plan.run_identity.conversation_id,
            plan.run_identity.run_id,
        )
        assert identity_key not in run_identities
        run_identities.add(identity_key)

        raw_plan = json.loads(
            (_RECOVERY_ROOT / directory_name / "fault-plan.json").read_text(
                encoding="utf-8"
            )
        )
        assert "case_id" not in raw_plan
        assert plan.plan_id == asset_id
        assert tuple(step.point for step in plan.steps) == expected_points
        assert tuple(step.ordinal for step in plan.steps) == tuple(
            range(1, len(expected_points) + 1)
        )
        assert expected.fault_plan_hash == plan.content_hash
        assert expected.run_identity == plan.run_identity
        assert expected.expected_triggered_ordinals == tuple(
            range(1, len(expected_points) + 1)
        )
        assert expected.final_run_status == terminal_status
        assert expected.recovery_action == recovery_action
        assert {item.resource for item in expected.resource_copies} == set(
            RecoveryResource
        )
        assert len(expected.resource_copies) == len(RecoveryResource)
        assert tuple(manifest_assets[asset_id].injection_points) == tuple(
            point.value for point in expected_points
        )


def test_abnormal_exit_cannot_hide_author_fact_or_workspace_change() -> None:
    _, expected = _load_case_assets("22_recovery_after_plan_before_execution")
    observed = {
        item.resource: item.expected_after_sha256 for item in expected.resource_copies
    }
    expected.verify_observed_after(observed)

    observed[RecoveryResource.KNOWLEDGE] = "f" * 64
    with pytest.raises(
        RecoverySentinelMismatchError,
        match="knowledge",
    ):
        expected.verify_observed_after(observed)


def test_bound_runtime_hook_is_driven_only_by_plan_and_persists_once(
    tmp_path: Path,
) -> None:
    store = JsonFaultTriggerStore(tmp_path)
    plan = _plan(
        points=(FaultPoint.CAPABILITY_RESULT_COMMITTED,),
    )
    hook = FaultPressureAdapter(store).bind(plan)
    context = GeneralAgentFaultContext(
        conversation_id=plan.run_identity.conversation_id,
        run_id=plan.run_identity.run_id,
        plan_revision=1,
        checkpoint_revision=3,
        node_id="read_chapter",
        attempt_id="attempt_read_chapter",
        capability_kind="tool",
        capability_name="read_manuscript",
        durable_identity="result_123",
    )

    hook.on_fault_point(
        point=FaultPoint.PLAN_CREATED,
        context=context,
    )
    assert store.load(plan).triggered_ordinals == ()

    with pytest.raises(InjectedProcessTermination):
        hook.on_fault_point(
            point=FaultPoint.CAPABILITY_RESULT_COMMITTED,
            context=context,
        )
    assert store.load(plan).triggered_ordinals == (1,)

    hook.on_fault_point(
        point=FaultPoint.CAPABILITY_RESULT_COMMITTED,
        context=context,
    )
    assert store.load(plan).triggered_ordinals == (1,)


def test_two_case_hooks_differ_only_by_plan_not_case_identifier(
    tmp_path: Path,
) -> None:
    adapter = FaultPressureAdapter(JsonFaultTriggerStore(tmp_path))
    first = _plan(
        identity=_identity("first"),
        plan_id="fault_first_plan",
        points=(FaultPoint.PLAN_CREATED,),
    )
    second = _plan(
        identity=_identity("second"),
        plan_id="fault_second_plan",
        points=(FaultPoint.VERIFICATION_STARTED,),
    )
    first_hook = adapter.bind(first)
    second_hook = adapter.bind(second)
    first_context = GeneralAgentFaultContext(
        conversation_id=first.run_identity.conversation_id,
        run_id=first.run_identity.run_id,
        plan_revision=1,
        checkpoint_revision=2,
    )
    second_context = GeneralAgentFaultContext(
        conversation_id=second.run_identity.conversation_id,
        run_id=second.run_identity.run_id,
        plan_revision=1,
        checkpoint_revision=2,
    )

    with pytest.raises(InjectedProcessTermination):
        first_hook.on_fault_point(
            point=FaultPoint.PLAN_CREATED,
            context=first_context,
        )
    first_hook.on_fault_point(
        point=FaultPoint.VERIFICATION_STARTED,
        context=first_context,
    )

    second_hook.on_fault_point(
        point=FaultPoint.PLAN_CREATED,
        context=second_context,
    )
    with pytest.raises(InjectedProcessTermination):
        second_hook.on_fault_point(
            point=FaultPoint.VERIFICATION_STARTED,
            context=second_context,
        )

    assert "case_id" not in inspect.signature(
        first_hook.on_fault_point
    ).parameters


def test_runtime_bound_plan_is_persisted_and_reloaded_without_case_identifier(
    tmp_path: Path,
) -> None:
    store = JsonFaultTriggerStore(tmp_path)
    adapter = FaultPressureAdapter(store)
    steps = (
        FaultStep(
            ordinal=1,
            point=FaultPoint.PLAN_CREATED,
            once=True,
        ),
    )
    first_hook = adapter.bind_runtime(
        plan_id="runtime_bound_plan",
        steps=steps,
    )
    context = GeneralAgentFaultContext(
        conversation_id="conversation_runtime_bound",
        run_id="general_run_20260730_150000_abcdef",
        plan_revision=1,
        checkpoint_revision=3,
    )

    with pytest.raises(InjectedProcessTermination):
        first_hook.on_fault_point(
            point=FaultPoint.PLAN_CREATED,
            context=context,
        )

    assert first_hook.resolved_plan is not None
    assert first_hook.resolved_plan.run_identity == FaultRunIdentity(
        conversation_id=context.conversation_id,
        run_id=context.run_id,
    )
    assert store.plan_path(first_hook.resolved_plan.run_identity).is_file()

    restarted_hook = FaultPressureAdapter(
        JsonFaultTriggerStore(tmp_path)
    ).bind_runtime(
        plan_id="runtime_bound_plan",
        steps=steps,
    )
    restarted_hook.on_fault_point(
        point=FaultPoint.PLAN_CREATED,
        context=context,
    )

    assert restarted_hook.resolved_plan == first_hook.resolved_plan
    assert store.load(first_hook.resolved_plan).triggered_ordinals == (1,)
