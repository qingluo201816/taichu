from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import inspect
from types import SimpleNamespace
from typing import cast

import pytest

from taichu.application.contracts.llm import (
    LLMCost,
    LLMMessage,
    LLMModelProfile,
    LLMRequest,
    LLMResponse,
    LLMUsage,
)
from taichu.application.evaluations.general_agent_benchmark.strict_driver import (
    InteractionKind,
    ScriptedStep,
    StrictScriptedDriver,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.live_runtime import (
    LiveFixtureRuntime,
    LiveInteractionObserver,
    LiveObservedLLMGateway,
    RecordingReplayRepository,
    RecordingUsageRepository,
    _live_human_problems,
    _live_invocation_problems,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    CapabilityKind,
)
from taichu.application.evaluations.general_agent_benchmark.observations import (
    ObservedTerminalState,
)
from taichu.application.evaluations.general_agent_benchmark.runtime_observer import (
    FixtureIsolationFacts,
    RuntimeObservationFacts,
    RuntimeUsageFacts,
    ScriptConsumptionFacts,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredCaseSpec,
    RequiredInvocationSpec,
)
from taichu.application.evaluations.general_agent_benchmark.synthetic_suite import (
    RuntimeInteractionRecord,
    SyntheticCapabilityInvocation,
    SyntheticCaseObservation,
)
from taichu.application.evaluations.general_agent_benchmark.strict_driver import (
    ObservedInteraction,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.synthetic_runtime import (
    StrictSyntheticInteractionObserver,
)
from taichu.infrastructure.evaluations.general_agent_benchmark import (
    synthetic_environment,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.synthetic_environment import (
    SyntheticFixtureRuntime,
)
from taichu.application.models.llm_replay import LLMCallReplayRecord
from taichu.application.models.llm_usage import LLMCallRecord
from taichu.config import Settings
from taichu.infrastructure.llm.rightcode import RightCodeGatewayError


def test_legacy_gate_proxy_path_is_removed() -> None:
    source = inspect.getsource(synthetic_environment)

    assert "def _gate_conditions" not in source
    assert "security_ok=True" not in source
    assert "artifact_ok=bool(" not in source
    assert "evidence_ok=bool(" not in source


class _Gateway:
    def __init__(self, response: LLMResponse | Exception) -> None:
        self.response = response

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    async def stream(self, request: LLMRequest):  # type: ignore[no-untyped-def]
        raise AssertionError("本测试不使用流式调用。")
        yield

    def list_models(self) -> list[LLMModelProfile]:
        return [
            LLMModelProfile(
                id="deepseek-v4-pro",
                display_name="DeepSeek V4 Pro",
                provider="rightcode",
                upstream_model="deepseek-v4-pro",
                wire_protocol="anthropic_messages",
                base_url_key="RIGHTCODE_DEEPSEEK_ANTHROPIC_BASE_URL",
                enabled=True,
                is_default=True,
                supports_streaming=True,
            )
        ]


class _UsageRepository:
    def __init__(self) -> None:
        self.records: list[LLMCallRecord] = []

    async def append(self, record: LLMCallRecord) -> None:
        self.records.append(record)


class _ReplayRepository:
    def __init__(self) -> None:
        self.records: list[LLMCallReplayRecord] = []

    async def save(self, record: LLMCallReplayRecord) -> None:
        self.records.append(record)


def _request() -> LLMRequest:
    return LLMRequest(
        model_id="deepseek-v4-pro",
        messages=(LLMMessage(role="user", content="测试"),),
        task_type="general_writing_agent",
        task_name="general_writing_orchestrator.plan",
        run_id="run-live",
    )


@pytest.mark.anyio
async def test_live_gateway_records_real_model_interaction_without_fallback() -> None:
    driver = StrictScriptedDriver(
        (
            ScriptedStep(
                step_id="plan",
                sequence=0,
                kind=InteractionKind.MODEL,
                name="orchestrator_plan",
                matchers=(),
                evidence_projection=(),
                response={"status": "completed"},
            ),
        )
    )
    observer = StrictSyntheticInteractionObserver(driver)
    response = LLMResponse(
        text='{"status":"completed"}',
        model_id="deepseek-v4-pro",
        upstream_model="deepseek-v4-pro",
        usage=LLMUsage(input_tokens=10, output_tokens=4, total_tokens=14),
        cost=LLMCost(amount=Decimal("0.01"), kind="actual"),
        finish_reason="end_turn",
        provider_request_id="request-live-1",
        call_id="llm-call-11111111111111111111111111111111",
    )
    gateway = LiveObservedLLMGateway(
        _Gateway(response),
        driver=driver,
        observer=observer,
    )

    actual = await gateway.complete(_request())

    assert actual is response
    assert gateway.failures == ()
    assert gateway.responses == (response,)
    assert [item.interaction.name for item in observer.interaction_records] == [
        "orchestrator_plan"
    ]
    assert observer.interaction_records[0].interaction.payload == {"phase": "plan"}


@pytest.mark.anyio
async def test_live_gateway_does_not_consume_synthetic_script() -> None:
    observer = LiveInteractionObserver()
    response = LLMResponse(
        text='{"status":"completed"}',
        model_id="deepseek-v4-pro",
        upstream_model="deepseek-v4-pro",
        usage=LLMUsage(input_tokens=10, output_tokens=4, total_tokens=14),
        cost=LLMCost(amount=Decimal("0.01"), kind="actual"),
        finish_reason="end_turn",
        provider_request_id="request-live-2",
        call_id="llm-call-22222222222222222222222222222222",
    )
    gateway = LiveObservedLLMGateway(
        _Gateway(response),
        driver=None,
        observer=observer,
    )

    await gateway.complete(_request())
    await gateway.complete(
        replace(
            _request(),
            task_name="general_writing_orchestrator.replan",
        )
    )

    assert [item.interaction.name for item in observer.interaction_records] == [
        "orchestrator_plan",
        "orchestrator_replan",
    ]


@pytest.mark.anyio
async def test_live_gateway_preserves_provider_error_without_consuming_script() -> None:
    driver = StrictScriptedDriver(
        (
            ScriptedStep(
                step_id="plan",
                sequence=0,
                kind=InteractionKind.MODEL,
                name="orchestrator_plan",
                matchers=(),
                evidence_projection=(),
                response={"status": "completed"},
            ),
        )
    )
    observer = StrictSyntheticInteractionObserver(driver)
    error = RightCodeGatewayError(
        "LLM_REQUEST_REJECTED",
        "provider failed",
        status_code=404,
    )
    gateway = LiveObservedLLMGateway(
        _Gateway(error),
        driver=driver,
        observer=observer,
    )

    with pytest.raises(RightCodeGatewayError, match="provider failed") as captured:
        await gateway.complete(_request())

    assert captured.value is error
    assert driver.current_step is not None
    assert observer.interaction_records == []
    assert gateway.failures[0].error_type == "RightCodeGatewayError"
    assert gateway.failures[0].status_code == 404


@pytest.mark.anyio
async def test_recording_repositories_keep_exact_usage_and_replay_records() -> None:
    usage_delegate = _UsageRepository()
    replay_delegate = _ReplayRepository()
    usage = RecordingUsageRepository(usage_delegate)
    replay = RecordingReplayRepository(replay_delegate)
    usage_record = LLMCallRecord(
        call_id="llm-call-11111111111111111111111111111111",
        run_id="run-live",
        task_type="general_writing_agent",
        task_name="plan",
        model_id="deepseek-v4-pro",
        model_display_name="DeepSeek V4 Pro",
        provider="rightcode",
        upstream_model="deepseek-v4-pro",
        wire_protocol="anthropic_messages",
        status="completed",
        started_at="2026-07-28T00:00:00Z",
        finished_at="2026-07-28T00:00:01Z",
        input_tokens=10,
        output_tokens=4,
        total_tokens=14,
        cost_amount=Decimal("0.01"),
        cost_kind="actual",
        provider_request_id="request-live-1",
    )
    replay_record = LLMCallReplayRecord(
        call_id=usage_record.call_id,
        run_id="run-live",
        task_type="general_writing_agent",
        task_name="plan",
        model_id="deepseek-v4-pro",
        provider="rightcode",
        upstream_model="deepseek-v4-pro",
        wire_protocol="anthropic_messages",
        status="completed",
        response_mode="json",
        messages=[{"role": "user", "content": "测试"}],
        response_text='{"status":"completed"}',
        request_sha256="1" * 64,
        response_sha256="2" * 64,
        input_tokens=10,
        output_tokens=4,
        total_tokens=14,
        provider_request_id="request-live-1",
        started_at="2026-07-28T00:00:00Z",
        finished_at="2026-07-28T00:00:01Z",
        duration_ms=1000,
    )

    await usage.append(usage_record)
    await replay.save(replay_record)

    assert usage.records == (usage_record,)
    assert replay.records == (replay_record,)
    assert usage_delegate.records == [usage_record]
    assert replay_delegate.records == [replay_record]


def test_live_fixture_runtime_requires_fallback_to_be_disabled(tmp_path) -> None:
    sealed = tmp_path / "fixtures" / "core_novel"
    sealed.mkdir(parents=True)
    (sealed / "fixture-manifest.json").write_text(
        '{"fixture_id":"core_novel","files":[]}',
        encoding="utf-8",
    )
    settings = Settings(
        project_assets_dir=tmp_path,
        deepseek_fallback_enabled=True,
    )

    with pytest.raises(ValueError, match="fallback"):
        LiveFixtureRuntime(
            sealed_fixture_root=sealed,
            workspaces_root=tmp_path / "workspaces",
            settings=settings,
        )


def test_live_fixture_runtime_reuses_shared_runtime_observation_path() -> None:
    source = inspect.getsource(LiveFixtureRuntime.execute)

    assert "super().execute(case)" in source
    assert "_gate_conditions(" not in source
    assert "_cleanup_successful_case(" not in source


@pytest.mark.anyio
async def test_live_fixture_runtime_replaces_only_gateway_usage_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = cast(AuthoredCaseSpec, SimpleNamespace(case_id="live-usage"))
    observation = SyntheticCaseObservation(
        interactions=(),
        runtime_facts=RuntimeObservationFacts(
            invocations=(),
            terminal=ObservedTerminalState(
                run_status="completed",
                stop_reason="goal_satisfied",
                resumable=False,
                pending_human_kind=None,
            ),
            usage=RuntimeUsageFacts(
                model_calls=0,
                total_tokens=0,
                runtime_ms=123,
                context_tokens=45,
            ),
            fixture_isolation=FixtureIsolationFacts(
                before_sha256="a" * 64,
                after_sha256="a" * 64,
            ),
            script_consumption=ScriptConsumptionFacts(
                declared_step_count=0,
                consumed_step_count=0,
                observed_interaction_count=0,
            ),
        ),
        normalized_result={},
    )

    async def shared_execute(
        _runtime: SyntheticFixtureRuntime,
        _case: AuthoredCaseSpec,
    ) -> SyntheticCaseObservation:
        return observation

    monkeypatch.setattr(SyntheticFixtureRuntime, "execute", shared_execute)
    collector = SimpleNamespace(
        usage=SimpleNamespace(
            records=(SimpleNamespace(total_tokens=37),),
        ),
        replay=SimpleNamespace(records=()),
        gateway=SimpleNamespace(
            requests=[object(), object()],
            failures=(),
            responses=(),
        ),
    )
    runtime = object.__new__(LiveFixtureRuntime)
    runtime._collectors = {case.case_id: collector}
    runtime._audits = {}

    actual = await runtime.execute(case)

    assert actual.runtime_facts is not None
    assert actual.runtime_facts.usage == RuntimeUsageFacts(
        model_calls=2,
        total_tokens=37,
        runtime_ms=123,
        context_tokens=45,
    )


@pytest.mark.anyio
async def test_live_fixture_runtime_preserves_empty_audit_when_setup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = object.__new__(LiveFixtureRuntime)
    runtime._collectors = {}
    runtime._audits = {}
    case = cast(
        AuthoredCaseSpec,
        SimpleNamespace(case_id="case-without-collector"),
    )

    async def fail_before_collector(
        _runtime: SyntheticFixtureRuntime,
        _case: AuthoredCaseSpec,
    ) -> None:
        raise RuntimeError("setup failed")

    monkeypatch.setattr(SyntheticFixtureRuntime, "execute", fail_before_collector)

    with pytest.raises(RuntimeError, match="setup failed"):
        await runtime.execute(case)

    audit = runtime.case_audit(case.case_id)
    assert audit.case_id == case.case_id
    assert audit.usage_records == ()
    assert audit.replay_records == ()
    assert audit.gateway_failures == ()
    assert audit.response_call_ids == ()


def test_live_invocation_gate_accepts_a_recovered_failed_attempt() -> None:
    expected = (
        RequiredInvocationSpec(
            type=CapabilityKind.SUBAGENT,
            name="story_architecture",
            min_calls=1,
            max_calls=1,
            expected_outcome="completed",
            parent="orchestrator",
            partial_order=None,
        ),
    )
    observed = (
        SyntheticCapabilityInvocation(
            kind=CapabilityKind.SUBAGENT,
            capability_name="story_architecture",
            call_id="failed-attempt",
            handler_identity="story_architecture",
            outcome="failed",
        ),
        SyntheticCapabilityInvocation(
            kind=CapabilityKind.SUBAGENT,
            capability_name="story_architecture",
            call_id="completed-retry",
            handler_identity="story_architecture",
            outcome="completed",
        ),
    )

    assert (
        _live_invocation_problems(
            expected,
            observed,
            scripted_capabilities=frozenset(),
        )
        == ()
    )


def test_live_human_gate_rejects_an_undeclared_clarification() -> None:
    case = cast(AuthoredCaseSpec, SimpleNamespace(scripted_steps=()))
    interactions = (
        RuntimeInteractionRecord(
            interaction=ObservedInteraction(
                kind=InteractionKind.HUMAN,
                name="clarification",
                payload={"approved": False},
                outcome="completed",
            )
        ),
    )

    assert _live_human_problems(case, interactions) == (
        "human:clarification 决定次数 1 不等于合同声明 0",
    )
