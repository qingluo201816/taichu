"""模型原生函数工具调用的受限多轮执行器。"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, replace
import json
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from taichu.application.contracts.llm import (
    LLMGatewayContract,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
)
from taichu.application.invocations.models import InvocationContext, InvocationEnvelope
from taichu.application.tools.contract import ToolManifest, ToolSideEffect


class NativeToolRuntime(Protocol):
    """执行器依赖的最小工具注册表边界。"""

    def list_manifests(self) -> list[ToolManifest]: ...

    def get_manifest(self, name: str) -> ToolManifest: ...

    async def invoke(
        self,
        name: str,
        input_data: BaseModel | dict[str, object],
        invocation: InvocationContext,
    ) -> InvocationEnvelope[BaseModel]: ...


class LLMToolLoopLimits(BaseModel):
    """一次模型原生工具循环的硬预算。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_rounds: int = Field(default=8, ge=1, le=30)
    max_tool_calls: int = Field(default=12, ge=1, le=100)
    max_tool_retries: int = Field(default=1, ge=0, le=5)
    timeout_seconds: float = Field(default=300, gt=0, le=1_800)


class LLMToolExecutionState(BaseModel):
    """一项模型工具请求的规范化执行状态。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    call_id: str
    tool_name: str
    status: Literal["completed", "failed"]
    retry_count: int = Field(default=0, ge=0)
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class LLMToolLoopResult:
    """最终模型响应以及可用于检查点和回放的完整循环状态。"""

    response: LLMResponse
    messages: tuple[LLMMessage, ...]
    executions: tuple[LLMToolExecutionState, ...]
    round_count: int
    tool_call_count: int


class LLMToolLoop:
    """供编排 Agent 和可升级子 Agent 共用的原生工具循环。"""

    def __init__(
        self,
        *,
        llm: LLMGatewayContract,
        tools: NativeToolRuntime,
    ) -> None:
        self._llm = llm
        self._tools = tools

    async def run(
        self,
        request: LLMRequest,
        *,
        invocation: InvocationContext,
        allowed_tool_names: Iterable[str],
        limits: LLMToolLoopLimits | None = None,
        allow_side_effects: bool = False,
    ) -> LLMToolLoopResult:
        """持续执行模型工具请求，直到模型返回不含工具请求的最终结果。"""
        effective_limits = limits or LLMToolLoopLimits(
            max_tool_calls=max(1, invocation.budget.max_tool_calls),
            max_tool_retries=invocation.budget.max_retries,
        )
        definitions = self._definitions(
            allowed_tool_names,
            invocation=invocation,
            allow_side_effects=allow_side_effects,
        )
        if not definitions:
            raise LLMToolLoopConfigurationError("本次调用没有可暴露给模型的工具。")

        messages = list(request.messages)
        executions: list[LLMToolExecutionState] = []
        seen_call_ids: set[str] = set()
        tool_call_count = 0

        try:
            async with asyncio.timeout(effective_limits.timeout_seconds):
                for round_index in range(1, effective_limits.max_rounds + 1):
                    round_request = replace(
                        request,
                        messages=tuple(messages),
                        tools=definitions,
                        tool_choice="auto",
                    )
                    response = await self._llm.complete(round_request)
                    if not response.tool_calls:
                        return LLMToolLoopResult(
                            response=response,
                            messages=tuple(messages),
                            executions=tuple(executions),
                            round_count=round_index,
                            tool_call_count=tool_call_count,
                        )

                    messages.append(
                        LLMMessage(
                            role="assistant",
                            content=response.text,
                            tool_calls=response.tool_calls,
                        )
                    )
                    for tool_call in response.tool_calls:
                        tool_call_count += 1
                        if tool_call_count > effective_limits.max_tool_calls:
                            raise LLMToolCallBudgetExceeded(
                                "模型工具调用次数超过本次运行预算。"
                            )
                        if tool_call.call_id in seen_call_ids:
                            result_message, state = _failed_tool_result(
                                tool_call,
                                LLMToolProtocolError("模型重复使用了工具调用标识。"),
                            )
                        else:
                            seen_call_ids.add(tool_call.call_id)
                            result_message, state = await self._execute(
                                tool_call,
                                invocation=invocation,
                                allowed_names={item.name for item in definitions},
                                max_retries=effective_limits.max_tool_retries,
                            )
                        messages.append(result_message)
                        executions.append(state)
        except TimeoutError as error:
            raise LLMToolLoopTimeoutError("模型工具循环执行超时。") from error

        raise LLMToolRoundBudgetExceeded("模型工具循环超过最大轮次，未形成最终回答。")

    def _definitions(
        self,
        names: Iterable[str],
        *,
        invocation: InvocationContext,
        allow_side_effects: bool,
    ) -> tuple[LLMToolDefinition, ...]:
        manifests = {item.name: item for item in self._tools.list_manifests()}
        definitions: list[LLMToolDefinition] = []
        for name in dict.fromkeys(names):
            manifest = manifests.get(name)
            if manifest is None:
                raise LLMToolLoopConfigurationError(f"工具“{name}”尚未注册。")
            if (
                invocation.caller_name not in manifest.allowed_callers
                and invocation.caller_type not in manifest.allowed_callers
            ):
                raise LLMToolLoopConfigurationError(
                    f"调用方“{invocation.caller_name}”无权使用工具“{name}”。"
                )
            if not allow_side_effects and manifest.side_effect in {
                ToolSideEffect.WRITE,
                ToolSideEffect.HIGH_RISK_WRITE,
            }:
                continue
            definitions.append(
                LLMToolDefinition(
                    name=manifest.name,
                    description=manifest.description,
                    parameters=manifest.input_schema.model_json_schema(),
                )
            )
        return tuple(definitions)

    async def _execute(
        self,
        tool_call: LLMToolCall,
        *,
        invocation: InvocationContext,
        allowed_names: set[str],
        max_retries: int,
    ) -> tuple[LLMMessage, LLMToolExecutionState]:
        if tool_call.name not in allowed_names:
            return _failed_tool_result(
                tool_call,
                LLMToolProtocolError(f"模型请求了未授权工具“{tool_call.name}”。"),
            )
        try:
            arguments = json.loads(tool_call.arguments_json)
            if not isinstance(arguments, dict):
                raise ValueError("工具参数必须是 JSON 对象。")
        except (json.JSONDecodeError, ValueError) as error:
            return _failed_tool_result(tool_call, error)

        manifest = self._tools.get_manifest(tool_call.name)
        if "idempotency_key" in manifest.input_schema.model_fields:
            arguments.setdefault(
                "idempotency_key",
                f"{invocation.run_id}:{tool_call.call_id}",
            )
        last_error: Exception | None = None
        retry_count = 0
        for attempt in range(max_retries + 1):
            child = invocation.child(
                caller_type=invocation.caller_type,
                caller_name=invocation.caller_name,
                phase=f"{invocation.phase}:native_tool:{tool_call.name}",
            )
            try:
                envelope = await self._tools.invoke(
                    tool_call.name,
                    arguments,
                    child,
                )
                content = json.dumps(
                    envelope.output.model_dump(mode="json"),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                return (
                    LLMMessage(
                        role="tool",
                        content=content,
                        tool_call_id=tool_call.call_id,
                        tool_name=tool_call.name,
                    ),
                    LLMToolExecutionState(
                        call_id=tool_call.call_id,
                        tool_name=tool_call.name,
                        status="completed",
                        retry_count=retry_count,
                    ),
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001
                last_error = error
                if not manifest.retryable or attempt >= max_retries:
                    break
                retry_count += 1
        assert last_error is not None
        return _failed_tool_result(tool_call, last_error, retry_count=retry_count)


def _failed_tool_result(
    tool_call: LLMToolCall,
    error: Exception,
    *,
    retry_count: int = 0,
) -> tuple[LLMMessage, LLMToolExecutionState]:
    error_message = str(error)[:2_000] or "工具执行失败。"
    content = json.dumps(
        {
            "status": "failed",
            "error_type": type(error).__name__,
            "error_message": error_message,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        LLMMessage(
            role="tool",
            content=content,
            tool_call_id=tool_call.call_id,
            tool_name=tool_call.name,
            is_error=True,
        ),
        LLMToolExecutionState(
            call_id=tool_call.call_id,
            tool_name=tool_call.name,
            status="failed",
            retry_count=retry_count,
            error_type=type(error).__name__,
            error_message=error_message,
        ),
    )


class LLMToolLoopError(RuntimeError):
    pass


class LLMToolLoopConfigurationError(LLMToolLoopError):
    pass


class LLMToolProtocolError(LLMToolLoopError):
    pass


class LLMToolCallBudgetExceeded(LLMToolLoopError):
    pass


class LLMToolRoundBudgetExceeded(LLMToolLoopError):
    pass


class LLMToolLoopTimeoutError(LLMToolLoopError):
    pass
