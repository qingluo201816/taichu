"""统一 Tool 调用协议的权限、授权、幂等和技术日志测试。"""

import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, Literal

from langchain.agents import create_agent
from langchain.agents.middleware import ToolRetryMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field
import pytest

from taichu.application.capabilities import CapabilityContext
from taichu.application.contracts.general_agent_tool_budget import (
    GeneralAgentToolBudgetClaimConflictError,
    GeneralAgentToolBudgetExceededError,
    GeneralAgentToolBudgetOwner,
)
from taichu.application.invocations.models import InvocationBudget, InvocationContext
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
    ToolInvocationError,
    ToolInvocationPermissionError,
    ToolRegistry,
)
from tests.fakes import (
    InMemoryGeneralAgentToolBudgetRepository,
    NativeToolCallSequenceChatModel,
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

    tool = registry.bind_langchain_tool("write_test", invocation)
    tool_call_schema = tool.tool_call_schema
    assert isinstance(tool_call_schema, type)
    model_visible_schema = tool_call_schema.model_json_schema()
    assert set(model_visible_schema["properties"]) == {"value"}

    tool_message = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "write_test",
            "args": payload,
            "id": "model-write-call-1",
        }
    )
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.tool_call_id == "model-write-call-1"
    assert tool_message.artifact.invocation_id == "model-write-call-1"


@_async_test
async def test_registry_exposes_native_langchain_tool_call_contract() -> None:
    traces = _TraceRepository()
    registry = ToolRegistry(
        CapabilityContext(
            capabilities={"invocation_policy_service": InvocationPolicyService()}
        ),
        traces,
    )

    async def run(input_data, invocation, capabilities):
        del invocation, capabilities
        return _Output(value=input_data.value, source_refs=["source:test"])

    registry.register(
        ToolPlugin(
            manifest=ToolManifest(
                name="read_test",
                description="读取测试数据",
                input_schema=_Input,
                output_schema=_Output,
                allowed_callers=frozenset({"orchestrator"}),
            ),
            run=run,
        )
    )
    invocation = _invocation(
        caller_name="orchestrator",
        caller_type="orchestrator",
    )
    tool = registry.bind_langchain_tool("read_test", invocation)

    assert isinstance(tool, BaseTool)
    assert isinstance(tool.args_schema, type)
    assert issubclass(tool.args_schema, _Input)
    assert set(tool.tool_call_schema.model_json_schema()["properties"]) == {"value"}
    first_tool_call_id = "model-tool-call-1"
    second_tool_call_id = "model-tool-call-2"
    assert invocation.call_id not in {first_tool_call_id, second_tool_call_id}
    first = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "read_test",
            "args": {"value": "第一次调用"},
            "id": first_tool_call_id,
        }
    )
    second = await tool.ainvoke(
        {
            "type": "tool_call",
            "name": "read_test",
            "args": {"value": "第二次调用"},
            "id": second_tool_call_id,
        }
    )

    assert isinstance(first, ToolMessage)
    assert isinstance(second, ToolMessage)
    assert first.tool_call_id == first_tool_call_id
    assert second.tool_call_id == second_tool_call_id
    assert first.name == second.name == "read_test"
    assert _Output.model_validate_json(str(first.content)).value == "第一次调用"
    assert _Output.model_validate_json(str(second.content)).value == "第二次调用"
    assert first.artifact.output.source_refs == ["source:test"]
    assert second.artifact.output.source_refs == ["source:test"]
    assert first.artifact.invocation_id == first_tool_call_id
    assert second.artifact.invocation_id == second_tool_call_id
    assert [record.call_id for record in traces.records] == [
        first_tool_call_id,
        second_tool_call_id,
    ]


