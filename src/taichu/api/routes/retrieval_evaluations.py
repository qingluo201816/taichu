"""统一召回专项评测的只读查看接口。"""

from fastapi import APIRouter, Depends, HTTPException, Query

from taichu.api.deps import provide_retrieval_evaluation_service
from taichu.api.schemas.retrieval_evaluations import (
    RetrievalEvaluationDatasetResponse,
    RetrievalEvaluationListItem,
    RetrievalEvaluationListResponse,
    RetrievalEvaluationResponse,
)
from taichu.application.evaluations.retrieval.service import (
    RetrievalEvaluationError,
    RetrievalEvaluationService,
)
from taichu.infrastructure.evaluations import RetrievalEvaluationStoreError

router = APIRouter(prefix="/api/agent-evaluations/retrieval")


@router.get(
    "/datasets/{dataset_id}",
    response_model=RetrievalEvaluationDatasetResponse,
)
async def get_retrieval_evaluation_dataset(
    dataset_id: str,
    service: RetrievalEvaluationService = Depends(
        provide_retrieval_evaluation_service
    ),
) -> RetrievalEvaluationDatasetResponse:
    try:
        dataset = await service.get_dataset(dataset_id)
    except RetrievalEvaluationError as error:
        raise _service_error(error) from error
    except RetrievalEvaluationStoreError as error:
        raise _unprocessable(str(error)) from error
    return RetrievalEvaluationDatasetResponse(dataset=dataset)


@router.get("/evaluations", response_model=RetrievalEvaluationListResponse)
async def list_retrieval_evaluations(
    limit: int = Query(default=20, ge=1, le=200),
    service: RetrievalEvaluationService = Depends(
        provide_retrieval_evaluation_service
    ),
) -> RetrievalEvaluationListResponse:
    try:
        records = await service.list_evaluations(limit=limit)
    except RetrievalEvaluationStoreError as error:
        raise _unprocessable(str(error)) from error
    return RetrievalEvaluationListResponse(
        evaluations=[RetrievalEvaluationListItem.from_record(item) for item in records]
    )


@router.get(
    "/evaluations/{evaluation_id}",
    response_model=RetrievalEvaluationResponse,
)
async def get_retrieval_evaluation(
    evaluation_id: str,
    service: RetrievalEvaluationService = Depends(
        provide_retrieval_evaluation_service
    ),
) -> RetrievalEvaluationResponse:
    try:
        record = await service.get_evaluation(evaluation_id)
    except RetrievalEvaluationError as error:
        raise _service_error(error) from error
    except RetrievalEvaluationStoreError as error:
        raise _unprocessable(str(error)) from error
    return RetrievalEvaluationResponse(evaluation=record)


def _service_error(error: RetrievalEvaluationError) -> HTTPException:
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
                "code": "RETRIEVAL_EVALUATION_INVALID",
                "message": message,
            }
        },
    )
