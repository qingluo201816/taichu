"""需求 5.1—5.27：六类硬门禁、机制结论与静态 verifier 注册。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from taichu.application.evaluations.general_agent_benchmark.gates import (
    GateConditionInput,
    MechanismGateEvaluator,
    StaticVerifierRegistry,
    VerifierObservation,
    VerificationInput,
    evaluate_case_gates,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    FailureCategory,
    GateKind,
    GateStatus,
    VerifierId,
    VerifierSpec,
    VerifierStatus,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    MechanismConclusion,
    MechanismDecisionSource,
)


_FAILURE_BY_GATE = {
    GateKind.BUDGET: FailureCategory.BUDGET_EXCEEDED,
    GateKind.VERIFIER: FailureCategory.VERIFIER_FAILED,
    GateKind.ARTIFACT: FailureCategory.MISSING_ARTIFACT,
    GateKind.STOP_REASON: FailureCategory.FAILURE_STOP_REASON,
    GateKind.SECURITY: FailureCategory.SECURITY_VIOLATION,
    GateKind.EVIDENCE: FailureCategory.EVIDENCE_INCOMPLETE,
}


def _condition(kind: GateKind, *, satisfied: bool | None = True) -> GateConditionInput:
    return GateConditionInput(
        gate_kind=kind,
        condition_id=f"{kind.value}_condition",
        satisfied=satisfied,
        expected="满足硬门禁",
        observed="满足" if satisfied else "不满足",
        evidence_refs=(f"evidence_{kind.value}",),
        failure_category=_FAILURE_BY_GATE[kind],
    )


@pytest.mark.parametrize("failed_kind", tuple(GateKind))
def test_each_hard_gate_failure_blocks_case_pass(failed_kind: GateKind) -> None:
    result = evaluate_case_gates(
        tuple(
            _condition(kind, satisfied=kind is not failed_kind)
            for kind in GateKind
        )
    )

    assert [gate.gate_kind for gate in result.gates] == list(GateKind)
    assert result.conclusion == "failed"
    assert result.hard_gate_failed is True
    failed = next(gate for gate in result.gates if gate.gate_kind is failed_kind)
    assert failed.status is GateStatus.FAILED
    assert failed.failure_categories == (_FAILURE_BY_GATE[failed_kind],)


def test_indeterminate_gate_makes_case_invalid_and_unknown_gate_is_rejected() -> None:
    result = evaluate_case_gates(
        tuple(
            _condition(
                kind,
                satisfied=None if kind is GateKind.EVIDENCE else True,
            )
            for kind in GateKind
        )
    )
    assert result.conclusion == "invalid"

    with pytest.raises(ValidationError):
        GateConditionInput(
            gate_kind="score",  # type: ignore[arg-type]
            condition_id="unknown",
            satisfied=True,
            expected="未知",
            observed="未知",
            evidence_refs=("evidence_unknown",),
            failure_category="undetermined",
        )


def test_mechanism_gate_is_hard_gate_decision_bound_to_evidence() -> None:
    result = MechanismGateEvaluator().evaluate(
        mechanism_id="memory_projection",
        conditions=(
            _condition(GateKind.EVIDENCE),
            _condition(GateKind.SECURITY),
        ),
    )

    assert result.status is GateStatus.PASSED
    assert result.conclusion is MechanismConclusion.MET
    assert result.decision_source is MechanismDecisionSource.HARD_GATE
    assert result.evidence_refs == ("evidence_evidence", "evidence_security")


def test_static_verifier_registry_executes_closed_id_and_records_rule_identity() -> None:
    registry = StaticVerifierRegistry()
    registry.register(
        VerifierId.EVIDENCE_COMPLETENESS,
        rule_identity="evidence_completeness@sha256:abc",
        verify=lambda value: VerifierObservation(
            status=(
                VerifierStatus.PASSED
                if value.values["complete"] is True
                else VerifierStatus.INVALID
            ),
            observed_summary="八类证据完整",
            evidence_refs=("evidence_bundle",),
        ),
    )
    spec = VerifierSpec(
        instance_id="verify_evidence",
        verifier_id=VerifierId.EVIDENCE_COMPLETENESS,
        expected_artifact_ids=("evidence_bundle",),
        required=True,
        config={"kind": "evidence_completeness"},
    )

    result = registry.execute(
        spec,
        VerificationInput(values={"complete": True}),
        observed_at="2026-07-27T00:00:00Z",
    )

    assert result.status is VerifierStatus.PASSED
    assert result.rule_identity == "evidence_completeness@sha256:abc"
    assert result.evidence_refs == ("evidence_bundle",)
    with pytest.raises(ValueError, match="未注册"):
        StaticVerifierRegistry().execute(
            spec,
            VerificationInput(values={"complete": True}),
            observed_at="2026-07-27T00:00:00Z",
        )
