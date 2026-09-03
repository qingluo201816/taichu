"""需求 10.3、10.13、13.5、14.5：新评测应用服务的独立组合。"""

from __future__ import annotations

from dataclasses import dataclass

from taichu.application.evaluations.general_agent_benchmark.closure import (
    IssueClosureCoordinator,
    ModelComparisonService,
)
from taichu.application.evaluations.general_agent_benchmark.experiments import (
    ExperimentService,
)
from taichu.application.evaluations.general_agent_benchmark.first_live import (
    FirstLiveIterationService,
)
from taichu.application.evaluations.general_agent_benchmark.hydration import (
    BenchmarkQueryHydration,
    QueryHydrationStatus,
)
from taichu.application.evaluations.general_agent_benchmark.issue_correlations import (
    IssueCorrelationQueryService,
    IssueCorrelationReconciler,
    IssueCorrelationRepository,
)
from taichu.application.evaluations.general_agent_benchmark.lifecycle import (
    BenchmarkLifecycleService,
    BenchmarkRunner,
    CaseExecutor,
    SuiteFinalizer,
    SuiteRunStore,
)
from taichu.application.evaluations.general_agent_benchmark.observability import (
    BenchmarkObservabilityQuery,
    UnavailableBenchmarkObservabilityQuery,
)
from taichu.application.evaluations.general_agent_benchmark.resources import (
    BenchmarkRunResourceService,
)
from taichu.application.evaluations.general_agent_benchmark.services import (
    BenchmarkCatalogEntry,
    BenchmarkCatalogService,
    BenchmarkQueryService,
    BenchmarkSubmissionService,
)
from taichu.application.evaluations.general_agent_benchmark.suite_loader import (
    AuthoredSuiteSpec,
)


@dataclass(frozen=True, slots=True)
class GeneralAgentBenchmarkServices:
    catalog: BenchmarkCatalogService
    lifecycle: BenchmarkLifecycleService
    submissions: BenchmarkSubmissionService
    queries: BenchmarkQueryService
    runner: BenchmarkRunner
    resources: BenchmarkRunResourceService
    experiments: ExperimentService
    first_live: FirstLiveIterationService
    issue_correlation_repository: IssueCorrelationRepository
    issue_query: IssueCorrelationQueryService
    issue_reconciler: IssueCorrelationReconciler
    issue_closure: IssueClosureCoordinator
    model_comparisons: ModelComparisonService
    query_hydration: BenchmarkQueryHydration
    observability: BenchmarkObservabilityQuery


def build_general_agent_benchmark_services(
    *,
    catalog_entries: tuple[BenchmarkCatalogEntry, ...],
    suite_run_store: SuiteRunStore,
    execute_case: CaseExecutor,
    finalize_suite: SuiteFinalizer,
    issue_correlation_repository: IssueCorrelationRepository,
    query_hydration: BenchmarkQueryHydration | None = None,
    authored_suites: tuple[AuthoredSuiteSpec, ...] = (),
    resources: BenchmarkRunResourceService | None = None,
    observability: BenchmarkObservabilityQuery | None = None,
) -> GeneralAgentBenchmarkServices:
    """仅从显式评测依赖构造服务，不读取活动应用全局状态。"""

    lifecycle = BenchmarkLifecycleService(suite_run_store)
    hydration = query_hydration or BenchmarkQueryHydration.not_configured()
    catalog = BenchmarkCatalogService(
        catalog_entries,
        authored_suites=authored_suites,
    )
    first_live = FirstLiveIterationService()
    model_comparisons = ModelComparisonService()
    resources = resources or BenchmarkRunResourceService()
    observability = observability or UnavailableBenchmarkObservabilityQuery(
        project_name="未配置",
        suite_content_hash=(
            catalog_entries[0].content_hash if catalog_entries else "0" * 64
        ),
    )
    if hydration.status in {
        QueryHydrationStatus.AVAILABLE,
        QueryHydrationStatus.PARTIAL,
    }:
        restore_run = getattr(suite_run_store, "restore_frozen", None)
        if restore_run is None:
            raise TypeError("评测运行存储不支持冻结查询恢复。")
        synthetic_entries = tuple(
            entry
            for entry in hydration.synthetic_entries
            if entry.suite_run is not None and entry.suite_artifact is not None
        )
        if synthetic_entries:
            # 冻结目录按“当前、由新到旧的历史”提供；查询存储按恢复顺序
            # 记录新鲜度，因此先恢复最旧历史，最后恢复当前活动基线。
            for entry in reversed(synthetic_entries):
                assert entry.suite_run is not None
                assert entry.suite_artifact is not None
                restore_run(entry.suite_run)
                resources.register(entry.suite_artifact)
        elif hydration.suite_run is not None and hydration.suite_artifact is not None:
            restore_run(hydration.suite_run)
            resources.register(hydration.suite_artifact)
        if (
            hydration.first_live_iteration is not None
            and hydration.first_live_artifact is not None
        ):
            first_live.restore_frozen(
                hydration.first_live_iteration,
                hydration.first_live_artifact,
            )
        if hydration.blocked_comparison is not None:
            model_comparisons.restore_frozen(hydration.blocked_comparison)
    return GeneralAgentBenchmarkServices(
        catalog=catalog,
        lifecycle=lifecycle,
        submissions=BenchmarkSubmissionService(
            lifecycle=lifecycle,
            catalog=catalog,
        ),
        queries=BenchmarkQueryService(suite_run_store),
        runner=BenchmarkRunner(
            lifecycle=lifecycle,
            execute_case=execute_case,
            finalize=finalize_suite,
        ),
        resources=resources,
        experiments=ExperimentService(),
        first_live=first_live,
        issue_correlation_repository=issue_correlation_repository,
        issue_query=IssueCorrelationQueryService(issue_correlation_repository),
        issue_reconciler=IssueCorrelationReconciler(),
        issue_closure=IssueClosureCoordinator(),
        model_comparisons=model_comparisons,
        query_hydration=hydration,
        observability=observability,
    )
