"""真实 Runtime 后态投影不得退化为脚本自证或预设布尔值。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from taichu.application.evaluations.general_agent_benchmark.claim_catalog import (
    DEFAULT_CLAIM_NORMALIZER_REGISTRY,
    load_claim_catalog,
)
from taichu.application.evaluations.general_agent_benchmark.gates import (
    build_typed_case_gate_decision,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    CapabilityCatalogSnapshot,
    CaseConclusion,
    GateKind,
    GateStatus,
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.observations import (
    EvidenceOwner,
    ObservedTerminalState,
)
from taichu.application.evaluations.general_agent_benchmark.oracles import (
    TypedOracle,
)
from taichu.application.evaluations.general_agent_benchmark.runtime_observer import (
    FixtureIsolationFacts,
    RuntimeObservationFacts,
    RuntimeUsageFacts,
    ScriptConsumptionFacts,
    project_observed_effects,
    project_runtime_case_observation,
)
from taichu.application.evaluations.general_agent_benchmark.strict_driver import (
    InteractionKind,
    ObservedInteraction,
)
from taichu.application.evaluations.general_agent_benchmark.synthetic_suite import (
    RuntimeInteractionRecord,
    SyntheticCaseObservation,
    SyntheticSuiteRunner,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    FinalClaimsAssertionSpec,
    load_authored_suite,
)
from taichu.application.general_agent.models import (
    GeneralAgentExecutionPlan,
    GeneralAgentRun,
    GeneralAgentRunStatus,
)
from taichu.application.general_agent.recovery import EffectRecord, EffectStatus

_ROOT = Path("tests/fixtures/evaluations/general_writing_agent_benchmark")
_SUITE_PATH = _ROOT / "suite.json"
_CATALOG_PATH = _ROOT / "claim-catalog.json"
_MANIFEST_PATH = _ROOT / "fixtures" / "core_novel" / "fixture-manifest.json"
_NOW = "2026-07-30T12:00:00Z"


def test_effect_projection_deduplicates_append_only_events_by_effect_identity() -> None:
    base = {
        "effect_id": "effect_" + "a" * 32,
        "attempt_id": "attempt_" + "b" * 32,
        "run_id": "general_run_effect_observer",
        "plan_revision": 1,
        "node_id": "apply_patch",
        "tool_name": "apply_manuscript_patch",
        "input_sha256": "c" * 64,
        "idempotency_key": "benchmark-effect",
        "resource_scopes": ["manuscript:chapter_001"],
        "authorization_reference": "grant_effect_observer",
        "created_at": _NOW,
    }
    prepared = EffectRecord(
        **base,
        event_id="effect_event_" + "1" * 32,
        status=EffectStatus.PREPARED,
    )
    succeeded = EffectRecord(
        **base,
        event_id="effect_event_" + "2" * 32,
        status=EffectStatus.SUCCEEDED,
        output={"updated": True},
        evidence={"trace_id": "trace_effect_observer"},
    )

    (observed,) = project_observed_effects((prepared, succeeded))

    assert observed.effect_id == prepared.effect_id
    assert observed.status == "succeeded"
    assert observed.authorization_reference == "grant_effect_observer"
    assert observed.resource_scopes == ("manuscript:chapter_001",)


def _case_and_oracle():
    payload = json.loads(_SUITE_PATH.read_text(encoding="utf-8"))
    suite = load_authored_suite(
        _SUITE_PATH,
        expected_capability_catalog_hash=payload["capability_catalog_hash"],
        fixture_manifest_path=_MANIFEST_PATH,
    )
    case = suite.cases[0]
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    claim_refs = tuple(
        claim_id
        for assertion in case.behavior_assertions
        if isinstance(assertion, FinalClaimsAssertionSpec)
        for claim_id in (
            *assertion.required_claim_refs,
            *assertion.forbidden_claim_refs,
        )
    )
    catalog = load_claim_catalog(
        _CATALOG_PATH,
        registry=DEFAULT_CLAIM_NORMALIZER_REGISTRY,
        known_fixture_refs=(item["asset_id"] for item in manifest["scenario_assets"]),
        referenced_claim_ids=claim_refs,
    )
    return suite, case, TypedOracle(catalog=catalog)


def _final_answer(case) -> str:
    for step in reversed(case.scripted_steps):
        response = step.response or {}
        for field in ("final_answer", "direct_response"):
            value = response.get(field)
            if isinstance(value, str):
                return value
    raise AssertionError("案例缺少固定最终回答。")


def _run(case, *, final_answer: str) -> GeneralAgentRun:
    plan_step = next(
        step for step in case.scripted_steps if step.name == "orchestrator_plan"
    )
    return GeneralAgentRun(
        run_id="general_run_20260730_120000_obsv01",
        task_id="benchmark_runtime_observer",
        conversation_id="benchmark_runtime_observer",
        request_index=1,
        user_goal=case.user_request_raw,
        status=GeneralAgentRunStatus.COMPLETED,
        plan=GeneralAgentExecutionPlan.model_validate(plan_step.response),
        plan_revision=1,
        final_answer=final_answer,
        resumable=False,
        created_at=_NOW,
        updated_at=_NOW,
        started_at=_NOW,
        finished_at=_NOW,
    )


def _facts(*, deviations: tuple[str, ...] = (), isolated: bool = True):
    before = "a" * 64
    return RuntimeObservationFacts(
        invocations=(),
        terminal=ObservedTerminalState(
            run_status="completed",
            stop_reason="goal_satisfied",
            resumable=False,
            pending_human_kind=None,
        ),
        usage=RuntimeUsageFacts(
            model_calls=1,
            total_tokens=64,
            runtime_ms=10,
            context_tokens=32,
        ),
        fixture_isolation=FixtureIsolationFacts(
            before_sha256=before,
            after_sha256=before if isolated else "b" * 64,
            changed_refs=() if isolated else ("sealed_fixture/manuscript.md",),
            external_backend_identity="fixture_external_research@1",
            network_attempt_count=0,
        ),
        script_consumption=ScriptConsumptionFacts(
            declared_step_count=2,
            consumed_step_count=2,
            observed_interaction_count=2,
            deviations=deviations,
        ),
    )


def _decision(*, deviations: tuple[str, ...] = (), isolated: bool = True):
    suite, case, oracle = _case_and_oracle()
    owner = EvidenceOwner(
        suite_id=suite.suite_id,
        suite_content_hash=suite.content_hash,
        case_id=case.case_id,
        case_execution_id="benchmark_case_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        run_id="general_run_20260730_120000_obsv01",
        track=TrackKind.SYNTHETIC,
        fixture_snapshot_id=suite.fixture.snapshot_id,
    )
    observation = project_runtime_case_observation(
        case=case,
        owner=owner,
        run=_run(case, final_answer=_final_answer(case)),
        facts=_facts(deviations=deviations, isolated=isolated),
    )
    assertions = oracle.evaluate_case(case, observation)
    return observation, build_typed_case_gate_decision(
        case=case,
        observation=observation,
        assertion_results=assertions,
    )


def test_real_projection_can_form_exactly_six_passing_gates() -> None:
    observation, decision = _decision()

    assert observation.evidence_integrity.value == "valid"
    assert len(observation.evidence_records) == 6
    assert tuple(item.gate_kind for item in decision.gates) == tuple(GateKind)
    assert all(item.status is GateStatus.PASSED for item in decision.gates)
    assert decision.conclusion is CaseConclusion.PASSED
    assert all(
        "observed" not in record.payload for record in observation.evidence_records
    )


def test_complete_script_output_cannot_hide_protocol_deviation() -> None:
    _, decision = _decision(deviations=("存在未消费脚本步骤。",))
    evidence_gate = next(
        item for item in decision.gates if item.gate_kind is GateKind.EVIDENCE
    )

    assert evidence_gate.status is GateStatus.FAILED
    assert decision.conclusion is CaseConclusion.FAILED


def test_completed_runtime_cannot_hide_fixture_boundary_change() -> None:
    _, decision = _decision(isolated=False)
    security_gate = next(
        item for item in decision.gates if item.gate_kind is GateKind.SECURITY
    )

    assert security_gate.status is GateStatus.FAILED
    assert decision.conclusion is CaseConclusion.FAILED


class _FixedRuntime:
    def __init__(self, observation: SyntheticCaseObservation) -> None:
        self._observation = observation

    async def execute(self, _case) -> SyntheticCaseObservation:
        return self._observation


def _runner_result(*, final_answer: str):
    suite, case, oracle = _case_and_oracle()
    run = _run(case, final_answer=final_answer)
    interaction = RuntimeInteractionRecord(
        interaction=ObservedInteraction(
            kind=InteractionKind.MODEL,
            name="orchestrator_plan",
            payload={"phase": "plan"},
            outcome="completed",
        )
    )
    facts = _facts().model_copy(
        update={
            "script_consumption": ScriptConsumptionFacts(
                declared_step_count=1,
                consumed_step_count=1,
                observed_interaction_count=1,
            )
        }
    )
    runtime_observation = SyntheticCaseObservation(
        interactions=(interaction,),
        case_execution_id="benchmark_case_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        fixture_snapshot_id=suite.fixture.snapshot_id,
        run=run,
        runtime_facts=facts,
        normalized_result={"status": "completed"},
    )
    runner = SyntheticSuiteRunner(
        runtime=_FixedRuntime(runtime_observation),
        runtime_config_identity="1" * 64,
        capability_catalog=CapabilityCatalogSnapshot.create(
            tools=(),
            subagents=(),
            registration_dependencies=(),
            discovered_at=_NOW,
        ),
        oracle=oracle,
    )
    return asyncio.run(runner._run_case(suite, case))  # noqa: SLF001


def test_formal_synthetic_runner_uses_typed_oracle_for_its_decision() -> None:
    _, case, _ = _case_and_oracle()

    passed = _runner_result(final_answer=_final_answer(case))
    wrong_answer = _runner_result(final_answer="脚本虽然走完，但实际回答内容错误。")

    assert passed.conclusion is CaseConclusion.PASSED
    assert len(passed.gates) == 6
    assert passed.observation_sha256 is not None
    assert len(passed.evidence_ids) == 6
    assert wrong_answer.normalization_artifact is not None
    assert wrong_answer.conclusion is CaseConclusion.FAILED
    verifier_gate = next(
        item for item in wrong_answer.gates if item.gate_kind is GateKind.VERIFIER
    )
    assert verifier_gate.status is GateStatus.FAILED
