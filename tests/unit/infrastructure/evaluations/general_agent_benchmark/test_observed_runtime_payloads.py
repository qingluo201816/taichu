"""37 条行为 Oracle 需要的真实能力输入、输出与调用树观察。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from taichu.application.evaluations.general_agent_benchmark.strict_driver import (
    InteractionKind,
    ScriptedMatcher,
    ScriptedStep,
    StrictScriptedDriver,
)
from taichu.application.evaluations.general_agent_benchmark.synthetic_suite import (
    RuntimeInteractionRecord,
    project_observed_human_decisions,
    project_observed_invocations,
)
from taichu.application.general_agent.models import GeneralAgentHumanRequest
from taichu.application.invocations.models import (
    InvocationContext,
    InvocationEnvelope,
    InvocationStatus,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.live_runtime import (
    LiveInteractionObserver,
)
from taichu.infrastructure.evaluations.general_agent_benchmark.synthetic_runtime import (
    ObservedSubagentRegistry,
    ObservedToolRegistry,
    StrictSyntheticInteractionObserver,
)


class _ObservedOutput(BaseModel):
    answer: str
    source_refs: list[str]


class _ObservedInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    source_request: dict[str, object] = Field(default_factory=dict)


class _Delegate:
    def __init__(self, capability_type: Literal["tool", "subagent"]) -> None:
        self._capability_type = capability_type

    async def invoke(
        self,
        name: str,
        input_data: dict[str, object],
        invocation: InvocationContext,
    ) -> InvocationEnvelope[_ObservedOutput]:
        return InvocationEnvelope[_ObservedOutput](
            invocation_id=invocation.call_id,
            capability_type=self._capability_type,
            capability_name=name,
            status=InvocationStatus.COMPLETED,
            output=_ObservedOutput(
                answer="实际能力输出",
                source_refs=["source_fixture_001"],
            ),
            source_refs=["source_fixture_001"],
            artifact_refs=["artifact_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"],
            trace_id="trace_observed_runtime",
            started_at="2026-07-30T00:00:00Z",
            finished_at="2026-07-30T00:00:01Z",
            duration_ms=1_000,
        )

    def list_manifests(self) -> list[object]:
        return []

    def get_manifest(self, name: str) -> object:
        if self._capability_type != "tool":
            raise AssertionError(name)
        return SimpleNamespace(input_schema=_ObservedInput)

    async def reconcile(self, name: str, *args: object, **kwargs: object) -> object:
        raise AssertionError((name, args, kwargs))


def _driver(kind: InteractionKind, name: str) -> StrictScriptedDriver:
    return StrictScriptedDriver(
        (
            ScriptedStep(
                step_id=f"observe_{kind.value}",
                sequence=0,
                kind=kind,
                name=name,
                matchers=(
                    ScriptedMatcher(
                        path="/capability_name",
                        expected=name,
                    ),
                ),
                evidence_projection=("/capability_name",),
            ),
        )
    )


def _invocation() -> InvocationContext:
    return InvocationContext(
        task_id="task_observed_runtime",
        run_id="general_run_observed_runtime",
        call_id="call_observed_runtime",
        parent_call_id="call_parent",
        caller_type="orchestrator",
        caller_name="general_writing_orchestrator",
        phase="dag:consume_upstream",
    )


def _assert_record(record: object) -> None:
    assert getattr(record, "call_id") == "call_observed_runtime"
    assert getattr(record, "parent_call_id") == "call_parent"
    assert getattr(record, "run_id") == "general_run_observed_runtime"
    assert getattr(record, "node_id") == "consume_upstream"
    assert getattr(record, "request_payload") == {
        "question": "核对固定事实",
        "source_request": {
            "upstream_artifact_refs": ["artifact_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]
        },
    }
    assert getattr(record, "response_payload") == {
        "answer": "实际能力输出",
        "source_refs": ["source_fixture_001"],
    }
    assert getattr(record, "source_refs") == ("source_fixture_001",)
    assert getattr(record, "artifact_refs") == (
        "artifact_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    assert getattr(record, "started_at") == "2026-07-30T00:00:00Z"
    assert getattr(record, "finished_at") == "2026-07-30T00:00:01Z"


def test_tool_observer_preserves_actual_input_output_and_call_tree() -> None:
    driver = _driver(InteractionKind.TOOL, "observed_tool")
    observer = StrictSyntheticInteractionObserver(driver)
    registry = ObservedToolRegistry(
        _Delegate("tool"),  # type: ignore[arg-type]
        observer=observer,
        handler_identities={"observed_tool": "test:observed_tool"},
    )

    asyncio.run(
        registry.invoke(
            "observed_tool",
            {
                "question": "核对固定事实",
                "source_request": {
                    "upstream_artifact_refs": [
                        "artifact_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                    ]
                },
            },
            _invocation(),
        )
    )

    _assert_record(observer.capability_records[0])


def test_subagent_observer_preserves_actual_input_output_and_call_tree() -> None:
    driver = _driver(InteractionKind.SUBAGENT, "observed_subagent")
    observer = StrictSyntheticInteractionObserver(driver)
    registry = ObservedSubagentRegistry(
        _Delegate("subagent"),  # type: ignore[arg-type]
        observer=observer,
        handler_identities={"observed_subagent": "test:observed_subagent"},
    )

    asyncio.run(
        registry.invoke(
            "observed_subagent",
            {
                "question": "核对固定事实",
                "source_request": {
                    "upstream_artifact_refs": [
                        "artifact_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                    ]
                },
            },
            _invocation(),
        )
    )

    _assert_record(observer.capability_records[0])

    projected = project_observed_invocations(tuple(observer.capability_records))
    assert len(projected) == 1
    assert projected[0].capability_kind == "subagent"
    assert projected[0].node_id == "consume_upstream"
    assert projected[0].parent_call_id == "call_parent"
    assert projected[0].source_refs == ("source_fixture_001",)
    assert projected[0].artifact_refs == ("artifact_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",)
    assert projected[0].input_sha256
    assert projected[0].output_sha256


def test_successful_capability_without_payload_is_rejected_as_invalid_evidence() -> (
    None
):
    record = RuntimeInteractionRecord(
        interaction={
            "kind": "tool",
            "name": "observed_tool",
            "payload": {"capability_name": "observed_tool"},
            "outcome": "completed",
        },
        call_id="call_missing_payload",
        handler_identity="test:observed_tool",
    )

    try:
        project_observed_invocations((record,))
    except ValueError as error:
        assert "真实输入" in str(error)
    else:
        raise AssertionError("缺少真实输入输出的调用不得进入 Typed Oracle。")


def test_live_observer_keeps_the_same_typed_capability_payload_contract() -> None:
    observer = LiveInteractionObserver()
    observer.record_capability(
        kind=InteractionKind.TOOL,
        name="observed_tool",
        call_id="call_observed_runtime",
        handler_identity="test:observed_tool",
        outcome="completed",
        invocation=_invocation(),
        request_payload={
            "question": "核对固定事实",
            "source_request": {
                "upstream_artifact_refs": ["artifact_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]
            },
        },
        response_payload={
            "answer": "实际能力输出",
            "source_refs": ["source_fixture_001"],
        },
        source_refs=("source_fixture_001",),
        artifact_refs=("artifact_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",),
        started_at="2026-07-30T00:00:00Z",
        finished_at="2026-07-30T00:00:01Z",
    )

    _assert_record(observer.capability_records[0])
    projected = project_observed_invocations(tuple(observer.capability_records))
    assert projected[0].run_id == "general_run_observed_runtime"


def test_human_observer_binds_actual_request_identity_and_submitted_decision() -> None:
    driver = StrictScriptedDriver(
        (
            ScriptedStep(
                step_id="observe_human",
                sequence=0,
                kind=InteractionKind.HUMAN,
                name="write_authorization",
                matchers=(
                    ScriptedMatcher(path="/approved", expected=True),
                ),
                evidence_projection=("/approved",),
            ),
        )
    )
    observer = StrictSyntheticInteractionObserver(driver)
    request = GeneralAgentHumanRequest(
        request_id="human_observed_runtime",
        kind="write_authorization",
        prompt="是否应用这一份正文预览？",
        node_id="apply_patch",
        tool_name="apply_manuscript_patch",
        input_sha256="a" * 64,
        resource_scopes=["manuscript:chapter_001"],
        second_confirmation_required=False,
        created_at="2026-07-30T00:00:00Z",
    )

    observer.record_human_decision(
        request=request,
        source_run_id="general_run_observed_runtime",
        approved=True,
        second_confirmation=False,
    )

    (decision,) = project_observed_human_decisions(
        tuple(observer.interaction_records)
    )
    assert decision.source_run_id == "general_run_observed_runtime"
    assert decision.request_id == request.request_id
    assert decision.input_sha256 == request.input_sha256
    assert decision.resource_scopes == ("manuscript:chapter_001",)
    assert decision.approved is True
