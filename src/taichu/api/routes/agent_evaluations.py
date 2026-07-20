"""Knowledge-extraction effect-evaluation endpoints."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from taichu.api.deps import provide_knowledge_extraction_evaluation_service
from taichu.api.schemas.agent_evaluations import (
    CreateKnowledgeEvaluationRequest,
    EligibleEvaluationRun,
    EligibleEvaluationRunListResponse,
    EvaluationDatasetDetailResponse,
    EvaluationDatasetListResponse,
    EvaluationDatasetValidationResponse,
    EvaluationDeleteResponse,
    EvaluationJudgeCallResponse,
    KnowledgeEvaluationComparison,
    KnowledgeEvaluationComparisonListResponse,
    KnowledgeEvaluationDetailResponse,
    KnowledgeEvaluationListResponse,
    KnowledgeEvaluationPreviewResponse,
    KnowledgeEvaluationResponse,
)
from taichu.application.evaluations.knowledge_extraction.records import (
    EvaluationComparison,
    KnowledgeEvaluationRecord,
)
from taichu.application.services.knowledge_extraction_evaluation_service import (
    EvaluationServiceError,
    KnowledgeExtractionEvaluationService,
)
from taichu.infrastructure.evaluations.json_dataset_repository import (
    EvaluationDatasetRepositoryError,
)
from taichu.infrastructure.evaluations.json_result_store import (
    EvaluationResultStoreError,
)


router = APIRouter(prefix="/api/agent-evaluations/knowledge-extraction")

_DATASET_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")
_EVALUATION_ID_PATTERN = re.compile(r"^knowledge_eval_\d{8}_\d{6}_[a-z0-9]{6}$")
_RUN_ID_PATTERN = re.compile(r"^extract_run_\d{8}_\d{6}_[a-z0-9]{6}$")
_CALL_ID_PATTERN = re.compile(r"^judge_call_[a-z0-9]{12}$")

_HTTP_STATUS_BY_CODE = {
    "EVALUATION_DATASET_NOT_FOUND": 404,
    "EVALUATION_DATASET_INVALID": 422,
    "EVALUATION_SCOPE_MISMATCH": 409,
    "EVALUATION_SOURCE_CHANGED": 409,
    "EVALUATION_RUN_NOT_FOUND": 404,
    "EVALUATION_CANDIDATE_SNAPSHOT_MISSING": 409,
    "EVALUATION_JUDGE_UNAVAILABLE": 503,
    "EVALUATION_ALREADY_RUNNING": 409,
    "EVALUATION_INVALID_TRANSITION": 409,
    "EVALUATION_ID_INVALID": 422,
    "EVALUATION_SNAPSHOT_CORRUPTED": 500,
    "EVALUATION_EXECUTION_FAILED": 500,
    "EVALUATION_NOT_FOUND": 404,
}
_EVALUATION_ERRORS = (
    EvaluationServiceError,
    EvaluationDatasetRepositoryError,
    EvaluationResultStoreError,
)


@router.get("/datasets", response_model=EvaluationDatasetListResponse)
async def list_evaluation_datasets(
    service: KnowledgeExtractionEvaluationService = Depends(
        provide_knowledge_extraction_evaluation_service
    ),
) -> EvaluationDatasetListResponse:
    try:
        datasets = await service.list_datasets()
    except _EVALUATION_ERRORS as error:
        raise _http_error(error) from error
    return EvaluationDatasetListResponse(datasets=datasets)


@router.get(
    "/datasets/{dataset_id}",
    response_model=EvaluationDatasetDetailResponse,
)
async def get_evaluation_dataset(
    dataset_id: str,
    service: KnowledgeExtractionEvaluationService = Depends(
        provide_knowledge_extraction_evaluation_service
    ),
) -> EvaluationDatasetDetailResponse:
    _validate_id(dataset_id, _DATASET_ID_PATTERN, "评测集")
    try:
        dataset = await service.get_dataset(dataset_id)
    except _EVALUATION_ERRORS as error:
        raise _http_error(error) from error
    return EvaluationDatasetDetailResponse(dataset=dataset)


@router.post(
    "/datasets/{dataset_id}/validate",
    response_model=EvaluationDatasetValidationResponse,
)
async def validate_evaluation_dataset(
    dataset_id: str,
    service: KnowledgeExtractionEvaluationService = Depends(
        provide_knowledge_extraction_evaluation_service
    ),
) -> EvaluationDatasetValidationResponse:
    _validate_id(dataset_id, _DATASET_ID_PATTERN, "评测集")
    try:
        validation = await service.validate_dataset(dataset_id)
    except _EVALUATION_ERRORS as error:
        raise _http_error(error) from error
    return EvaluationDatasetValidationResponse(validation=validation)


@router.get("/eligible-runs", response_model=EligibleEvaluationRunListResponse)
async def list_eligible_evaluation_runs(
    dataset_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    service: KnowledgeExtractionEvaluationService = Depends(
        provide_knowledge_extraction_evaluation_service
    ),
) -> EligibleEvaluationRunListResponse:
    _validate_id(dataset_id, _DATASET_ID_PATTERN, "评测集")
    try:
        runs, total = await service.list_eligible_runs(
            dataset_id=dataset_id,
            page=page,
            page_size=page_size,
        )
    except _EVALUATION_ERRORS as error:
        raise _http_error(error) from error
    return EligibleEvaluationRunListResponse(
        runs=[EligibleEvaluationRun.model_validate(item) for item in runs],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/preview", response_model=KnowledgeEvaluationPreviewResponse)
async def preview_knowledge_evaluation(
    request: CreateKnowledgeEvaluationRequest,
    service: KnowledgeExtractionEvaluationService = Depends(
        provide_knowledge_extraction_evaluation_service
    ),
) -> KnowledgeEvaluationPreviewResponse:
    _validate_request_ids(request)
    try:
        preview = await service.preview(**request.model_dump())
    except _EVALUATION_ERRORS as error:
        raise _http_error(error) from error
    return KnowledgeEvaluationPreviewResponse.model_validate(_round_floats(preview))


@router.post(
    "/evaluations",
    response_model=KnowledgeEvaluationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_knowledge_evaluation(
    request: CreateKnowledgeEvaluationRequest,
    service: KnowledgeExtractionEvaluationService = Depends(
        provide_knowledge_extraction_evaluation_service
    ),
) -> KnowledgeEvaluationResponse:
    _validate_request_ids(request)
    try:
        record = await service.create_evaluation(**request.model_dump())
    except _EVALUATION_ERRORS as error:
        raise _http_error(error) from error
    return _record_response(record)


@router.get("/evaluations", response_model=KnowledgeEvaluationListResponse)
async def list_knowledge_evaluations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str = Query(default="all", alias="status"),
    service: KnowledgeExtractionEvaluationService = Depends(
        provide_knowledge_extraction_evaluation_service
    ),
) -> KnowledgeEvaluationListResponse:
    try:
        records, total = await service.list_evaluations(
            page=page,
            page_size=page_size,
            status=status_filter,
        )
    except _EVALUATION_ERRORS as error:
        raise _http_error(error) from error
    return KnowledgeEvaluationListResponse(
        evaluations=[_record_response(record) for record in records],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/evaluations/{evaluation_id}",
    response_model=KnowledgeEvaluationDetailResponse,
)
async def get_knowledge_evaluation(
    evaluation_id: str,
    service: KnowledgeExtractionEvaluationService = Depends(
        provide_knowledge_extraction_evaluation_service
    ),
) -> KnowledgeEvaluationDetailResponse:
    _validate_id(evaluation_id, _EVALUATION_ID_PATTERN, "评估")
    try:
        record = await service.get_evaluation(evaluation_id)
    except _EVALUATION_ERRORS as error:
        raise _http_error(error) from error
    return KnowledgeEvaluationDetailResponse(evaluation=_record_response(record))


@router.get(
    "/evaluations/{evaluation_id}/comparisons",
    response_model=KnowledgeEvaluationComparisonListResponse,
)
async def list_knowledge_evaluation_comparisons(
    evaluation_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    run_id: str | None = None,
    knowledge_type: str | None = None,
    issue_type: str | None = None,
    service: KnowledgeExtractionEvaluationService = Depends(
        provide_knowledge_extraction_evaluation_service
    ),
) -> KnowledgeEvaluationComparisonListResponse:
    _validate_id(evaluation_id, _EVALUATION_ID_PATTERN, "评估")
    if run_id is not None:
        _validate_id(run_id, _RUN_ID_PATTERN, "历史任务")
    try:
        comparisons, total = await service.list_comparisons(
            evaluation_id,
            page=page,
            page_size=page_size,
            run_id=run_id,
            knowledge_type=knowledge_type,
            issue_type=issue_type,
        )
    except _EVALUATION_ERRORS as error:
        raise _http_error(error) from error
    return KnowledgeEvaluationComparisonListResponse(
        comparisons=[_comparison_response(item) for item in comparisons],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/evaluations/{evaluation_id}/judge-calls/{call_id}",
    response_model=EvaluationJudgeCallResponse,
)
async def get_knowledge_evaluation_judge_call(
    evaluation_id: str,
    call_id: str,
    service: KnowledgeExtractionEvaluationService = Depends(
        provide_knowledge_extraction_evaluation_service
    ),
) -> EvaluationJudgeCallResponse:
    _validate_id(evaluation_id, _EVALUATION_ID_PATTERN, "评估")
    _validate_id(call_id, _CALL_ID_PATTERN, "裁判调用")
    try:
        judge_call = await service.get_judge_call(evaluation_id, call_id)
    except _EVALUATION_ERRORS as error:
        raise _http_error(error) from error
    return EvaluationJudgeCallResponse(judge_call=judge_call)


@router.post(
    "/evaluations/{evaluation_id}/retry",
    response_model=KnowledgeEvaluationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_knowledge_evaluation(
    evaluation_id: str,
    service: KnowledgeExtractionEvaluationService = Depends(
        provide_knowledge_extraction_evaluation_service
    ),
) -> KnowledgeEvaluationResponse:
    _validate_id(evaluation_id, _EVALUATION_ID_PATTERN, "评估")
    try:
        record = await service.retry_evaluation(evaluation_id)
    except _EVALUATION_ERRORS as error:
        raise _http_error(error) from error
    return _record_response(record)


@router.post(
    "/evaluations/{evaluation_id}/confirm",
    response_model=KnowledgeEvaluationResponse,
)
async def confirm_knowledge_evaluation(
    evaluation_id: str,
    service: KnowledgeExtractionEvaluationService = Depends(
        provide_knowledge_extraction_evaluation_service
    ),
) -> KnowledgeEvaluationResponse:
    _validate_id(evaluation_id, _EVALUATION_ID_PATTERN, "评估")
    try:
        record = await service.confirm_evaluation(evaluation_id)
    except _EVALUATION_ERRORS as error:
        raise _http_error(error) from error
    return _record_response(record)


@router.delete(
    "/evaluations/{evaluation_id}",
    response_model=EvaluationDeleteResponse,
)
async def reject_knowledge_evaluation(
    evaluation_id: str,
    service: KnowledgeExtractionEvaluationService = Depends(
        provide_knowledge_extraction_evaluation_service
    ),
) -> EvaluationDeleteResponse:
    _validate_id(evaluation_id, _EVALUATION_ID_PATTERN, "评估")
    try:
        await service.reject_evaluation(evaluation_id)
    except _EVALUATION_ERRORS as error:
        raise _http_error(error) from error
    return EvaluationDeleteResponse(evaluation_id=evaluation_id)


@router.api_route(
    "/evaluations/{unsafe_path:path}",
    methods=["GET", "POST", "DELETE"],
    include_in_schema=False,
)
async def reject_unsafe_evaluation_path(unsafe_path: str) -> None:
    """Return the stable ID error for decoded slash/path traversal attempts."""

    raise _id_error("评估")


@router.api_route(
    "/datasets/{unsafe_path:path}",
    methods=["GET", "POST"],
    include_in_schema=False,
)
async def reject_unsafe_dataset_path(unsafe_path: str) -> None:
    """Return the stable ID error for decoded dataset path traversal attempts."""

    raise _id_error("评测集")


def _record_response(record: KnowledgeEvaluationRecord) -> KnowledgeEvaluationResponse:
    payload = record.model_dump(mode="json", exclude={"execution_token"})
    payload.pop("dataset_id")
    payload.pop("dataset_label")
    payload.pop("dataset_checksum")
    payload["dataset"] = {
        "dataset_id": record.dataset_id,
        "display_name": record.dataset_label,
        "checksum": record.dataset_checksum,
    }
    payload["poll_url"] = (
        "/api/agent-evaluations/knowledge-extraction/evaluations/"
        f"{record.evaluation_id}"
    )
    return KnowledgeEvaluationResponse.model_validate(_round_floats(payload))


def _comparison_response(
    comparison: EvaluationComparison,
) -> KnowledgeEvaluationComparison:
    expected_name = (comparison.expected_card or {}).get("name")
    actual_name = (comparison.actual_card or {}).get("name")
    display_title = next(
        (
            value
            for value in (
                expected_name,
                actual_name,
                comparison.expected_card_id,
                comparison.actual_candidate_id,
            )
            if isinstance(value, str) and value
        ),
        "未命名知识卡",
    )
    payload = {
        "comparison_id": "::".join(
            (
                comparison.run_id,
                comparison.expected_card_id or "none",
                comparison.actual_candidate_id or "none",
                comparison.issue_type,
            )
        ),
        "run_id": comparison.run_id,
        "case_id": comparison.case_id,
        "task_title": comparison.task_title or "未命名章节",
        "knowledge_type": comparison.knowledge_type,
        "issue_type": comparison.issue_type,
        "display_title": display_title,
        "expected_card_id": comparison.expected_card_id,
        "actual_review_item_id": comparison.actual_candidate_id,
        "expected_card": comparison.expected_card,
        "actual_card": comparison.actual_card,
        "match_basis": comparison.match_kind,
        "field_diffs": comparison.field_diffs,
        "judge_result": comparison.judge_result,
        "explanation": (
            comparison.explanation.model_dump(mode="json")
            if comparison.explanation
            else None
        ),
    }
    return KnowledgeEvaluationComparison.model_validate(_round_floats(payload))


def _round_floats(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, list):
        return [_round_floats(item) for item in value]
    if isinstance(value, tuple):
        return [_round_floats(item) for item in value]
    if isinstance(value, dict):
        return {key: _round_floats(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return _round_floats(value.model_dump(mode="json"))
    return value


def _validate_request_ids(request: CreateKnowledgeEvaluationRequest) -> None:
    _validate_id(request.dataset_id, _DATASET_ID_PATTERN, "评测集")
    for run_id in request.run_ids:
        _validate_id(run_id, _RUN_ID_PATTERN, "历史任务")


def _validate_id(value: str, pattern: re.Pattern[str], label: str) -> None:
    if not pattern.fullmatch(value):
        raise _id_error(label)


def _id_error(label: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "error": {
                "code": "EVALUATION_ID_INVALID",
                "message": f"{label}标识格式不正确。",
            }
        },
    )


def _http_error(error: Exception) -> HTTPException:
    code = getattr(error, "code", "EVALUATION_DATASET_INVALID")
    message = str(error).strip() or "评估请求处理失败，请检查后再试。"
    return HTTPException(
        status_code=_HTTP_STATUS_BY_CODE.get(code, 422),
        detail={"error": {"code": code, "message": message}},
    )
