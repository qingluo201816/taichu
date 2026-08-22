from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from pydantic import BaseModel, ConfigDict

from taichu.application.contracts.llm import (
    LLMCost,
    LLMMessage,
    LLMModelProfile,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    LLMToolCall,
    LLMUsage,
)
from taichu.application.invocations.models import (
    InvocationContext,
    InvocationEnvelope,
    InvocationStatus,
)
from taichu.application.services.llm_tool_loop import (
    LLMToolCallBudgetExceeded,
    LLMToolLoop,
    LLMToolLoopLimits,
    LLMToolLoopTimeoutError,
)
from taichu.application.tools.contract import ToolManifest


class WeatherInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str


class WeatherOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: int


@dataclass
class FakeLLM:
    responses: list[LLMResponse]
    delay_seconds: float = 0

    def __post_init__(self) -> None:
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        return self.responses.pop(0)

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        if False:
            yield LLMStreamEvent(event_type="started")

    def list_models(self) -> list[LLMModelProfile]:
        return []


class FakeTools:
    def __init__(self, *, failures: int = 0, retryable: bool = True) -> None:
        self.failures = failures
        self.invocations = 0
        self.manifest = ToolManifest(
            name="get_weather",
            description="按城市查询天气。",
            input_schema=WeatherInput,
            output_schema=WeatherOutput,
            retryable=retryable,
        )

    def list_manifests(self) -> list[ToolManifest]:
        return [self.manifest]

    def get_manifest(self, name: str) -> ToolManifest:
        assert name == self.manifest.name
        return self.manifest

    async def invoke(
        self,
        name: str,
        input_data: BaseModel | dict[str, object],
        invocation: InvocationContext,
    ) -> InvocationEnvelope[BaseModel]:
        self.invocations += 1
        if self.invocations <= self.failures:
            raise RuntimeError("临时查询失败")
        parsed = WeatherInput.model_validate(input_data)
        assert parsed.city == "北京"
        return InvocationEnvelope[BaseModel](
            invocation_id=invocation.call_id,
            capability_type="tool",
            capability_name=name,
            status=InvocationStatus.COMPLETED,
            output=WeatherOutput(temperature=26),
            trace_id="trace_test",
            started_at="2026-07-22T00:00:00Z",
            finished_at="2026-07-22T00:00:01Z",
            duration_ms=1,
        )


async def _tool_loop_executes_tool_and_returns_final_response() -> None:
    llm = FakeLLM(
        responses=[
            _response(
                tool_calls=(
                    LLMToolCall(
                        call_id="call_weather_1",
                        name="get_weather",
                        arguments_json='{"city":"北京"}',
                    ),
                )
            ),
            _response(text="北京当前 26 度。"),
        ]
    )
    tools = FakeTools()

    result = await LLMToolLoop(llm=llm, tools=tools).run(
        _request(),
        invocation=_invocation(),
        allowed_tool_names=["get_weather"],
    )

    assert result.response.text == "北京当前 26 度。"
    assert result.round_count == 2
    assert result.tool_call_count == 1
    assert result.executions[0].status == "completed"
    assert llm.requests[0].tools[0].name == "get_weather"
    assert llm.requests[1].messages[-1].role == "tool"
    assert llm.requests[1].messages[-1].tool_call_id == "call_weather_1"


async def _tool_loop_retries_retryable_tool() -> None:
    llm = FakeLLM(
        responses=[
            _response(
                tool_calls=(
                    LLMToolCall(
                        call_id="call_weather_retry",
                        name="get_weather",
                        arguments_json='{"city":"北京"}',
                    ),
                )
            ),
            _response(text="查询完成。"),
        ]
    )
    tools = FakeTools(failures=1)

    result = await LLMToolLoop(llm=llm, tools=tools).run(
        _request(),
        invocation=_invocation(),
        allowed_tool_names=["get_weather"],
        limits=LLMToolLoopLimits(max_tool_retries=1),
    )

    assert tools.invocations == 2
    assert result.executions[0].retry_count == 1


async def _tool_loop_returns_tool_error_to_model() -> None:
    llm = FakeLLM(
        responses=[
            _response(
                tool_calls=(
                    LLMToolCall(
                        call_id="call_weather_bad_args",
                        name="get_weather",
                        arguments_json="不是 JSON",
                    ),
                )
            ),
            _response(text="工具参数无效，无法查询。"),
        ]
    )

    result = await LLMToolLoop(llm=llm, tools=FakeTools()).run(
        _request(),
        invocation=_invocation(),
        allowed_tool_names=["get_weather"],
    )

    assert result.executions[0].status == "failed"
    assert llm.requests[1].messages[-1].is_error is True


async def _tool_loop_stops_when_tool_call_budget_is_exceeded() -> None:
    llm = FakeLLM(
        responses=[
            _response(
                tool_calls=(
                    LLMToolCall(
                        call_id="call_1",
                        name="get_weather",
                        arguments_json='{"city":"北京"}',
                    ),
                    LLMToolCall(
                        call_id="call_2",
                        name="get_weather",
                        arguments_json='{"city":"北京"}',
                    ),
                )
            )
        ]
    )

    with pytest.raises(LLMToolCallBudgetExceeded):
        await LLMToolLoop(llm=llm, tools=FakeTools()).run(
            _request(),
            invocation=_invocation(),
            allowed_tool_names=["get_weather"],
            limits=LLMToolLoopLimits(max_tool_calls=1),
        )


async def _tool_loop_has_total_timeout() -> None:
    llm = FakeLLM(responses=[_response(text="不会返回")], delay_seconds=0.05)

    with pytest.raises(LLMToolLoopTimeoutError):
        await LLMToolLoop(llm=llm, tools=FakeTools()).run(
            _request(),
            invocation=_invocation(),
            allowed_tool_names=["get_weather"],
            limits=LLMToolLoopLimits(timeout_seconds=0.01),
        )


def test_tool_loop_executes_tool_and_returns_final_response() -> None:
    asyncio.run(_tool_loop_executes_tool_and_returns_final_response())


def test_tool_loop_retries_retryable_tool() -> None:
    asyncio.run(_tool_loop_retries_retryable_tool())


def test_tool_loop_returns_tool_error_to_model() -> None:
    asyncio.run(_tool_loop_returns_tool_error_to_model())


def test_tool_loop_stops_when_tool_call_budget_is_exceeded() -> None:
    asyncio.run(_tool_loop_stops_when_tool_call_budget_is_exceeded())


def test_tool_loop_has_total_timeout() -> None:
    asyncio.run(_tool_loop_has_total_timeout())


def _request() -> LLMRequest:
    return LLMRequest(
        model_id="test-model",
        messages=(
            LLMMessage(role="system", content="系统规则"),
            LLMMessage(role="user", content="北京天气如何？"),
        ),
        task_type="test",
        task_name="native_tool_loop",
    )


def _invocation() -> InvocationContext:
    return InvocationContext(
        task_id="task_test",
        run_id="run_test",
        caller_type="orchestrator",
        caller_name="orchestrator",
    )


def _response(
    *,
    text: str = "",
    tool_calls: tuple[LLMToolCall, ...] = (),
) -> LLMResponse:
    return LLMResponse(
        text=text,
        model_id="test-model",
        upstream_model="test-model",
        usage=LLMUsage(),
        cost=LLMCost(),
        tool_calls=tool_calls,
    )
