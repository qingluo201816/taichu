"""需求 2.3—2.6、10.1—10.10：由真实观察构建六类硬门禁。"""

from __future__ import annotations

import json
from pathlib import Path

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.claim_catalog import (
    DEFAULT_CLAIM_NORMALIZER_REGISTRY,
    load_claim_catalog,
)
from taichu.application.evaluations.general_agent_benchmark.gates import (
    build_typed_case_gate_decision,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    GateKind,
    GateStatus,
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.observations import (
    EvidenceOwner,
    EvidenceRecord,
    EvidenceRef,
    ObservedBudgetUsage,
    ObservedFinalAnswer,
    ObservedResourceSnapshot,
    ObservedTerminalState,
    build_case_observation,
)
from taichu.application.evaluations.general_agent_benchmark.oracles import (
    AssertionEvaluationContext,
    ResourceDiffObservation,
    TypedOracle,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredCaseSpec,
    ExpectedTerminalSpec,
    FinalClaimsAssertionSpec,
    ResourceDiffAssertionSpec,
    load_authored_suite,
)

_ROOT = Path("tests/fixtures/evaluations/general_writing_agent_benchmark")
_SUITE_PATH = _ROOT / "suite.json"
_CATALOG_PATH = _ROOT / "claim-catalog.json"
_MANIFEST_PATH = _ROOT / "fixtures" / "core_novel" / "fixture-manifest.json"


def _case_owner_oracle() -> tuple[AuthoredCaseSpec, EvidenceOwner, TypedOracle]:
    suite_payload = json.loads(_SUITE_PATH.read_text(encoding="utf-8"))
    suite = load_authored_suite(
        _SUITE_PATH,
        expected_capability_catalog_hash=suite_payload["capability_catalog_hash"],
        fixture_manifest_path=_MANIFEST_PATH,
    )
    case = suite.cases[0]
    owner = EvidenceOwner(
        suite_id=suite.suite_id,
        suite_content_hash=suite.content_hash,
        case_id=case.case_id,
        case_execution_id=f"benchmark_case_{'b' * 32}",
        run_id="general_run_20260730_180000_gates1",
        track=TrackKind.SYNTHETIC,
        fixture_snapshot_id=suite.fixture.snapshot_id,
    )
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    catalog = load_claim_catalog(
        _CATALOG_PATH,
        registry=DEFAULT_CLAIM_NORMALIZER_REGISTRY,
        known_fixture_refs=tuple(
            item["asset_id"] for item in manifest["scenario_assets"]
        ),
    )
    return case, owner, TypedOracle(catalog=catalog)


def _records(
    case: AuthoredCaseSpec,
    owner: EvidenceOwner,
    *,
    isolate: bool = True,
) -> tuple[EvidenceRecord, ...]:
    before = canonical_sha256({"workspace": "sealed"})
    after = before if isolate else canonical_sha256({"workspace": "changed"})
    records: list[EvidenceRecord] = []
    for requirement in case.required_evidence:
        if requirement.gate is GateKind.SECURITY:
            payload = {
                "before_sha256": before,
                "after_sha256": after,
                "changed_refs": [] if isolate else ["other_workspace"],
            }
        else:
            payload = {
                "recorded_from_runtime": True,
                "selector": requirement.probe.selector,
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
    *,
    final_text: str = (
        "先明确冲突双方无法同时实现的目标；"
        "因为目标互斥才能形成持续阻力。"
    ),
    records: tuple[EvidenceRecord, ...] | None = None,
    terminal: ObservedTerminalState | None = None,
    budget: ObservedBudgetUsage | None = None,
    resource_snapshots: tuple[ObservedResourceSnapshot, ...] = (),
    script_protocol_deviations: tuple[str, ...] = (),
):
    return build_case_observation(
        case=case,
        owner=owner,
        user_request_raw=case.user_request_raw,
        plan={"route": "direct", "nodes": []},
        nodes=(),
        invocations=(),
        final_answer=ObservedFinalAnswer.create(
            text=final_text,
            source_refs=(),
        ),
        artifacts=(),
        resource_snapshots=resource_snapshots,
        recovery_decisions=(),
        terminal=terminal
        or ObservedTerminalState(
            run_status=case.expected_terminal.run_status,
            stop_reason=case.expected_terminal.reason_code,
            resumable=case.expected_terminal.resumable,
            pending_human_kind=case.expected_terminal.pending_human_kind,
        ),
        budget=budget
        or ObservedBudgetUsage(
            node_executions=0,
            replans=0,
            capability_calls=0,
            model_calls=1,
            total_tokens=128,
            runtime_ms=20,
            context_tokens=64,
        ),
        script_protocol_deviations=script_protocol_deviations,
        evidence_records=records if records is not None else _records(case, owner),
    )


def _gate(decision, kind: GateKind):
    return next(item for item in decision.gates if item.gate_kind is kind)


def test_real_observation_and_oracle_build_exactly_six_nonempty_gates() -> None:
    case, owner, oracle = _case_owner_oracle()
    observation = _observation(case, owner)
    assertion_results = oracle.evaluate_case(case, observation)

    decision = build_typed_case_gate_decision(
        case=case,
        observation=observation,
        assertion_results=assertion_results,
    )

    assert tuple(item.gate_kind for item in decision.gates) == tuple(GateKind)
    assert len(decision.gates) == 6
    assert decision.conclusion == "passed"
    assert all(item.status is GateStatus.PASSED for item in decision.gates)
    assert all(item.evidence_refs for item in decision.gates)


def test_call_success_cannot_cover_wrong_final_claim() -> None:
    case, owner, oracle = _case_owner_oracle()
    semantic_case = case.model_copy(
        update={
            "behavior_assertions": (
                *case.behavior_assertions,
                FinalClaimsAssertionSpec(
                    kind="final_claims",
                    assertion_id="answer_contract",
                    description="最终回答必须保持直接路由语义。",
                    required_claim_refs=("route_direct", "capability_none"),
                    forbidden_claim_refs=("tide_lamp_memory_temporarily_stored",),
                    normalizer_ref="claim_text",
                ),
            )
        }
    )
    observation = _observation(
        semantic_case,
        owner,
        final_text="归潮灯会把共同记忆暂存在潮汐回廊。",
    )

    decision = build_typed_case_gate_decision(
        case=semantic_case,
        observation=observation,
        assertion_results=oracle.evaluate_case(
            semantic_case,
            observation,
        ),
    )

    assert _gate(decision, GateKind.VERIFIER).status is GateStatus.FAILED
    assert decision.conclusion == "failed"


def test_artifact_presence_cannot_cover_wrong_resource_after_state() -> None:
    case, owner, oracle = _case_owner_oracle()
    resource_case = case.model_copy(
        update={
            "behavior_assertions": (
                *case.behavior_assertions,
                ResourceDiffAssertionSpec(
                    kind="resource_diff",
                    assertion_id="resource_must_stay_unchanged",
                    description="只读任务不得改变正文。",
                    resource_snapshot_ref="resource_snapshot_core_novel",
                    expected_change="unchanged",
                ),
            )
        }
    )
    before = {"chapter": "原文"}
    after = {"chapter": "被改写"}
    observation = _observation(
        resource_case,
        owner,
        resource_snapshots=(
            ObservedResourceSnapshot(
                snapshot_ref="resource_snapshot_core_novel",
                phase="before",
                content_sha256=canonical_sha256(before),
                payload=before,
            ),
            ObservedResourceSnapshot(
                snapshot_ref="resource_snapshot_core_novel",
                phase="after",
                content_sha256=canonical_sha256(after),
                payload=after,
            ),
        ),
    )
    context = AssertionEvaluationContext(
        resource_diffs=(
            ResourceDiffObservation(
                resource_snapshot_ref="resource_snapshot_core_novel",
                actual_change="updated",
                before_sha256=canonical_sha256(before),
                after_sha256=canonical_sha256(after),
                changed_refs=("chapter_001",),
            ),
        )
    )

    decision = build_typed_case_gate_decision(
        case=resource_case,
        observation=observation,
        assertion_results=oracle.evaluate_case(
            resource_case,
            observation,
            context=context,
        ),
    )

    assert _gate(decision, GateKind.ARTIFACT).status is GateStatus.FAILED
    assert decision.conclusion == "failed"


def test_security_is_derived_from_workspace_hashes_not_supplied_true() -> None:
    case, owner, oracle = _case_owner_oracle()
    observation = _observation(
        case,
        owner,
        records=_records(case, owner, isolate=False),
    )

    decision = build_typed_case_gate_decision(
        case=case,
        observation=observation,
        assertion_results=oracle.evaluate_case(case, observation),
    )

    assert _gate(decision, GateKind.SECURITY).status is GateStatus.FAILED
    assert decision.conclusion == "failed"


def test_missing_or_corrupt_evidence_is_invalid_and_never_empty_fallback() -> None:
    case, owner, oracle = _case_owner_oracle()
    observation = _observation(
        case,
        owner,
        records=_records(case, owner)[:-1],
    )

    decision = build_typed_case_gate_decision(
        case=case,
        observation=observation,
        assertion_results=oracle.evaluate_case(case, observation),
    )

    evidence_gate = _gate(decision, GateKind.EVIDENCE)
    assert evidence_gate.status is GateStatus.INVALID
    assert evidence_gate.evidence_refs
    assert decision.conclusion == "invalid"


def test_budget_uses_actual_replans_context_tokens_and_runtime() -> None:
    case, owner, oracle = _case_owner_oracle()
    over_budget = ObservedBudgetUsage(
        node_executions=0,
        replans=case.budgets.max_replans + 1,
        capability_calls=0,
        model_calls=1,
        total_tokens=128,
        runtime_ms=20,
        context_tokens=case.budgets.max_total_tokens + 1,
    )
    observation = _observation(case, owner, budget=over_budget)

    decision = build_typed_case_gate_decision(
        case=case,
        observation=observation,
        assertion_results=oracle.evaluate_case(case, observation),
    )

    budget_gate = _gate(decision, GateKind.BUDGET)
    assert budget_gate.status is GateStatus.FAILED
    assert "重规划" in budget_gate.observed
    assert "上下文" in budget_gate.observed


def test_stop_reason_accepts_declared_non_completed_terminal_only() -> None:
    case, owner, oracle = _case_owner_oracle()
    rejected_case = case.model_copy(
        update={
            "expected_terminal": ExpectedTerminalSpec(
                run_status="write_rejected",
                resumable=False,
                pending_human_kind=None,
                recovery_action="none",
                reason_code="authorization_denied",
            )
        }
    )
    correct = _observation(
        rejected_case,
        owner,
        terminal=ObservedTerminalState(
            run_status="write_rejected",
            stop_reason="authorization_denied",
            resumable=False,
            pending_human_kind=None,
        ),
    )
    wrong = _observation(
        rejected_case,
        owner,
        terminal=ObservedTerminalState(
            run_status="completed",
            stop_reason="goal_satisfied",
            resumable=False,
            pending_human_kind=None,
        ),
    )

    correct_decision = build_typed_case_gate_decision(
        case=rejected_case,
        observation=correct,
        assertion_results=oracle.evaluate_case(rejected_case, correct),
    )
    wrong_decision = build_typed_case_gate_decision(
        case=rejected_case,
        observation=wrong,
        assertion_results=oracle.evaluate_case(rejected_case, wrong),
    )

    assert _gate(correct_decision, GateKind.STOP_REASON).status is GateStatus.PASSED
    assert _gate(wrong_decision, GateKind.STOP_REASON).status is GateStatus.FAILED


def test_strict_driver_deviation_fails_evidence_even_when_records_exist() -> None:
    case, owner, oracle = _case_owner_oracle()
    observation = _observation(
        case,
        owner,
        script_protocol_deviations=("出现未声明的额外交互",),
    )

    decision = build_typed_case_gate_decision(
        case=case,
        observation=observation,
        assertion_results=oracle.evaluate_case(case, observation),
    )

    assert _gate(decision, GateKind.EVIDENCE).status is GateStatus.FAILED
    assert decision.conclusion == "failed"
