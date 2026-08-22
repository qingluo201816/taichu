"""LLM exchange 四行状态矩阵与不改变底层语义的 observer。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any, Literal


class GatewayOutcome(StrEnum):
    RETURNED = "returned"
    RAISED = "raised"


class ObservationStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


_POST_GATEWAY_VALIDATION_ERRORS = frozenset(
    {
        "JSONDecodeError",
        "ValidationError",
        "SchemaValidationError",
        "PydanticValidationError",
    }
)


def validate_exchange_status_matrix(
    *,
    track: Literal["synthetic", "live_provider"] | str,
    gateway_outcome: GatewayOutcome,
    driver_status: ObservationStatus | None,
    trace_status: ObservationStatus,
    trace_error_type: str | None,
    replay_status: ObservationStatus | None,
    usage_status: ObservationStatus,
) -> tuple[str, ...]:
    """只接受设计声明的四行组合，不按近似状态猜测关联。"""
    problems: list[str] = []
    expected = (
        ObservationStatus.COMPLETED
        if gateway_outcome is GatewayOutcome.RETURNED
        else ObservationStatus.FAILED
    )
    if trace_status is not expected:
        allowed_schema_failure = (
            gateway_outcome is GatewayOutcome.RETURNED
            and trace_status is ObservationStatus.FAILED
            and trace_error_type in _POST_GATEWAY_VALIDATION_ERRORS
        )
        if not allowed_schema_failure:
            problems.append("TRACE_STATUS_INVALID")
    if track == "live_provider":
        if driver_status is not None:
            problems.append("LIVE_DRIVER_MUST_BE_NOT_APPLICABLE")
        if replay_status is not expected:
            problems.append("REPLAY_STATUS_INVALID")
        if usage_status is not expected:
            problems.append("USAGE_STATUS_INVALID")
    elif track == "synthetic":
        if driver_status is not expected:
            problems.append("DRIVER_STATUS_INVALID")
        if replay_status is not None:
            problems.append("SYNTHETIC_REPLAY_MUST_BE_NOT_APPLICABLE")
        if usage_status is not expected:
            problems.append("FIXED_USAGE_STATUS_INVALID")
    else:
        problems.append("TRACK_INVALID")
    return tuple(problems)


class SafeGatewayObserver:
    """底层恰调用一次；observer/report 失败只进入独立 problems。"""

    def __init__(
        self,
        *,
        invoke_underlying: Callable[[object], Awaitable[Any]],
        report: Callable[[object], Awaitable[None]],
    ) -> None:
        self._invoke_underlying = invoke_underlying
        self._report = report
        self._problems: list[str] = []

    @property
    def problems(self) -> tuple[str, ...]:
        return tuple(self._problems)

    async def invoke(self, request: object) -> Any:
        try:
            result = await self._invoke_underlying(request)
        except BaseException as error:
            await self._safe_report(
                {
                    "gateway_outcome": GatewayOutcome.RAISED,
                    "error_type": type(error).__name__,
                }
            )
            raise
        await self._safe_report(
            {
                "gateway_outcome": GatewayOutcome.RETURNED,
                "result_type": type(result).__name__,
            }
        )
        return result

    async def _safe_report(self, observation: object) -> None:
        try:
            await self._report(observation)
        except Exception:
            self._problems.append("correlation_repository_unavailable")
