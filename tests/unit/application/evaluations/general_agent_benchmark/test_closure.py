"""需求 15.14-15.40：问题关闭协调与模型比较入场门禁。"""

from __future__ import annotations

import pytest

from taichu.application.evaluations.general_agent_benchmark.closure import (
    ClosureEvidence,
    ClosureLeaseConflict,
    IssueClosureCoordinator,
    ModelComparisonRequest,
    ModelComparisonService,
)
from taichu.application.evaluations.general_agent_benchmark.experiments import (
    ComparisonAdmissionInput,
    ModelCandidateEvidence,
)


def _evidence(**updates: object) -> ClosureEvidence:
    values: dict[str, object] = {
        "intent_id": f"issue_intent_{'a' * 64}",
        "issue_id": "issue_a",
        "issue_revision": 3,
        "targeted_case_passed": True,
        "full_suite_passed": True,
        "rerun_suite_hash": "b" * 64,
        "current_suite_hash": "b" * 64,
        "core_gates_passed": True,
        "symmetry_gate_passed": True,
        "issue_status": "processed",
        "first_live_artifact_ref": f"first_live_{'c' * 64}",
        "evidence_refs": ("targeted_run", "full_suite", "issue_readback"),
    }
    values.update(updates)
    return ClosureEvidence(**values)


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"targeted_case_passed": False}, "定向案例复跑未通过。"),
        ({"full_suite_passed": False}, "当前套件全量复跑未通过。"),
        ({"rerun_suite_hash": "d" * 64}, "复跑套件哈希不是当前套件。"),
        ({"core_gates_passed": False}, "核心硬门禁未通过。"),
        ({"symmetry_gate_passed": False}, "问题关联对称性门禁未通过。"),
        ({"issue_status": "todo"}, "Inbox 问题尚未读回为已处理。"),
        ({"first_live_artifact_ref": None}, "首轮工件尚未冻结。"),
    ],
)
def test_each_missing_closure_precondition_blocks(
    updates: dict[str, object],
    reason: str,
) -> None:
    decision = IssueClosureCoordinator.evaluate(_evidence(**updates))

    assert decision.ready is False
    assert reason in decision.blocked_reasons


def test_closure_lease_has_one_owner_and_commit_is_content_addressed() -> None:
    coordinator = IssueClosureCoordinator()
    lease = coordinator.acquire_lease(
        intent_id=f"issue_intent_{'a' * 64}",
        owner_id="coordinator_a",
        expected_revision=0,
    )
    with pytest.raises(ClosureLeaseConflict):
        coordinator.acquire_lease(
            intent_id=f"issue_intent_{'a' * 64}",
            owner_id="coordinator_b",
            expected_revision=0,
        )

    first = coordinator.commit(
        _evidence(),
        owner_id="coordinator_a",
        expected_lease_revision=lease.revision,
    )
    repeated = coordinator.commit(
        _evidence(),
        owner_id="coordinator_a",
        expected_lease_revision=lease.revision,
    )

    assert first == repeated
    assert first.ready is True
    assert first.closure_id.startswith("issue_closure_")


def _admission() -> ComparisonAdmissionInput:
    return ComparisonAdmissionInput(
        iteration_state="ready_for_comparison",
        code_hash="1" * 64,
        suite_hash="2" * 64,
        fixture_hash="3" * 64,
        case_set_hash="4" * 64,
        per_case_budgets_hash="5" * 64,
        capability_catalog_hash="6" * 64,
        authorization_policy_hash="7" * 64,
        decode_configuration_hash="8" * 64,
        environment_hash="9" * 64,
        all_system_defects_processed=True,
        symmetry_gates_passed=True,
        benchmark_verifier_defects_closed=True,
        core_gates_passed=True,
        candidates=(
            ModelCandidateEvidence(
                candidate_id="deepseek_v4_pro",
                requested_model_ref="deepseek-v4-pro",
                probe_succeeded=True,
                actual_provider_id="deepseek",
                actual_model_id="deepseek-v4-pro",
                fallback_used=False,
                replay_available=True,
                usage_available=True,
                cost_available=True,
                error_code=None,
            ),
        ),
    )


def test_model_comparison_requires_frozen_first_live_and_ready_closures() -> None:
    service = ModelComparisonService()
    blocked = service.create(
        ModelComparisonRequest(
            comparison_id="comparison_blocked",
            idempotency_key="comparison-blocked",
            first_live_artifact_ref=None,
            admission_input=_admission(),
            closure_decisions=(
                IssueClosureCoordinator.evaluate(
                    _evidence(issue_status="todo")
                ),
            ),
        )
    )

    assert blocked.admitted is False
    assert blocked.ranking_candidate_ids == ()
    assert "首轮工件尚未冻结。" in blocked.blocked_reasons
    assert "Inbox 问题尚未读回为已处理。" in blocked.blocked_reasons


def test_model_comparison_admission_is_issued_once_idempotently() -> None:
    coordinator = IssueClosureCoordinator()
    lease = coordinator.acquire_lease(
        intent_id=f"issue_intent_{'a' * 64}",
        owner_id="coordinator_a",
        expected_revision=0,
    )
    closure = coordinator.commit(
        _evidence(),
        owner_id="coordinator_a",
        expected_lease_revision=lease.revision,
    )
    request = ModelComparisonRequest(
        comparison_id="comparison_ready",
        idempotency_key="comparison-ready",
        first_live_artifact_ref=f"first_live_{'c' * 64}",
        admission_input=_admission(),
        closure_decisions=(closure,),
    )
    service = ModelComparisonService()

    first = service.create(request)
    repeated = service.create(request)

    assert repeated == first
    assert first.admitted is True
    assert first.ranking_candidate_ids == ("deepseek_v4_pro",)
    assert len(service.list()) == 1
