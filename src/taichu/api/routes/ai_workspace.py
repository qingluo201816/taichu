"""MVP writing-area AI conversation endpoints."""

from pydantic import ValidationError
from fastapi import APIRouter, Depends, HTTPException

from taichu.api.deps import provide_ai_workspace_service
from taichu.api.schemas.mvp import (
    AIWorkspaceConversationListResponse,
    AIWorkspaceConversationResponse,
    CreateAIWorkspaceConversationRequest,
    SendAIWorkspaceMessageRequest,
)
from taichu.application.services.ai_workspace_service import (
    AIConversationNotFoundError,
    AIConversationNotPersistedError,
    AIWorkspaceService,
)
from taichu.domain.models import (
    AIReferenceScope,
    AIWorkspaceSubtaskType,
    AIWorkspaceTaskType,
)

router = APIRouter(prefix="/api")


@router.post(
    "/ai-workspace-conversations",
    response_model=AIWorkspaceConversationResponse,
)
async def api_create_ai_workspace_conversation(
    request: CreateAIWorkspaceConversationRequest,
    service: AIWorkspaceService = Depends(provide_ai_workspace_service),
) -> AIWorkspaceConversationResponse:
    """Create one mock writing-area AI conversation."""
    try:
        conversation = await service.create_conversation(
            chapter_id=request.chapter_id,
            task_type=_task_type(request.task_type),
            subtask_type=_subtask_type(request.subtask_type),
            reference_scope=_reference_scope(request.reference_scope),
            model_name=request.model_name,
        )
    except AIConversationNotPersistedError as error:
        raise _bad_request(str(error)) from error
    except ValueError as error:
        raise _bad_request(str(error)) from error
    return AIWorkspaceConversationResponse(conversation=conversation)


@router.post(
    "/ai-workspace-conversations/{conversation_id}/messages",
    response_model=AIWorkspaceConversationResponse,
)
async def api_send_ai_workspace_message(
    conversation_id: str,
    request: SendAIWorkspaceMessageRequest,
    service: AIWorkspaceService = Depends(provide_ai_workspace_service),
) -> AIWorkspaceConversationResponse:
    """Append one user message and one deterministic mock assistant message."""
    try:
        conversation = await service.send_message(
            conversation_id,
            request.user_input,
            request.reference,
        )
    except AIConversationNotFoundError as error:
        raise _not_found(str(error)) from error
    except ValidationError as error:
        raise _bad_request(_validation_message(error)) from error
    return AIWorkspaceConversationResponse(conversation=conversation)


@router.get(
    "/ai-workspace-conversations",
    response_model=AIWorkspaceConversationListResponse,
)
async def api_list_ai_workspace_conversations(
    service: AIWorkspaceService = Depends(provide_ai_workspace_service),
) -> AIWorkspaceConversationListResponse:
    """List saved writing-area AI conversations."""
    return AIWorkspaceConversationListResponse(
        conversations=await service.list_conversations()
    )


@router.get(
    "/ai-workspace-conversations/{conversation_id}",
    response_model=AIWorkspaceConversationResponse,
)
async def api_get_ai_workspace_conversation(
    conversation_id: str,
    service: AIWorkspaceService = Depends(provide_ai_workspace_service),
) -> AIWorkspaceConversationResponse:
    """Read one saved writing-area AI conversation."""
    try:
        conversation = await service.get_conversation(conversation_id)
    except AIConversationNotFoundError as error:
        raise _not_found(str(error)) from error
    return AIWorkspaceConversationResponse(conversation=conversation)


def _task_type(value: str) -> AIWorkspaceTaskType:
    try:
        return AIWorkspaceTaskType(value)
    except ValueError as error:
        raise ValueError("未知的 AI 功能入口") from error


def _subtask_type(value: str | None) -> AIWorkspaceSubtaskType | None:
    if value is None:
        return None
    try:
        return AIWorkspaceSubtaskType(value)
    except ValueError as error:
        raise ValueError("未知的润色子类型") from error


def _reference_scope(value: str) -> AIReferenceScope:
    try:
        return AIReferenceScope(value)
    except ValueError as error:
        raise ValueError("未知的正文参考范围") from error


def _validation_message(error: ValidationError) -> str:
    return "AI 对话内容不完整或格式不正确，请检查后再发送。"


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
