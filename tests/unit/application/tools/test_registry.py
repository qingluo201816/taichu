"""统一 Tool 调用协议的权限、授权、幂等和技术日志测试。"""

import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
import pytest

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.services.invocation_policy_service import (
    IdempotencyConflictError,
    InvocationAuthorizationError,
    InvocationPolicyService,
)
from taichu.application.tools.contract import (
    ToolAuthorizationPolicy,
    ToolIdempotencyPolicy,
    ToolManifest,
    ToolPlugin,
    ToolReconciliationResult,
    ToolReconciliationStatus,
    ToolSideEffect,
)
from taichu.application.tools.registry import (
    ToolInvocationPermissionError,
    ToolRegistry,
)


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


class _WriteInput(_Input):
    author_grant_id: str
    idempotency_key: str = Field(min_length=8)


class _Output(BaseModel):
    value: str
    source_refs: list[str] = []


class _TraceRepository:
    def __init__(self) -> None:
        self.records: list[object] = []

    async def append(self, record: object) -> None:
        self.records.append(record)


def _async_test(
    test: Callable[..., Coroutine[Any, Any, None]],
) -> Callable[..., None]:
    @wraps(test)
    def run(*args: Any, **kwargs: Any) -> None:
        asyncio.run(test(*args, **kwargs))

    return run


@_async_test
async def test_registry_enforces_caller_and_external_grant() -> None:
    policy = InvocationPolicyService()
    traces = _TraceRepository()
    context = CapabilityContext(capabilities={"invocation_policy_service": policy})
    registry = ToolRegistry(context, traces)

    async def run(input_data, invocation, capabilities):
        del invocation, capabilities
        return _Output(value=input_data.value)

    async def reconcile(input_data, invocation, capabilities):
        del invocation, capabilities
        return ToolReconciliationResult(
            status=ToolReconciliationStatus.SUCCEEDED,
            output={"value": input_data.value},
        )

    registry.register(
        ToolPlugin(
            manifest=ToolManifest(
                name="external_test",
                description="测试外部权限",
                input_schema=_Input,
                output_schema=_Output,
                allowed_callers=frozenset({"external_research"}),
                requires_external_access=True,
            ),
            run=run,
            reconcile=reconcile,
        )
    )
    invocation = _invocation(caller_name="external_research")
    with pytest.raises(InvocationAuthorizationError):
        await registry.invoke("external_test", {"value": "资料"}, invocation)

    grant = await policy.issue_external_access(
        task_id=invocation.task_id,
        user_intent_ref="用户明确要求联网核实",
        allowed_tools=frozenset({"external_test"}),
    )
    result = await registry.invoke(
        "external_test",
        {"value": "资料"},
        invocation.model_copy(update={"external_access_grant_id": grant.grant_id}),
    )
    assert _Output.model_validate(result.output).value == "资料"
    assert len(traces.records) == 1

    with pytest.raises(ToolInvocationPermissionError):
        await registry.invoke(
            "external_test",
            {"value": "资料"},
            _invocation(caller_name="drafting"),
        )


@_async_test
async def test_registry_binds_write_grant_and_idempotency_to_input() -> None:
    policy = InvocationPolicyService()
    context = CapabilityContext(capabilities={"invocation_policy_service": policy})
    registry = ToolRegistry(context)
    calls = 0

    async def run(input_data, invocation, capabilities):
        nonlocal calls
        del invocation, capabilities
        calls += 1
        return _Output(value=input_data.value)

    async def reconcile(input_data, invocation, capabilities):
        del invocation, capabilities
        return ToolReconciliationResult(
            status=ToolReconciliationStatus.SUCCEEDED,
            output={"value": input_data.value},
        )

    registry.register(
        ToolPlugin(
            manifest=ToolManifest(
                name="write_test",
                description="测试写入门禁",
                input_schema=_WriteInput,
                output_schema=_Output,
                side_effect=ToolSideEffect.WRITE,
                allowed_callers=frozenset({"orchestrator"}),
                authorization_policy=ToolAuthorizationPolicy.AUTHOR_GRANT,
                idempotency_policy=ToolIdempotencyPolicy.REQUIRED,
            ),
            run=run,
            reconcile=reconcile,
        )
    )
    invocation = _invocation(caller_name="orchestrator", caller_type="orchestrator")
    draft: dict[str, object] = {
        "value": "新正文",
        "idempotency_key": "idem-0001",
    }
    grant = await policy.issue_author_write(
        task_id=invocation.task_id,
        tool_name="write_test",
        input_payload=draft,
        resource_scopes=("chapter:1",),
    )
    payload = {**draft, "author_grant_id": grant.grant_id}
    first = await registry.invoke("write_test", payload, invocation)
    second = await registry.invoke("write_test", payload, invocation)

    assert (
        _Output.model_validate(first.output).value
        == _Output.model_validate(second.output).value
        == "新正文"
    )
    assert calls == 1

    with pytest.raises(IdempotencyConflictError):
        await registry.invoke(
            "write_test",
            {**payload, "value": "被篡改的正文"},
            invocation,
        )


def _invocation(
    *,
    caller_name: str,
    caller_type: Literal["application", "orchestrator", "subagent", "test"] = (
        "subagent"
    ),
) -> InvocationContext:
    return InvocationContext(
        task_id="task-tool-test",
        run_id="run-tool-test",
        caller_type=caller_type,
        caller_name=caller_name,
    )
