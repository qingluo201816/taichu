"""StrictScriptedDriver 与真实 Runtime 能力注册表之间的观察适配。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
import json
from typing import Any

from pydantic import BaseModel

from taichu.application.contracts.llm import LLMModelProfile
from taichu.infrastructure.llm.contracts import (
    LLMCost,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    LLMToolCall,
    LLMUsage,
)
from taichu.application.evaluations.general_agent_benchmark.strict_driver import (
    InteractionKind,
    ObservedInteraction,
    StrictScriptedDriver,
    SyntheticProtocolError,
)
from taichu.application.evaluations.general_agent_benchmark.synthetic_suite import (
    RuntimeInteractionRecord,
)
from taichu.application.general_agent.executor import InjectedProcessTermination
from taichu.application.general_agent.models import GeneralAgentHumanRequest
from taichu.application.subagents.registry import SubagentRegistry
from taichu.application.tools.registry import ToolRegistry


class SyntheticInjectedProcessTermination(InjectedProcessTermination):
    """评测控制面用于验证生产 Runtime 检查点恢复的一次性进程终止。"""


class StrictSyntheticLLMGateway:
    """唯一替换模型返回；不执行或伪造 Tool/Subagent。"""

    def __init__(
        self,
        driver: StrictScriptedDriver,
        *,
        observer: StrictSyntheticInteractionObserver | None = None,
        crash_once_task_name: str | None = None,
    ) -> None:
        self._driver = driver
        self._observer = observer
        self._response_bindings: dict[str, Any] = {}
        self._crash_once_task_name = crash_once_task_name
        self._crashed = False
        self.requests: list[LLMRequest] = []

    def set_response_bindings(self, values: dict[str, Any]) -> None:
        self._response_bindings.update(values)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if request.task_name == self._crash_once_task_name and not self._crashed:
            self.requests.append(request)
            self._crashed = True
            raise SyntheticInjectedProcessTermination(
                f"在 {request.task_name} 注入一次进程终止。"
            )
        payload = {"phase": _model_phase(request.task_name)}
        step = self._driver.select_step(
            kind=InteractionKind.MODEL,
            payload=payload,
        )
        if step is None or step.kind is not InteractionKind.MODEL:
            current = self._driver.current_step
            name = current.name if current is not None else "unexpected_model"
            self._driver.observe(
                ObservedInteraction(
                    kind=InteractionKind.MODEL,
                    name=name,
                    payload=payload,
                    outcome="failed",
                )
            )
            raise AssertionError("unreachable")
        if not isinstance(step.response, dict):
            raise SyntheticProtocolError(
                self._driver_error_evidence(
                    "SYNTHETIC_CONTENT_MISMATCH",
                    observed={"response": step.response},
                )
            )
        interaction = ObservedInteraction(
            kind=InteractionKind.MODEL,
            name=step.name,
            payload=payload,
            outcome="completed",
        )
        self._driver.observe(interaction)
        if self._observer is not None:
            self._observer.record_observed(interaction)
        self.requests.append(request)
        response = _resolve_response_bindings(
            step.response,
            self._response_bindings,
        )
        tool_calls = _native_tool_calls(request, response, len(self.requests))
        return LLMResponse(
            text="" if tool_calls else json.dumps(response, ensure_ascii=False),
            model_id=request.model_id,
            upstream_model="strict-synthetic",
            usage=LLMUsage(
                input_tokens=0,
                cached_input_tokens=0,
                output_tokens=0,
                reasoning_tokens=0,
                total_tokens=0,
            ),
            cost=LLMCost(amount=None, kind="unavailable"),
            finish_reason="stop",
            call_id=f"synthetic_model_{len(self.requests):04d}",
            tool_calls=tool_calls,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        response = await self.complete(request)
        yield LLMStreamEvent(
            event_type="completed",
            response=response,
            usage=response.usage,
            call_id=response.call_id,
        )

    def list_models(self) -> list[LLMModelProfile]:
        return [
            LLMModelProfile(
                id="synthetic-model",
                display_name="确定性合成模型",
                provider="rightcode",
                upstream_model="strict-synthetic",
                wire_protocol="openai_responses",
                enabled=True,
                is_default=True,
                supports_streaming=True,
                input_price_per_million=Decimal("0"),
                output_price_per_million=Decimal("0"),
                currency="CNY",
                upstream_verified=False,
            )
        ]

    def _driver_error_evidence(
        self,
        code: str,
        *,
        observed: object,
    ):
        step = self._driver.current_step
        from taichu.application.evaluations.general_agent_benchmark.strict_driver import (
            SyntheticProtocolEvidence,
        )

        return SyntheticProtocolEvidence(
            error_code=code,
            step_id=step.step_id if step is not None else None,
            step_index=None,
            expected=step.response if step is not None else None,
            observed=observed,
            matcher_path="/response",
            remaining_step_ids=(
                tuple(item.step_id for item in self._driver.steps)
                if step is not None
                else ()
            ),
        )


def _native_tool_calls(
    request: LLMRequest,
    payload: dict[str, Any],
    sequence: int,
) -> tuple[LLMToolCall, ...]:
    if not request.tools:
        return ()
    selected = (
        request.tool_choice
        if request.tool_choice not in {"auto", "none", "required"}
        else request.tools[-1].name
    )
    return (
        LLMToolCall(
            call_id=f"synthetic_tool_{sequence:04d}",
            name=selected,
            arguments_json=json.dumps(payload, ensure_ascii=False),
        ),
    )


class StrictSyntheticInteractionObserver:
    """只在真实 delegate 已返回或抛错后记录能力 outcome。"""

    def __init__(self, driver: StrictScriptedDriver) -> None:
        self._driver = driver
        self.interaction_records: list[RuntimeInteractionRecord] = []
        self.capability_records: list[RuntimeInteractionRecord] = []

    def record_observed(self, interaction: ObservedInteraction) -> None:
        """记录已被 strict driver 消费的非能力交互，供套件 runner 独立重放。"""
        self.interaction_records.append(
            RuntimeInteractionRecord(interaction=interaction)
        )

    def record_capability(
        self,
        *,
        kind: InteractionKind,
        name: str,
        call_id: str,
        handler_identity: str,
        outcome: str,
        invocation: object | None = None,
        request_payload: dict[str, object] | None = None,
        response_payload: dict[str, object] | None = None,
        source_refs: tuple[str, ...] = (),
        artifact_refs: tuple[str, ...] = (),
        started_at: str | None = None,
        finished_at: str | None = None,
    ) -> None:
        interaction = ObservedInteraction(
            kind=kind,
            name=name,
            payload={"capability_name": name},
            outcome=outcome,
        )
        self._driver.observe(interaction)
        record = RuntimeInteractionRecord(
            interaction=interaction,
            call_id=call_id,
            handler_identity=handler_identity,
            parent_call_id=_optional_string(
                getattr(invocation, "parent_call_id", None)
            ),
            run_id=_optional_string(getattr(invocation, "run_id", None)),
            node_id=_node_id(invocation),
            request_payload=request_payload,
            response_payload=response_payload,
            source_refs=source_refs,
            artifact_refs=artifact_refs,
            started_at=started_at,
            finished_at=finished_at,
        )
        self.interaction_records.append(record)
        self.capability_records.append(record)

    def record_human_decision(
        self,
        *,
        request: GeneralAgentHumanRequest,
        source_run_id: str,
        approved: bool,
        second_confirmation: bool,
    ) -> None:
        """只观察 Runtime 已创建的人工请求以及控制器实际提交的决定。"""
        interaction = ObservedInteraction(
            kind=InteractionKind.HUMAN,
            name=request.kind,
            payload={"approved": approved},
            outcome="completed",
        )
        self._driver.observe(interaction)
        self.interaction_records.append(
            RuntimeInteractionRecord(
                interaction=interaction,
                run_id=source_run_id,
                node_id=request.node_id,
                human_request_id=request.request_id,
                human_request_kind=request.kind,
                human_tool_name=request.tool_name,
                human_input_sha256=request.input_sha256,
                human_resource_scopes=tuple(request.resource_scopes),
                human_second_confirmation_required=(
                    request.second_confirmation_required
                ),
                human_approved=approved,
                human_second_confirmation=second_confirmation,
                human_request_created_at=request.created_at,
            )
        )


class ObservedToolRegistry(ToolRegistry):
    """保持 ToolRegistry 全部门禁，仅在真实调用完成后增加评测观察。"""

    def __init__(
        self,
        delegate: ToolRegistry,
        *,
        observer: StrictSyntheticInteractionObserver,
        handler_identities: dict[str, str],
    ) -> None:
        self._delegate = delegate
        self._observer = observer
        self._handler_identities = dict(handler_identities)

    def list_manifests(self):  # type: ignore[no-untyped-def]
        return self._delegate.list_manifests()

    def get_manifest(self, name: str):  # type: ignore[no-untyped-def]
        return self._delegate.get_manifest(name)

    async def invoke(self, name: str, *args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        handler_identity = self._handler_identities[name]
        invocation = _invocation_context(args, kwargs)
        request_payload = self.get_manifest(name).input_schema.model_validate(
            _request_input(args, kwargs)
        ).model_dump(mode="json")
        try:
            result = await self._delegate.invoke(name, *args, **kwargs)
        except Exception:
            call_id = _invocation_call_id(args, kwargs)
            self._observer.record_capability(
                kind=InteractionKind.TOOL,
                name=name,
                call_id=call_id,
                handler_identity=handler_identity,
                outcome="failed",
                invocation=invocation,
                request_payload=request_payload,
            )
            raise
        self._observer.record_capability(
            kind=InteractionKind.TOOL,
            name=name,
            call_id=str(result.invocation_id),
            handler_identity=handler_identity,
            outcome=str(result.status.value),
            invocation=invocation,
            request_payload=request_payload,
            response_payload=_json_object(result.output),
            source_refs=tuple(str(item) for item in result.source_refs),
            artifact_refs=tuple(str(item) for item in result.artifact_refs),
            started_at=str(result.started_at),
            finished_at=str(result.finished_at),
        )
        return result

    async def reconcile(self, name: str, *args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        return await self._delegate.reconcile(name, *args, **kwargs)


class ObservedSubagentRegistry:
    """保持 SubagentRegistry 真实执行，只观察最终 envelope 或真实异常。"""

    def __init__(
        self,
        delegate: SubagentRegistry,
        *,
        observer: StrictSyntheticInteractionObserver,
        handler_identities: dict[str, str],
    ) -> None:
        self._delegate = delegate
        self._observer = observer
        self._handler_identities = dict(handler_identities)

    def list_manifests(self):  # type: ignore[no-untyped-def]
        return self._delegate.list_manifests()

    def get_manifest(self, name: str):  # type: ignore[no-untyped-def]
        return self._delegate.get_manifest(name)

    async def invoke(self, name: str, *args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        handler_identity = self._handler_identities[name]
        invocation = _invocation_context(args, kwargs)
        request_payload = _request_payload(args, kwargs)
        try:
            result = await self._delegate.invoke(name, *args, **kwargs)
        except Exception:
            self._observer.record_capability(
                kind=InteractionKind.SUBAGENT,
                name=name,
                call_id=_invocation_call_id(args, kwargs),
                handler_identity=handler_identity,
                outcome="failed",
                invocation=invocation,
                request_payload=request_payload,
            )
            raise
        self._observer.record_capability(
            kind=InteractionKind.SUBAGENT,
            name=name,
            call_id=str(result.invocation_id),
            handler_identity=handler_identity,
            outcome=str(result.status.value),
            invocation=invocation,
            request_payload=request_payload,
            response_payload=_json_object(result.output),
            source_refs=tuple(str(item) for item in result.source_refs),
            artifact_refs=tuple(str(item) for item in result.artifact_refs),
            started_at=str(result.started_at),
            finished_at=str(result.finished_at),
        )
        return result


def _model_phase(task_name: str) -> str:
    if task_name.endswith(".plan"):
        return "plan"
    if task_name.endswith(".replan"):
        return "replan"
    if task_name.endswith(".verify"):
        return "verify"
    return task_name


def _invocation_call_id(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    invocation = _invocation_context(args, kwargs)
    return str(getattr(invocation, "call_id", "unknown_call"))


def _invocation_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> object | None:
    invocation = kwargs.get("invocation")
    if invocation is None and len(args) >= 2:
        invocation = args[1]
    return invocation


def _request_payload(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, object] | None:
    return _json_object(_request_input(args, kwargs))


def _request_input(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> object | None:
    value = kwargs.get("input_data")
    if value is None and args:
        value = args[0]
    return value


def _json_object(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        payload: object = value.model_dump(mode="json")
    else:
        payload = value
    serialized = json.loads(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    )
    if not isinstance(serialized, dict):
        raise TypeError("能力调用观察只接受对象形式的输入输出。")
    return serialized


def _node_id(invocation: object | None) -> str | None:
    phase = getattr(invocation, "phase", None)
    if not isinstance(phase, str) or not phase.startswith("dag:"):
        return None
    node_id = phase.removeprefix("dag:")
    return node_id or None


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None


def _resolve_response_bindings(value: Any, bindings: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return bindings.get(value, value)
    if isinstance(value, list):
        return [_resolve_response_bindings(item, bindings) for item in value]
    if isinstance(value, dict):
        return {
            key: _resolve_response_bindings(item, bindings)
            for key, item in value.items()
        }
    return value
