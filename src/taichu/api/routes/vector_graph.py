"""Milvus Vector Graph RAG 索引同步与状态接口。"""

from fastapi import APIRouter, Depends, HTTPException

from taichu.api.deps import provide_vector_graph_rag_service
from taichu.application.vector_graph import (
    VectorGraphBuildError,
    VectorGraphBuildStartResult,
    VectorGraphIndexStatus,
    VectorGraphRAGService,
)

router = APIRouter(prefix="/api/vector-graph", tags=["向量图谱检索"])


@router.get("/status", response_model=VectorGraphIndexStatus)
async def get_vector_graph_status(
    service: VectorGraphRAGService = Depends(provide_vector_graph_rag_service),
) -> VectorGraphIndexStatus:
    try:
        return await service.status()
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "VECTOR_GRAPH_STATUS_UNAVAILABLE",
                    "message": f"RAG 索引状态读取失败：{str(error)[:500]}",
                }
            },
        ) from error


@router.post(
    "/update",
    response_model=VectorGraphBuildStartResult,
    status_code=202,
)
async def start_vector_graph_update(
    service: VectorGraphRAGService = Depends(provide_vector_graph_rag_service),
) -> VectorGraphBuildStartResult:
    try:
        result = await service.start_update()
    except VectorGraphBuildError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "VECTOR_GRAPH_UPDATE_INVALID",
                    "message": str(error),
                }
            },
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "VECTOR_GRAPH_UPDATE_UNAVAILABLE",
                    "message": f"RAG 索引同步启动失败：{str(error)[:500]}",
                }
            },
        ) from error
    if not result.accepted:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "VECTOR_GRAPH_UPDATE_ALREADY_RUNNING",
                    "message": result.message,
                }
            },
        )
    return result
