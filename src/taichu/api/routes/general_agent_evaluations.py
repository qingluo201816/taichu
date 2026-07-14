"""通用写作助手独立效果评测接口。"""

from fastapi import APIRouter, Depends, HTTPException, Query

from taichu.api.deps import provide_general_agent_evaluation_service
from taichu.api.schemas.general_agent_evaluations import (
    CreateGeneralAgentEvaluationRequest,
    GeneralAgentEvaluationDatasetListResponse,
    GeneralAgentEvaluationDatasetResponse,
    GeneralAgentEvaluationDeleteResponse,
    GeneralAgentEvaluationListResponse,
    GeneralAgentEvaluationResponse,
)
from taichu.application.evaluations.general_agent.service import (
    GeneralAgentEvaluationError,
    GeneralAgentEvaluationService,
)
from taichu.infrastructure.evaluations import GeneralAgentEvaluationStoreError

router = APIRouter(prefix="/api/agent-evaluations/general-agent")


@router.get("/datasets", response_model=GeneralAgentEvaluationDatasetListResponse)
async def list_general_agent_evaluation_datasets(
    service: GeneralAgentEvaluationService = Depends(
        provide_general_agent_evaluation_service
    ),
) -> GeneralAgentEvaluationDatasetListResponse:
    try:
        datasets = await service.list_datasets()
    except GeneralAgentEvaluationStoreError as error:
        raise _unprocessable(str(error)) from error
    return GeneralAgentEvaluationDatasetListResponse(datasets=datasets)


@router.get(
    "/datasets/{dataset_id}",
    response_model=GeneralAgentEvaluationDatasetResponse,
)
async def get_general_agent_evaluation_dataset(
    dataset_id: str,
    service: GeneralAgentEvaluationService = Depends(
        provide_general_agent_evaluation_service
    ),
) -> GeneralAgentEvaluationDatasetResponse:
    try:
        dataset = await service.get_dataset(dataset_id)
    except GeneralAgentEvaluationError as error:
        raise _service_error(error) from error
    except GeneralAgentEvaluationStoreError as error:
        raise _unprocessable(str(error)) from error
    return GeneralAgentEvaluationDatasetResponse(dataset=dataset)


@router.post("/evaluations", response_model=GeneralAgentEvaluationResponse)
async def create_general_agent_evaluation(
    request: CreateGeneralAgentEvaluationRequest,
    service: GeneralAgentEvaluationService = Depends(
        provide_general_agent_evaluation_service
    ),
) -> GeneralAgentEvaluationResponse:
    try:
        record = await service.evaluate(**request.model_dump())
    except GeneralAgentEvaluationError as error:
        raise _service_error(error) from error
    except GeneralAgentEvaluationStoreError as error:
        raise _unprocessable(str(error)) from error
    return GeneralAgentEvaluationResponse(evaluation=record)


@router.get("/evaluations", response_model=GeneralAgentEvaluationListResponse)
async def list_general_agent_evaluations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str = "all",
    service: GeneralAgentEvaluationService = Depends(
        provide_general_agent_evaluation_service
    ),
) -> GeneralAgentEvaluationListResponse:
    try:
        records, total = await service.list_evaluations(
            page=page,
            page_size=page_size,
            status=status,
        )
    except GeneralAgentEvaluationStoreError as error:
        raise _unprocessable(str(error)) from error
    return GeneralAgentEvaluationListResponse(
        evaluations=records,
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/evaluations/{evaluation_id}",
    response_model=GeneralAgentEvaluationResponse,
)
async def get_general_agent_evaluation(
    evaluation_id: str,
    service: GeneralAgentEvaluationService = Depends(
        provide_general_agent_evaluation_service
    ),
) -> GeneralAgentEvaluationResponse:
    try:
        record = await service.get_evaluation(evaluation_id)
    except GeneralAgentEvaluationError as error:
        raise _service_error(error) from error
    except GeneralAgentEvaluationStoreError as error:
        raise _unprocessable(str(error)) from error
    return GeneralAgentEvaluationResponse(evaluation=record)


@router.delete(
    "/evaluations/{evaluation_id}",
    response_model=GeneralAgentEvaluationDeleteResponse,
)
async def delete_general_agent_evaluation(
    evaluation_id: str,
    service: GeneralAgentEvaluationService = Depends(
        provide_general_agent_evaluation_service
    ),
) -> GeneralAgentEvaluationDeleteResponse:
    try:
        deleted = await service.delete_evaluation(evaluation_id)
    except GeneralAgentEvaluationStoreError as error:
        raise _unprocessable(str(error)) from error
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "未找到指定评估。"}},
        )
    return GeneralAgentEvaluationDeleteResponse(
        evaluation_id=evaluation_id,
        deleted=True,
    )


def _service_error(error: GeneralAgentEvaluationError) -> HTTPException:
    status_code = 404 if error.code.endswith("NOT_FOUND") else 422
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": error.code, "message": str(error)}},
    )


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "error": {
                "code": "GENERAL_AGENT_EVALUATION_INVALID",
                "message": message,
            }
        },
    )
