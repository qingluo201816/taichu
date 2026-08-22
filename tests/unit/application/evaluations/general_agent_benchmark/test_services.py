"""需求 13.2、13.4、13.6、13.8、13.10、13.12、13.14：目录、提交与分页。"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import TypeVar

import pytest

from taichu.application.evaluations.general_agent_benchmark.lifecycle import (
    BenchmarkLifecycleService,
    InMemorySuiteRunStore,
)
from taichu.application.evaluations.general_agent_benchmark.services import (
    BenchmarkCatalogEntry,
    BenchmarkCatalogService,
    BenchmarkQueryService,
    BenchmarkSubmissionConflict,
    BenchmarkSubmissionService,
    SubmissionRequest,
)

_ResultT = TypeVar("_ResultT")


def _run(awaitable: Coroutine[object, object, _ResultT]) -> _ResultT:
    return asyncio.run(awaitable)


def _request(index: int, *, key: str | None = None) -> SubmissionRequest:
    return SubmissionRequest(
        idempotency_key=key or f"submit-{index}",
        run_id=f"benchmark_run_20260727T{index:06d}Z_abcdef123456",
        suite_id="general_writing_agent_core",
        suite_content_hash="a" * 64,
        selected_case_ids=("case_a",),
        track="synthetic",
    )


def test_catalog_lookup_and_submission_are_idempotent() -> None:
    async def scenario() -> None:
        catalog = BenchmarkCatalogService(
            (
                BenchmarkCatalogEntry(
                    suite_id="general_writing_agent_core",
                    name="通用写作智能体固定基准",
                    content_hash="a" * 64,
                    case_count=37,
                ),
            )
        )
        store = InMemorySuiteRunStore()
        submissions = BenchmarkSubmissionService(
            lifecycle=BenchmarkLifecycleService(store),
        )

        assert catalog.get("general_writing_agent_core").case_count == 37
        first = await submissions.submit(_request(1, key="same-key"))
        repeated = await submissions.submit(_request(1, key="same-key"))
        assert repeated.run_id == first.run_id
        with pytest.raises(BenchmarkSubmissionConflict):
            await submissions.submit(_request(2, key="same-key"))

    _run(scenario())


def test_query_uses_snapshot_pagination_across_concurrent_insert() -> None:
    async def scenario() -> None:
        store = InMemorySuiteRunStore()
        lifecycle = BenchmarkLifecycleService(store)
        submissions = BenchmarkSubmissionService(lifecycle=lifecycle)
        query = BenchmarkQueryService(store)
        for index in range(1, 4):
            await submissions.submit(_request(index))

        first = await query.list_runs(page=1, page_size=2)
        await submissions.submit(_request(4))
        second = await query.list_runs(
            page=2,
            page_size=2,
            total_snapshot=first.total_snapshot,
        )

        assert first.total == 3
        assert first.total_pages == 2
        assert second.total == 3
        assert second.total_snapshot == first.total_snapshot
        assert len({item.run_id for item in (*first.items, *second.items)}) == 3
        assert (await query.get_run(first.items[0].run_id)).run_id == first.items[0].run_id

    _run(scenario())
