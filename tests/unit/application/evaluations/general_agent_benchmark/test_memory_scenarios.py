"""需求 14.1、14.4、14.12—14.20：工作记忆载体抗污染硬门禁。"""

from __future__ import annotations

from taichu.application.agent_memory.models import (
    AgentMemoryDependencyRelation,
    AgentMemoryValidity,
)
from taichu.application.evaluations.general_agent_benchmark.memory_scenarios import (
    MemoryCarrierKind,
    MemoryCarrierObservation,
    audit_memory_carriers,
)


def _observation(
    carrier: MemoryCarrierKind,
    *,
    memory_id: str,
    validity: AgentMemoryValidity = AgentMemoryValidity.ACTIVE,
    role: AgentMemoryDependencyRelation = AgentMemoryDependencyRelation.BASIS,
    repair_only: bool = False,
    proof_valid: bool = True,
) -> MemoryCarrierObservation:
    return MemoryCarrierObservation(
        carrier=carrier,
        memory_id=memory_id,
        producer_ref=f"node:run_fixture:1:{memory_id}",
        validity=validity,
        role=role,
        repair_only=repair_only,
        source_fingerprint="a" * 64,
        dependency_fingerprint="b" * 64,
        state_hash="c" * 64,
        proof_valid=proof_valid,
        branch_id="branch_main",
        evidence_ref=f"evidence_{memory_id}",
    )


def test_all_current_carriers_accept_active_and_repair_is_explicitly_isolated() -> None:
    current_carriers = (
        MemoryCarrierKind.NODE_SUMMARY,
        MemoryCarrierKind.NORMAL_DIGEST,
        MemoryCarrierKind.FALLBACK_DIGEST,
        MemoryCarrierKind.SNAPSHOT_CURRENT,
        MemoryCarrierKind.REUSE,
        MemoryCarrierKind.PARALLEL_BRANCH,
    )
    observations = tuple(
        _observation(
            carrier,
            memory_id=f"memory_active_{index}",
        )
        for index, carrier in enumerate(current_carriers)
    ) + (
        _observation(
            MemoryCarrierKind.REPAIR_PROJECTION,
            memory_id="memory_stale_repair",
            validity=AgentMemoryValidity.STALE,
            role=AgentMemoryDependencyRelation.REPAIR_SOURCE,
            repair_only=True,
        ),
    )

    report = audit_memory_carriers(observations)

    assert report.complete is True
    assert report.violations == ()
    assert all(item.passed for item in report.carrier_results)


def test_each_invalid_state_fails_every_current_carrier_and_reuse_proof_is_required() -> None:
    current_carriers = (
        MemoryCarrierKind.NODE_SUMMARY,
        MemoryCarrierKind.NORMAL_DIGEST,
        MemoryCarrierKind.FALLBACK_DIGEST,
        MemoryCarrierKind.SNAPSHOT_CURRENT,
        MemoryCarrierKind.REUSE,
        MemoryCarrierKind.PARALLEL_BRANCH,
    )
    invalid_states = (
        AgentMemoryValidity.STALE,
        AgentMemoryValidity.REJECTED,
        AgentMemoryValidity.SUPERSEDED,
    )
    observations = tuple(
        _observation(
            carrier,
            memory_id=f"memory_{state.value}_{carrier.value}",
            validity=state,
        )
        for carrier in current_carriers
        for state in invalid_states
    ) + (
        _observation(
            MemoryCarrierKind.REUSE,
            memory_id="memory_active_bad_proof",
            proof_valid=False,
        ),
    )

    report = audit_memory_carriers(observations)

    assert report.complete is False
    assert len(report.violations) == len(current_carriers) * len(invalid_states) + 1
    failed_carriers = {
        item.carrier for item in report.carrier_results if not item.passed
    }
    assert failed_carriers == set(current_carriers)
    assert any("producer 有效性证明" in violation for violation in report.violations)


def test_invalid_memory_outside_repair_source_role_is_rejected() -> None:
    report = audit_memory_carriers(
        (
            _observation(
                MemoryCarrierKind.REPAIR_PROJECTION,
                memory_id="memory_rejected_wrong_role",
                validity=AgentMemoryValidity.REJECTED,
                role=AgentMemoryDependencyRelation.REVIEW_TARGET,
                repair_only=True,
            ),
        )
    )

    assert report.complete is False
    assert report.carrier_results[0].passed is False
