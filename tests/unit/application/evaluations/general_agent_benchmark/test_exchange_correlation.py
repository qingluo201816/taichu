"""评测 LLM exchange 状态矩阵与 observer 故障隔离。"""

from __future__ import annotations

import asyncio

import pytest

from taichu.application.evaluations.general_agent_benchmark.exchange_correlation import (
    GatewayOutcome,
    ObservationStatus,
    SafeGatewayObserver,
    validate_exchange_status_matrix,
)


@pytest.mark.parametrize(
    ("track", "outcome", "driver", "trace", "replay", "usage"),
    [
        ("live_provider", "returned", None, "completed", "completed", "completed"),
        ("live_provider", "raised", None, "failed", "failed", "failed"),
        ("synthetic", "returned", "completed", "completed", None, "completed"),
        ("synthetic", "raised", "failed", "failed", None, "failed"),
    ],
)
def test_four_exchange_status_matrix_rows_are_explicit(
    track: str,
    outcome: str,
    driver: str | None,
    trace: str,
    replay: str | None,
    usage: str,
) -> None:
    assert (
        validate_exchange_status_matrix(
            track=track,
            gateway_outcome=GatewayOutcome(outcome),
            driver_status=ObservationStatus(driver) if driver else None,
            trace_status=ObservationStatus(trace),
            trace_error_type=None,
            replay_status=ObservationStatus(replay) if replay else None,
            usage_status=ObservationStatus(usage),
        )
        == ()
    )

    assert validate_exchange_status_matrix(
        track=track,
        gateway_outcome=GatewayOutcome(outcome),
        driver_status=ObservationStatus(driver) if driver else None,
        trace_status=ObservationStatus.FAILED
        if trace == "completed"
        else ObservationStatus.COMPLETED,
        trace_error_type=None,
        replay_status=ObservationStatus(replay) if replay else None,
        usage_status=ObservationStatus(usage),
    )


def test_live_returned_allows_only_proven_post_gateway_schema_failure() -> None:
    assert (
        validate_exchange_status_matrix(
            track="live_provider",
            gateway_outcome=GatewayOutcome.RETURNED,
            driver_status=None,
            trace_status=ObservationStatus.FAILED,
            trace_error_type="ValidationError",
            replay_status=ObservationStatus.COMPLETED,
            usage_status=ObservationStatus.COMPLETED,
        )
        == ()
    )
    assert validate_exchange_status_matrix(
        track="live_provider",
        gateway_outcome=GatewayOutcome.RETURNED,
        driver_status=None,
        trace_status=ObservationStatus.FAILED,
        trace_error_type="TimeoutError",
        replay_status=ObservationStatus.COMPLETED,
        usage_status=ObservationStatus.COMPLETED,
    ) == ("TRACE_STATUS_INVALID",)


def test_observer_or_repository_failure_never_changes_underlying_outcome() -> None:
    calls = 0

    async def returned(_: object) -> str:
        nonlocal calls
        calls += 1
        return "原始返回"

    async def failed_report(_: object) -> None:
        raise OSError("repository unavailable")

    observer = SafeGatewayObserver(invoke_underlying=returned, report=failed_report)
    assert asyncio.run(observer.invoke({"input": "甲"})) == "原始返回"
    assert calls == 1
    assert observer.problems == ("correlation_repository_unavailable",)

    original = TimeoutError("原始异常")

    async def raised(_: object) -> str:
        raise original

    observer = SafeGatewayObserver(invoke_underlying=raised, report=failed_report)
    with pytest.raises(TimeoutError) as captured:
        asyncio.run(observer.invoke({"input": "乙"}))
    assert captured.value is original
    assert observer.problems == ("correlation_repository_unavailable",)
