"""需求 9.1—9.9：评测运行状态机、取消、中断与幂等恢复。"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import TypeVar

import pytest

from taichu.application.evaluations.general_agent_benchmark.lifecycle import (
    BenchmarkLifecycleService,
    BenchmarkRunner,
    InMemorySuiteRunStore,
    SuiteRunRevisionConflict,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    SuiteConclusion,
    SuiteRunLifecycle,
)

_ResultT = TypeVar("_ResultT")


def _run(awaitable: Coroutine[object, object, _ResultT]) -> _ResultT:
    return asyncio.run(awaitable)


def test_lifecycle_only_exposes_conclusion_after_finalizing() -> None:
    async def scenario() -> None:
        store = InMemorySuiteRunStore()
        service = BenchmarkLifecycleService(store)
        created = await service.create(
            run_id="benchmark_run_20260727T000000Z_abcdef123456",
            suite_content_hash="a" * 64,
            selected_case_ids=("case_a",),
            track="synthetic",
        )
        running = await service.start(created.run_id, expected_revision=0)
        recorded = await service.record_case(
            running.run_id,
            case_id="case_a",
            case_row_ref="case-row-a",
            expected_revision=1,
        )
        finalizing = await service.begin_finalizing(
            recorded.run_id,
            expected_revision=2,
        )
        completed = await service.complete(
            finalizing.run_id,
            conclusion=SuiteConclusion.PASSED,
            terminal_artifact_ref="artifact-suite-a",
            expected_revision=3,
        )

        assert [
            created.lifecycle,
            running.lifecycle,
            recorded.lifecycle,
            finalizing.lifecycle,
            completed.lifecycle,
        ] == [
            SuiteRunLifecycle.QUEUED,
            SuiteRunLifecycle.RUNNING,
            SuiteRunLifecycle.RUNNING,
            SuiteRunLifecycle.FINALIZING,
            SuiteRunLifecycle.COMPLETED,
        ]
        assert all(
            item.conclusion is None
            for item in (created, running, recorded, finalizing)
        )
        assert completed.conclusion is SuiteConclusion.PASSED

    _run(scenario())


def test_run_listing_uses_creation_order_instead_of_hash_suffix_order() -> None:
    async def scenario() -> None:
        store = InMemorySuiteRunStore()
        service = BenchmarkLifecycleService(store)
        await service.create(
            run_id="benchmark_run_20260727T000010Z_ffffffffffff",
            suite_content_hash="a" * 64,
            selected_case_ids=("case_a",),
            track="synthetic",
        )
        await service.create(
            run_id="benchmark_run_20260727T000010Z_000000000000",
            suite_content_hash="a" * 64,
            selected_case_ids=("case_a",),
            track="synthetic",
        )

        runs, _revision, _snapshot = await store.list_snapshot()

        assert [run.run_id for run in runs] == [
            "benchmark_run_20260727T000010Z_000000000000",
            "benchmark_run_20260727T000010Z_ffffffffffff",
        ]

    _run(scenario())


def test_cancel_and_revision_conflict_do_not_create_false_completion() -> None:
    async def scenario() -> None:
        service = BenchmarkLifecycleService(InMemorySuiteRunStore())
        created = await service.create(
            run_id="benchmark_run_20260727T000001Z_abcdef123456",
            suite_content_hash="a" * 64,
            selected_case_ids=("case_a", "case_b"),
            track="synthetic",
        )
        running = await service.start(created.run_id, expected_revision=0)
        cancelling = await service.request_cancel(
            running.run_id,
            expected_revision=1,
        )
        cancelled = await service.finish_cancel(
            cancelling.run_id,
            expected_revision=2,
        )

        assert cancelling.lifecycle is SuiteRunLifecycle.CANCELLING
        assert cancelled.lifecycle is SuiteRunLifecycle.CANCELLED
        assert cancelled.conclusion is None
        assert cancelled.terminal_artifact_ref is None
        with pytest.raises(SuiteRunRevisionConflict):
            await service.start(created.run_id, expected_revision=0)

    _run(scenario())


def test_runner_resume_skips_frozen_case_rows_and_finishes_remaining_cases() -> None:
    async def scenario() -> None:
        store = InMemorySuiteRunStore()
        service = BenchmarkLifecycleService(store)
        await service.create(
            run_id="benchmark_run_20260727T000002Z_abcdef123456",
            suite_content_hash="a" * 64,
            selected_case_ids=("case_a", "case_b"),
            track="synthetic",
        )
        attempts: list[str] = []
        fail_once = True

        async def execute_case(_run_state, case_id: str) -> str:
            nonlocal fail_once
            attempts.append(case_id)
            if case_id == "case_b" and fail_once:
                fail_once = False
                raise RuntimeError("模拟进程中断")
            return f"case-row-{case_id}"

        async def finalize(_run_state) -> tuple[SuiteConclusion, str]:
            return SuiteConclusion.PASSED, "artifact-suite-complete"

        runner = BenchmarkRunner(
            lifecycle=service,
            execute_case=execute_case,
            finalize=finalize,
        )
        interrupted = await runner.run(
            "benchmark_run_20260727T000002Z_abcdef123456"
        )
        completed = await runner.run(interrupted.run_id)

        assert interrupted.lifecycle is SuiteRunLifecycle.UNFINISHED
        assert interrupted.case_row_refs == ("case-row-case_a",)
        assert completed.lifecycle is SuiteRunLifecycle.COMPLETED
        assert attempts == ["case_a", "case_b", "case_b"]

    _run(scenario())