@_async_test
async def test_agent_tool_runtime_maps_parallel_model_calls_independently() -> None:
    traces = _TraceRepository()
    registry = ToolRegistry(
        CapabilityContext(
            capabilities={"invocation_policy_service": InvocationPolicyService()}
        ),
        traces,
    )

    async def run(input_data, invocation, capabilities):
        del invocation, capabilities
        return _Output(value=input_data.value)

    registry.register(
        ToolPlugin(
            manifest=ToolManifest(
                name="read_test",
                description="读取测试数据",
                input_schema=_Input,
                output_schema=_Output,
                allowed_callers=frozenset({"orchestrator"}),
            ),
            run=run,
        )
    )
    invocation = _invocation(
        caller_name="orchestrator",
        caller_type="orchestrator",
    )
    envelopes = []
    tool = registry.bind_langchain_agent_tool(
        "read_test",
        invocation,
        result_sink=envelopes.append,
    )
    model = NativeToolCallSequenceChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "model-parallel-call-1",
                        "name": "read_test",
                        "args": {"value": "甲"},
                        "type": "tool_call",
                    },
                    {
                        "id": "model-parallel-call-2",
                        "name": "read_test",
                        "args": {"value": "乙"},
                        "type": "tool_call",
                    },
                ],
            ),
            AIMessage(content="完成"),
        ]
    )
    agent = create_agent(model=model, tools=[tool])

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content="读取两次测试数据")]}
    )

    tool_messages = [
        message for message in result["messages"] if isinstance(message, ToolMessage)
    ]
    assert {message.tool_call_id for message in tool_messages} == {
        "model-parallel-call-1",
        "model-parallel-call-2",
    }
    assert {envelope.invocation_id for envelope in envelopes} == {
        "model-parallel-call-1",
        "model-parallel-call-2",
    }
    assert {record.call_id for record in traces.records} == {
        "model-parallel-call-1",
        "model-parallel-call-2",
    }


@_async_test
async def test_general_agent_tool_budget_is_shared_idempotent_and_fail_closed() -> None:
    repository = InMemoryGeneralAgentToolBudgetRepository()
    policy = InvocationPolicyService()
    registry = ToolRegistry(
        CapabilityContext(capabilities={"invocation_policy_service": policy}),
        tool_budget_repository=repository,
        require_tool_budget=True,
    )
    calls: list[str] = []

    async def run(input_data, invocation, capabilities):
        del invocation, capabilities
        calls.append(input_data.value)
        return _Output(value=input_data.value)

    registry.register(
        ToolPlugin(
            manifest=ToolManifest(
                name="budgeted_read",
                description="验证任务级 Tool 预算",
                input_schema=_Input,
                output_schema=_Output,
                allowed_callers=frozenset({"orchestrator", "drafting"}),
            ),
            run=run,
        )
    )
    direct = _general_agent_invocation(
        call_id="attempt_direct",
        caller_name="orchestrator",
        caller_type="orchestrator",
        max_tool_calls=1,
    )

    await registry.invoke("budgeted_read", {"value": "相同输入"}, direct)
    await registry.invoke("budgeted_read", {"value": "相同输入"}, direct)
    owner = GeneralAgentToolBudgetOwner(
        conversation_id=direct.conversation_id or "",
        run_id=direct.run_id,
    )
    snapshot = await repository.read(owner)
    assert snapshot is not None
    assert snapshot.used == 1
    assert snapshot.remaining == 0

    with pytest.raises(GeneralAgentToolBudgetClaimConflictError):
        await registry.invoke("budgeted_read", {"value": "身份冲突"}, direct)

    nested = direct.model_copy(
        update={
            "call_id": "model-tool-call-new",
            "parent_call_id": direct.call_id,
            "caller_type": "subagent",
            "caller_name": "drafting",
        }
    )
    with pytest.raises(GeneralAgentToolBudgetExceededError):
        await registry.invoke("budgeted_read", {"value": "超限"}, nested)
    assert calls == ["相同输入", "相同输入"]


@_async_test
async def test_required_general_agent_budget_rejects_missing_repository() -> None:
    registry = ToolRegistry(
        CapabilityContext(
            capabilities={"invocation_policy_service": InvocationPolicyService()}
        ),
        require_tool_budget=True,
    )

    async def run(input_data, invocation, capabilities):
        del invocation, capabilities
        return _Output(value=input_data.value)

    registry.register(
        ToolPlugin(
            manifest=ToolManifest(
                name="strict_budget_read",
                description="验证预算仓储强制注入",
                input_schema=_Input,
                output_schema=_Output,
                allowed_callers=frozenset({"orchestrator"}),
            ),
            run=run,
        )
    )

    with pytest.raises(ToolInvocationError, match="预算仓储"):
        await registry.invoke(
            "strict_budget_read",
            {"value": "不会执行"},
            _general_agent_invocation(
                call_id="attempt_missing_repository",
                caller_name="orchestrator",
                caller_type="orchestrator",
                max_tool_calls=1,
            ),
        )


