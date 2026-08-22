"""需求 10.3、10.13、13.5、14.5：独立评测应用服务组合。"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Coroutine
from typing import TypeVar

from taichu.application.evaluations.general_agent_benchmark.container import (
    build_general_agent_benchmark_services,
)
from taichu.application.evaluations.general_agent_benchmark.issue_correlations import (
    IssueCorrelationRepository,
)
from taichu.application.evaluations.general_agent_benchmark.lifecycle import (
    InMemorySuiteRunStore,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    SuiteConclusion,
    SuiteRun,
)
from taichu.application.evaluations.general_agent_benchmark.services import (
    BenchmarkCatalogEntry,
    SubmissionRequest,
)

_ResultT = TypeVar("_ResultT")


def _run(awaitable: Coroutine[object, object, _ResultT]) -> _ResultT:
    return asyncio.run(awaitable)


async def _execute_case(run: SuiteRun, case_id: str) -> str:
    return f"row:{run.run_id}:{case_id}"


async def _finalize(run: SuiteRun) -> tuple[SuiteConclusion, str]:
    return SuiteConclusion.PASSED, f"artifact:{run.run_id}"


def test_container_composes_all_services_with_shared_explicit_dependencies() -> None:
    async def scenario() -> None:
        store = InMemorySuiteRunStore()
        issue_repository = IssueCorrelationRepository()
        services = build_general_agent_benchmark_services(
            catalog_entries=(
                BenchmarkCatalogEntry(
                    suite_id="general_writing_agent_core",
                    name="通用写作智能体固定基准",
                    content_hash="a" * 64,
                    case_count=37,
                ),
            ),
            suite_run_store=store,
            execute_case=_execute_case,
            finalize_suite=_finalize,
            issue_correlation_repository=issue_repository,
        )

        assert services.issue_correlation_repository is issue_repository
        assert services.catalog.get("general_writing_agent_core").case_count == 37
        assert services.experiments is not None
        assert services.first_live is not None
        assert services.issue_closure is not None
        assert services.model_comparisons is not None
        assert services.issue_query is not None
        submitted = await services.submissions.submit(
            SubmissionRequest(
                idempotency_key="container-run",
                run_id="benchmark_run_20260727T000001Z_abcdef123456",
                suite_id="general_writing_agent_core",
                suite_content_hash="a" * 64,
                selected_case_ids=("case_a",),
                track="synthetic",
            )
        )
        assert (await services.queries.get_run(submitted.run_id)).run_id == (
            submitted.run_id
        )

    _run(scenario())


def test_container_has_no_normal_runtime_or_old_evaluation_dependency() -> None:
    source = inspect.getsource(build_general_agent_benchmark_services)

    assert "application.general_agent" not in source
    assert "evaluations.general_agent.service" not in source
    assert "create_app" not in source
