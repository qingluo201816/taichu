"""通用写作智能体固定基准、运行、生命周期与证据资源。"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from math import ceil
from typing import Any
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute

from taichu.api.deps import provide_general_agent_benchmark_services
from taichu.api.schemas.general_agent_benchmarks import (
    CaseResultResponse,
    EvidenceBundleResponse,
    ExperimentDetailResponse,
    ExperimentSubmissionRequest,
    ExperimentSubmissionResponse,
    FirstLiveIterationCreateRequest,
    FirstLiveIterationResponse,
    IssueCorrelationCommandRequest,
    IssueCorrelationCommandResponse,
    IssueCorrelationStatusResponse,
    LifecycleCommandRequest,
    LifecycleCommandResponse,
    ModelComparisonDetailResponse,
    ModelComparisonSubmissionRequest,
    PaginatedResponse,
    RunDetailResponse,
    RunSubmissionRequest,
    RunSubmissionResponse,
    SuiteArtifactResponse,
    SuiteDetailResponse,
    SuiteSummaryResponse,
)
from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.container import (
    GeneralAgentBenchmarkServices,
)
from taichu.application.evaluations.general_agent_benchmark.hydration import (
    QueryHydrationStatus,
)
from taichu.application.evaluations.general_agent_benchmark.lifecycle import (
    SuiteRunRevisionConflict,
    SuiteRunStateError,
)
from taichu.application.evaluations.general_agent_benchmark.experiments import (
    ExperimentSpec,
)
from taichu.application.evaluations.general_agent_benchmark.services import (
    BenchmarkSelectionRejected,
    BenchmarkSubmissionConflict,
    SubmissionRequest,
)


def _error_detail(
    *,
    error: str,
    message: str,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "error": error,
        "message": message,
        "request_id": f"req_{uuid4().hex}",
        "details": details or {},
    }


class RequestIdRoute(APIRoute):
    def get_route_handler(
        self,
    ) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError as error:
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    content={
                        "detail": _error_detail(
                            error="request_invalid",
                            message="请求参数不符合评测契约。",
                            details={
                                "issues": jsonable_encoder(error.errors())
                            },
                        )
                    },
                )
            except HTTPException:
                raise
            except Exception as error:
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={
                        "detail": _error_detail(
                            error="internal_error",
                            message="评测资源处理失败。",
                            details={"type": type(error).__name__},
                        )
                    },
                )

        return handler


router = APIRouter(
    prefix="/api/general-agent-benchmarks",
    tags=["通用写作智能体固定基准"],
    route_class=RequestIdRoute,
)


@router.get("/suites")
async def list_suites(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> PaginatedResponse[SuiteSummaryResponse]:
    entries = services.catalog.list()
    total = len(entries)
    offset = (page - 1) * page_size
    return PaginatedResponse[SuiteSummaryResponse](
        items=tuple(
            SuiteSummaryResponse.model_validate(item.model_dump())
            for item in entries[offset : offset + page_size]
        ),
        page=page,
        page_size=page_size,
        total=total,
        total_pages=ceil(total / page_size) if total else 0,
        index_revision=0,
        total_snapshot=canonical_sha256(entries),
    )


@router.get("/suites/{suite_id}")
async def get_suite(
    suite_id: str,
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> SuiteDetailResponse:
    try:
        suite = services.catalog.get_detail(suite_id)
    except KeyError as error:
        _not_found(str(error))
    return SuiteDetailResponse(suite=suite)


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def submit_run(
    request: RunSubmissionRequest,
    background_tasks: BackgroundTasks,
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> RunSubmissionResponse:
    try:
        run = await services.submissions.submit(
            SubmissionRequest(**request.model_dump())
        )
    except BenchmarkSubmissionConflict as error:
        _conflict(str(error))
    except BenchmarkSelectionRejected as error:
        selection = error.selection_error
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_error_detail(
                error="benchmark_selection_invalid",
                message=selection.message,
                details={
                    "code": selection.code,
                    "track": selection.track,
                    "case_ids": list(selection.case_ids),
                    "expected_case_ids": list(
                        selection.expected_case_ids
                    ),
                },
            ),
        ) from error
    background_tasks.add_task(services.runner.run, run.run_id)
    return RunSubmissionResponse(run=run)


@router.get("/runs")
async def list_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    total_snapshot: str | None = Query(default=None),
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> PaginatedResponse:
    _require_query_hydration(services)
    try:
        result = await services.queries.list_runs(
            page=page,
            page_size=page_size,
            total_snapshot=total_snapshot,
        )
    except (KeyError, ValueError) as error:
        _unprocessable(str(error))
    return PaginatedResponse(**result.model_dump())


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> RunDetailResponse:
    _require_query_hydration(services)
    try:
        run = await services.queries.get_run(run_id)
    except KeyError as error:
        _not_found(str(error))
    return RunDetailResponse(run=run)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    request: LifecycleCommandRequest,
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> LifecycleCommandResponse:
    try:
        run = await services.lifecycle.request_cancel(
            run_id,
            expected_revision=request.expected_revision,
        )
    except KeyError as error:
        _not_found(str(error))
    except (SuiteRunRevisionConflict, SuiteRunStateError) as error:
        _conflict(str(error))
    return LifecycleCommandResponse(run=run)


@router.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    request: LifecycleCommandRequest,
    background_tasks: BackgroundTasks,
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> LifecycleCommandResponse:
    try:
        run = await services.lifecycle.resume(
            run_id,
            expected_revision=request.expected_revision,
        )
    except KeyError as error:
        _not_found(str(error))
    except (SuiteRunRevisionConflict, SuiteRunStateError) as error:
        _conflict(str(error))
    background_tasks.add_task(services.runner.run, run.run_id)
    return LifecycleCommandResponse(run=run)


@router.get("/runs/{run_id}/cases")
async def list_case_results(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> PaginatedResponse:
    _require_query_hydration(services)
    try:
        result = services.resources.list_cases(
            run_id,
            page=page,
            page_size=page_size,
        )
    except KeyError as error:
        _not_found(str(error))
    return PaginatedResponse(
        **result.model_dump(exclude={"total_snapshot"}),
        index_revision=0,
        total_snapshot=result.total_snapshot,
    )


@router.get("/runs/{run_id}/cases/{case_id}")
async def get_case_result(
    run_id: str,
    case_id: str,
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> CaseResultResponse:
    _require_query_hydration(services)
    try:
        item = services.resources.get_case(run_id, case_id)
    except KeyError as error:
        _not_found(str(error))
    return CaseResultResponse(case=item)


@router.get("/runs/{run_id}/cases/{case_id}/evidence")
async def get_case_evidence(
    run_id: str,
    case_id: str,
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> EvidenceBundleResponse:
    _require_query_hydration(services)
    try:
        evidence = services.resources.get_evidence(run_id, case_id)
    except KeyError as error:
        _not_found(str(error))
    return EvidenceBundleResponse(evidence=evidence)


@router.get("/runs/{run_id}/artifact")
async def get_suite_artifact(
    run_id: str,
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> SuiteArtifactResponse:
    _require_query_hydration(services)
    try:
        artifact = services.resources.get_artifact(run_id)
    except KeyError as error:
        _not_found(str(error))
    return SuiteArtifactResponse(artifact=artifact)


def _not_found(message: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_error_detail(
            error="resource_not_found",
            message=message,
        ),
    )


def _conflict(message: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=_error_detail(
            error="resource_conflict",
            message=message,
        ),
    )


def _unprocessable(message: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=_error_detail(
            error="request_invalid",
            message=message,
        ),
    )


@router.post("/experiments", status_code=status.HTTP_201_CREATED)
async def create_experiment(
    request: ExperimentSubmissionRequest,
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> ExperimentSubmissionResponse:
    try:
        experiment = services.experiments.create(
            ExperimentSpec.model_validate(request.model_dump())
        )
    except ValueError as error:
        _conflict(str(error))
    return ExperimentSubmissionResponse(experiment=experiment)


@router.get("/experiments")
async def list_experiments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> PaginatedResponse:
    return _paginate(
        services.experiments.list(),
        page=page,
        page_size=page_size,
    )


@router.get("/experiments/{experiment_id}")
async def get_experiment(
    experiment_id: str,
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> ExperimentDetailResponse:
    try:
        experiment = services.experiments.get(experiment_id)
    except KeyError as error:
        _not_found(str(error))
    return ExperimentDetailResponse(experiment=experiment)


@router.post("/iterations", status_code=status.HTTP_201_CREATED)
async def create_iteration(
    request: FirstLiveIterationCreateRequest,
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> FirstLiveIterationResponse:
    try:
        iteration = services.first_live.create_iteration(
            **request.model_dump()
        )
    except ValueError as error:
        _conflict(str(error))
    return FirstLiveIterationResponse(iteration=iteration)


@router.get("/iterations")
async def list_iterations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> PaginatedResponse:
    _require_query_hydration(services)
    return _paginate(
        services.first_live.list_iterations(),
        page=page,
        page_size=page_size,
    )


@router.get("/iterations/{iteration_id}")
async def get_iteration(
    iteration_id: str,
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> FirstLiveIterationResponse:
    _require_query_hydration(services)
    try:
        iteration = services.first_live.get_manifest(iteration_id)
    except KeyError as error:
        _not_found(str(error))
    return FirstLiveIterationResponse(iteration=iteration)


@router.get("/iterations/{iteration_id}/issue-correlations")
async def get_issue_correlations(
    iteration_id: str,
    subject_id: str = Query(pattern=r"^[a-f0-9]{64}$"),
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> IssueCorrelationStatusResponse:
    try:
        correlation_status = services.issue_query.get_by_subject(subject_id)
    except KeyError as error:
        _not_found(str(error))
    if correlation_status.snapshot.iteration.iteration_id != iteration_id:
        _not_found("该迭代不存在指定 subject 关联。")
    return IssueCorrelationStatusResponse(status=correlation_status)


@router.get("/iterations/{iteration_id}/issue-correlation-observations")
async def list_issue_correlation_observations(
    iteration_id: str,
    intent_id: str = Query(min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> object:
    try:
        intent = next(
            item
            for item in await services.issue_correlation_repository.list_intents()
            if item.intent_id == intent_id
        )
    except StopIteration:
        _not_found("问题关联意图不存在。")
    if intent.iteration_id != iteration_id:
        _not_found("问题关联意图不属于指定迭代。")
    return await services.issue_query.list_observations(
        intent_id=intent_id,
        page=page,
        page_size=page_size,
    )


@router.post("/iterations/{iteration_id}/reconcile-issues")
async def reconcile_issue_correlations(
    iteration_id: str,
    request: IssueCorrelationCommandRequest,
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> IssueCorrelationCommandResponse:
    try:
        correlation_status = services.issue_query.get_by_subject(
            request.subject_id
        )
    except KeyError as error:
        _not_found(str(error))
    if correlation_status.snapshot.iteration.iteration_id != iteration_id:
        _not_found("该迭代不存在指定 subject 关联。")
    report = services.issue_reconciler.inspect(correlation_status.snapshot)
    return IssueCorrelationCommandResponse(report=report)


@router.post("/comparisons", status_code=status.HTTP_201_CREATED)
async def create_comparison(
    request: ModelComparisonSubmissionRequest,
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> ModelComparisonDetailResponse:
    try:
        comparison = services.model_comparisons.create(request)
    except ValueError as error:
        _conflict(str(error))
    return ModelComparisonDetailResponse(comparison=comparison)


@router.get("/comparisons")
async def list_comparisons(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> PaginatedResponse:
    _require_query_hydration(services)
    return _paginate(
        services.model_comparisons.list(),
        page=page,
        page_size=page_size,
    )


@router.get("/comparisons/{comparison_id}")
async def get_comparison(
    comparison_id: str,
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> ModelComparisonDetailResponse:
    _require_query_hydration(services)
    try:
        comparison = services.model_comparisons.get(comparison_id)
    except KeyError as error:
        _not_found(str(error))
    return ModelComparisonDetailResponse(comparison=comparison)


@router.get("/comparisons/{comparison_id}/admission")
async def get_comparison_admission(
    comparison_id: str,
    services: GeneralAgentBenchmarkServices = Depends(
        provide_general_agent_benchmark_services
    ),
) -> object:
    _require_query_hydration(services)
    try:
        comparison = services.model_comparisons.get(comparison_id)
    except KeyError as error:
        _not_found(str(error))
    return comparison.admission


def _paginate(
    items: tuple[object, ...],
    *,
    page: int,
    page_size: int,
) -> PaginatedResponse:
    total = len(items)
    offset = (page - 1) * page_size
    return PaginatedResponse(
        items=items[offset : offset + page_size],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=ceil(total / page_size) if total else 0,
        index_revision=total,
        total_snapshot=canonical_sha256(items),
    )


def _require_query_hydration(
    services: GeneralAgentBenchmarkServices,
) -> None:
    hydration = services.query_hydration
    if hydration.status is not QueryHydrationStatus.UNAVAILABLE:
        return
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=_error_detail(
            error="benchmark_query_unavailable",
            message="冻结评测查询索引不可用，已拒绝返回不完整结果。",
            details={
                "source_refs": list(hydration.source_refs),
                "problems": list(hydration.problems),
            },
        ),
    )