@_async_test
async def test_trace_repository_failure_is_logged_without_masking_tool_result(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingTraceRepository:
        async def append(self, record: object) -> None:
            del record
            raise OSError("trace backend unavailable")

    registry = ToolRegistry(
        CapabilityContext(
            capabilities={"invocation_policy_service": InvocationPolicyService()}
        ),
        FailingTraceRepository(),
    )

    async def run(input_data, invocation, capabilities):
        del invocation, capabilities
        return _Output(value=input_data.value)

    registry.register(
        ToolPlugin(
            manifest=ToolManifest(
                name="trace_failure_read",
                description="验证轨迹失败降级",
                input_schema=_Input,
                output_schema=_Output,
                allowed_callers=frozenset({"orchestrator"}),
            ),
            run=run,
        )
    )

    result = await registry.invoke(
        "trace_failure_read",
        {"value": "正常结果"},
        _invocation(caller_name="orchestrator", caller_type="orchestrator"),
    )

    assert result.output.value == "正常结果"
    assert "Tool 调用轨迹写入失败" in caplog.text


@_async_test
async def test_tool_retry_reuses_the_same_task_budget_claim() -> None:
    repository = InMemoryGeneralAgentToolBudgetRepository()
    registry = ToolRegistry(
        CapabilityContext(
            capabilities={"invocation_policy_service": InvocationPolicyService()}
        ),
        tool_budget_repository=repository,
        require_tool_budget=True,
    )
    attempts = 0

    async def flaky_run(input_data, invocation, capabilities):
        nonlocal attempts
        del invocation, capabilities
        attempts += 1
        if attempts == 1:
            raise ConnectionError("temporary upstream failure")
        return _Output(value=input_data.value)

    registry.register(
        ToolPlugin(
            manifest=ToolManifest(
                name="retry_read",
                description="验证同一 ToolCall 的重试预算",
                input_schema=_Input,
                output_schema=_Output,
                allowed_callers=frozenset({"drafting"}),
                retryable=True,
            ),
            run=flaky_run,
        )
    )
    parent = _general_agent_invocation(
        call_id="attempt_retry_parent",
        caller_name="orchestrator",
        caller_type="orchestrator",
        max_tool_calls=1,
    )
    invocation = parent.child(
        caller_type="subagent",
        caller_name="drafting",
        phase="drafting:model_tool",
    )
    tool = registry.bind_langchain_agent_tool("retry_read", invocation)
    model = NativeToolCallSequenceChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "model-retry-call-1",
                        "name": "retry_read",
                        "args": {"value": "重试成功"},
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="完成"),
        ]
    )
    agent = create_agent(
        model=model,
        tools=[tool],
        middleware=[
            ToolRetryMiddleware(
                max_retries=1,
                tools=["retry_read"],
                retry_on=(ConnectionError,),
                on_failure="error",
                initial_delay=0,
                jitter=False,
            )
        ],
    )

    await agent.ainvoke({"messages": [HumanMessage(content="读取测试数据")]})

    snapshot = await repository.read(
        GeneralAgentToolBudgetOwner(
            conversation_id=parent.conversation_id or "",
            run_id=parent.run_id,
        )
    )
    assert attempts == 2
    assert snapshot is not None
    assert snapshot.used == 1
    assert snapshot.claims[0].call_id == "model-retry-call-1"
    assert snapshot.claims[0].parent_call_id == parent.call_id


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


def _general_agent_invocation(
    *,
    call_id: str,
    caller_name: str,
    caller_type: Literal["orchestrator", "subagent"],
    max_tool_calls: int,
) -> InvocationContext:
    return InvocationContext(
        task_id="general-conversation-budget",
        conversation_id="general-conversation-budget",
        run_id="general_run_20260830_000000_budget",
        call_id=call_id,
        caller_type=caller_type,
        caller_name=caller_name,
        budget=InvocationBudget(max_tool_calls=max_tool_calls),
    )
