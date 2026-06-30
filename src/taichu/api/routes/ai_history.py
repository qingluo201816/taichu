"""MVP AI history endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query

from taichu.api.deps import provide_ai_workspace_service
from taichu.api.schemas.mvp import (
    AIWorkspaceConversationListResponse,
    AIWorkspaceConversationResponse,
)
from taichu.application.services.ai_workspace_service import (
    AIConversationNotFoundError,
    AIHistoryFilters,
    AIWorkspaceService,
)
from taichu.domain.models import AIWorkspaceTaskType

router = APIRouter(prefix="/api")


@router.get("/ai-history", response_model=AIWorkspaceConversationListResponse)
async def api_list_ai_history(
    chapter_id: str | None = Query(default=None),
    task_type: str | None = Query(default=None),
    has_source: bool | None = Query(default=None),
    has_error: bool | None = Query(default=None),
    service: AIWorkspaceService = Depends(provide_ai_workspace_service),
) -> AIWorkspaceConversationListResponse:
    """List saved writing-area AI conversations for the AI history page."""
    try:
        filters = AIHistoryFilters(
            chapter_id=chapter_id or None,
            task_type=_task_type(task_type),
            has_source=has_source,
            has_error=has_error,
        )
    except ValueError as error:
        raise _bad_request(str(error)) from error
    return AIWorkspaceConversationListResponse(
        conversations=await service.list_conversations(filters)
    )


@router.get(
    "/ai-history/{conversation_id}",
    response_model=AIWorkspaceConversationResponse,
)
async def api_get_ai_history_detail(
    conversation_id: str,
    service: AIWorkspaceService = Depends(provide_ai_workspace_service),
) -> AIWorkspaceConversationResponse:
    """Read one AI history record."""
    try:
        conversation = await service.get_conversation(conversation_id)
    except AIConversationNotFoundError as error:
        raise _not_found(str(error)) from error
    return AIWorkspaceConversationResponse(conversation=conversation)


def _task_type(value: str | None) -> AIWorkspaceTaskType | None:
    if not value:
        return None
    try:
        return AIWorkspaceTaskType(value)
    except ValueError as error:
        raise ValueError("未知的 AI 功能入口") from error


def _not_found(message: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "NOT_FOUND", "message": message}},
    )


def _bad_request(message: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"error": {"code": "VALIDATION_ERROR", "message": message}},
    )
