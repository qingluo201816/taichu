"""任务 7.2：Live 21 必须复用统一判定并隔离 provider 结果。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from taichu.application.evaluations.general_agent_benchmark.claim_catalog import (
    DEFAULT_CLAIM_NORMALIZER_REGISTRY,
    load_claim_catalog,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    CaseConclusion,
    GateKind,
    GateStatus,
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.observations import (
    CaseObservation,
    ObservedTerminalState,
)
from taichu.application.evaluations.general_agent_benchmark.oracles import (
    AssertionEvaluationContext,
    AssertionResult,
    TypedOracle,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    ProviderExecutionState,
)
from taichu.application.evaluations.general_agent_benchmark.runtime_observer import (
    FixtureIsolationFacts,
    RuntimeObservationFacts,
    RuntimeUsageFacts,
    ScriptConsumptionFacts,
)
from taichu.application.evaluations.general_agent_benchmark.selection import (
    SelectionError,
)
from taichu.application.evaluations.general_agent_benchmark.strict_driver import (
    InteractionKind,
    ObservedInteraction,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredCaseSpec,
    AuthoredSuiteSpec,
    FinalClaimsAssertionSpec,
    load_authored_suite,
)
from taichu.application.evaluations.general_agent_benchmark.synthetic_suite import (
    RuntimeInteractionRecord,
    SyntheticCaseObservation,
    SyntheticRuntimePort,
    SyntheticSuiteBaselineResult,
)
from taichu.application.general_agent.models import (
    GeneralAgentExecutionPlan,
    GeneralAgentRun,
    GeneralAgentRunStatus,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.live_runtime import (
    LiveSuiteRunner,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.runtime_factory import (
    production_capability_catalog_snapshot,
)
from taichu.infrastructure.llm.rightcode import LLMGatewayError

_ROOT = Path("tests/fixtures/evaluations/general_writing_agent_benchmark")
_SUITE_PATH = _ROOT / "suite.json"
_CLAIM_CATALOG_PATH = _ROOT / "claim-catalog.json"
_FIXTURE_MANIFEST_PATH = (
    _ROOT / "fixtures" / "core_novel" / "fixture-manifest.json"
)
_NOW = "2026-07-30T14:00:00Z"


def _suite() -> AuthoredSuiteSpec:
    catalog = production_capability_catalog_snapshot()
    return load_authored_suite(
        _SUITE_PATH,
        expected_capability_catalog_hash=catalog.canonical_hash,
        fixture_manifest_path=_FIXTURE_MANIFEST_PATH,
    )


def _case_oracle(case: AuthoredCaseSpec) -> TypedOracle:
    manifest = json.loads(_FIXTURE_MANIFEST_PATH.read_text(encoding="utf-8"))
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
        _CLAIM_CATALOG_PATH,
        registry=DEFAULT_CLAIM_NORMALIZER_REGISTRY,
        known_fixture_refs=(item["asset_id"] for item in manifest["scenario_assets"]),
        referenced_claim_ids=claim_refs,
    )
    return TypedOracle(catalog=catalog)


def _final_answer(case: AuthoredCaseSpec) -> str:
    for step in reversed(case.scripted_steps):
        response = step.response or {}
        for field in ("final_answer", "direct_response"):
            value = response.get(field)
            if isinstance(value, str):
                return value
    raise AssertionError("案例缺少固定最终回答。")


def _typed_runtime_observation(
    suite: AuthoredSuiteSpec,
    case: AuthoredCaseSpec,
) -> SyntheticCaseObservation:
    plan_step = next(
        step for step in case.scripted_steps if step.name == "orchestrator_plan"
    )
    run = GeneralAgentRun(
        run_id="general_run_20260730_140000_live01",
        task_id="benchmark_live_typed",
        conversation_id="benchmark_live_typed",
        request_index=1,
        user_goal=case.user_request_raw,
        status=GeneralAgentRunStatus.COMPLETED,
        plan=GeneralAgentExecutionPlan.model_validate(plan_step.response),
        plan_revision=1,
        final_answer=_final_answer(case),
        resumable=False,
        created_at=_NOW,
        updated_at=_NOW,
        started_at=_NOW,
        finished_at=_NOW,
    )
    interaction = RuntimeInteractionRecord(
        interaction=ObservedInteraction(
            kind=InteractionKind.MODEL,
            name="orchestrator_plan",
            payload={"phase": "plan"},
            outcome="completed",
        )
    )
    return SyntheticCaseObservation(
        interactions=(interaction,),
        case_execution_id="benchmark_case_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        fixture_snapshot_id=suite.fixture.snapshot_id,
        run=run,
        runtime_facts=RuntimeObservationFacts(
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
                before_sha256="a" * 64,
                after_sha256="a" * 64,
                changed_refs=(),
                external_backend_identity="fixture_external_research@1",
                network_attempt_count=0,
            ),
            script_consumption=ScriptConsumptionFacts(
                declared_step_count=1,
                consumed_step_count=1,
                observed_interaction_count=1,
            ),
        ),
        normalized_result={"status": "completed"},
    )


class _Runtime:
    def __init__(
        self,
        observation: SyntheticCaseObservation | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.observation = observation or SyntheticCaseObservation(
            interactions=(),
            normalized_result={},
        )
        self.error = error
        self.case_ids: list[str] = []

    async def execute(self, case: AuthoredCaseSpec) -> SyntheticCaseObservation:
        self.case_ids.append(case.case_id)
        if self.error is not None:
            raise self.error
        return self.observation


class _RecordingOracle:
    def __init__(self, delegate: TypedOracle) -> None:
        self.delegate = delegate
        self.observations: list[CaseObservation] = []

    def evaluate_case(
        self,
        case: AuthoredCaseSpec,
        observation: CaseObservation,
        *,
        context: AssertionEvaluationContext | None = None,
    ) -> tuple[AssertionResult, ...]:
        self.observations.append(observation)
        return self.delegate.evaluate_case(case, observation, context=context)


def _runner(runtime: _Runtime, oracle: object) -> LiveSuiteRunner:
    return LiveSuiteRunner(
        runtime=cast(SyntheticRuntimePort, runtime),
        runtime_config_identity="1" * 64,
        capability_catalog=production_capability_catalog_snapshot(),
        oracle=cast(TypedOracle, oracle),
    )


@pytest.mark.anyio
async def test_live_full_run_uses_shared_selector_and_executes_exact_first_21() -> None:
    suite = _suite()
    runtime = _Runtime()
    runner = _runner(runtime, _case_oracle(suite.cases[0]))

    result = await runner.run(suite)

    assert not isinstance(result, SelectionError)
    assert runtime.case_ids == list(suite.case_order[:21])
    assert result.selected_case_ids == suite.case_order[:21]
    assert result.applicable_case_ids == suite.case_order[:21]
    assert result.case_count == 21
    assert result.executed_case_count == 21
    assert result.provider_state is ProviderExecutionState.COMPLETED


@pytest.mark.anyio
async def test_live_rejects_cases_22_through_37_before_runtime_or_provider_call() -> None:
    suite = _suite()
    runtime = _Runtime()
    runner = _runner(runtime, _case_oracle(suite.cases[0]))
    not_applicable = suite.case_order[21:]

    result = await runner.run(
        suite,
        requested_case_ids=not_applicable,
    )

    assert isinstance(result, SelectionError)
    assert result.code == "case_track_not_applicable"
    assert result.case_ids == not_applicable
    assert runtime.case_ids == []


@pytest.mark.anyio
async def test_live_revalidates_suite_to_prevent_selector_bypass() -> None:
    suite = _suite()
    runtime = _Runtime()
    runner = _runner(runtime, _case_oracle(suite.cases[0]))
    bypassed = suite.model_copy(
        update={
            "case_order": suite.case_order[:1],
            "cases": suite.cases[:1],
        }
    )

    result = await runner.run(bypassed)

    assert isinstance(result, SelectionError)
    assert runtime.case_ids == []


@pytest.mark.anyio
async def test_live_uses_shared_runtime_observation_typed_oracle_and_six_gates() -> None:
    suite = _suite()
    case = suite.cases[0]
    runtime = _Runtime(_typed_runtime_observation(suite, case))
    oracle = _RecordingOracle(_case_oracle(case))
    runner = _runner(runtime, oracle)

    result = await runner.run(
        suite,
        requested_case_ids=(case.case_id,),
    )

    assert not isinstance(result, SelectionError)
    assert len(oracle.observations) == 1
    assert oracle.observations[0].owner.track is TrackKind.LIVE_PROVIDER
    assert len(result.cases) == 1
    assert result.cases[0].conclusion is CaseConclusion.PASSED
    assert tuple(gate.gate_kind for gate in result.cases[0].gates) == tuple(GateKind)
    assert all(gate.status is GateStatus.PASSED for gate in result.cases[0].gates)
    assert result.cases[0].assertions
    assert result.cases[0].observation_sha256 is not None
    assert len(result.cases[0].evidence_ids) == 6
    assert result.complete is False


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("code", "status_code", "expected_state"),
    [
        ("LLM_MODEL_FORBIDDEN", 403, ProviderExecutionState.BLOCKED),
        ("LLM_UPSTREAM_ERROR", 503, ProviderExecutionState.ERROR),
    ],
)
async def test_provider_blocked_or_error_is_live_only_and_preserves_synthetic(
    code: str,
    status_code: int,
    expected_state: ProviderExecutionState,
) -> None:
    suite = _suite()
    synthetic = SyntheticSuiteBaselineResult(
        suite_id=suite.suite_id,
        suite_content_hash=suite.content_hash,
        runtime_config_identity="2" * 64,
        cases=(),
        case_count=37,
        passed_case_count=37,
        failed_case_count=0,
        complete=True,
        result_hash="3" * 64,
        stable_result_hash="4" * 64,
    )
    synthetic_before = synthetic.model_dump(mode="json")
    runtime = _Runtime(
        error=LLMGatewayError(
            code,
            "provider unavailable",
            status_code=status_code,
        )
    )
    runner = _runner(runtime, _case_oracle(suite.cases[0]))

    result = await runner.run(
        suite,
        requested_case_ids=(suite.case_order[0],),
    )

    assert not isinstance(result, SelectionError)
    assert result.provider_state is expected_state
    assert result.cases == ()
    assert result.executed_case_count == 0
    assert result.pending_case_ids == (suite.case_order[0],)
    assert result.complete is False
    assert synthetic.model_dump(mode="json") == synthetic_before
