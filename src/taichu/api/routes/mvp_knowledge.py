"""Structured knowledge endpoints backed exclusively by MongoDB."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from taichu.api.deps import provide_knowledge_service
from taichu.api.schemas.mvp import (
    CreateKnowledgeCardRequest,
    KnowledgeCardListResponse,
    KnowledgeCardMergeResponse,
    KnowledgeCardResponse,
    KnowledgeSchemaResponse,
    KnowledgeSchemasResponse,
    KnowledgeTypeInfo,
    KnowledgeTypesResponse,
    MergeKnowledgeCardsRequest,
    PatchKnowledgeCardRequest,
)
from taichu.application.services.knowledge_service import (
    KnowledgeCardNotFoundError,
    KnowledgeCardValidationError,
    KnowledgeConcurrentUpdateError,
    KnowledgeIdentityConflictError,
    KnowledgeService,
    KnowledgeUnavailableError,
)
from taichu.domain.models import StructuredKnowledgeType, knowledge_type_label

router = APIRouter(prefix="/api")


@router.get("/knowledge/types", response_model=KnowledgeTypesResponse)
async def api_list_knowledge_types(
    service: KnowledgeService = Depends(provide_knowledge_service),
) -> KnowledgeTypesResponse:
    """Return structured knowledge types with Chinese labels."""
    return KnowledgeTypesResponse(
        types=[
            KnowledgeTypeInfo(value=item.value, label=knowledge_type_label(item))
            for item in service.list_types()
        ]
    )


@router.get("/knowledge/schemas", response_model=KnowledgeSchemasResponse)
async def api_list_knowledge_schemas(
    service: KnowledgeService = Depends(provide_knowledge_service),
) -> KnowledgeSchemasResponse:
    """Return all structured knowledge schemas."""
    return KnowledgeSchemasResponse(schemas=service.list_schemas())


@router.get("/knowledge/schemas/{type}", response_model=KnowledgeSchemaResponse)
async def api_get_knowledge_schema(
    type: str,
    service: KnowledgeService = Depends(provide_knowledge_service),
) -> KnowledgeSchemaResponse:
    """Return one structured knowledge schema."""
    try:
        schema = service.get_schema(_knowledge_type(type))
    except ValueError as error:
        raise _bad_request(str(error) or "未知的知识卡类型") from error
    return KnowledgeSchemaResponse(schema=schema)


@router.get("/knowledge/cards", response_model=KnowledgeCardListResponse)
async def api_list_knowledge_cards(
    type: str = Query(...),
    lifecycle: str = "all",
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    service: KnowledgeService = Depends(provide_knowledge_service),
) -> KnowledgeCardListResponse:
    """List one knowledge type; rejected cards require an explicit filter."""
    try:
        result = await service.list_cards(
            _knowledge_type(type),
            lifecycle=lifecycle,
            q=q,
            page=page,
            page_size=page_size,
        )
    except KnowledgeUnavailableError as error:
        raise _unavailable(str(error)) from error
    except ValueError as error:
        raise _bad_request(str(error) or "知识库筛选条件不正确") from error
    return KnowledgeCardListResponse(
        cards=result.cards,
        page=page,
        page_size=page_size,
        total=result.total,
    )


@router.post("/knowledge/cards", response_model=KnowledgeCardResponse)
async def api_create_knowledge_card(
    request: CreateKnowledgeCardRequest,
    service: KnowledgeService = Depends(provide_knowledge_service),
) -> KnowledgeCardResponse:
    """Create one draft knowledge card."""
    try:
        card = await service.create_card(_knowledge_type(request.type), request.data)
    except KnowledgeUnavailableError as error:
        raise _unavailable(str(error)) from error
    except (ValidationError, ValueError) as error:
        raise _bad_request(_validation_message(error)) from error
    return KnowledgeCardResponse(card=card)


@router.get("/knowledge/cards/{card_id}", response_model=KnowledgeCardResponse)
async def api_get_knowledge_card(
    card_id: str,
    service: KnowledgeService = Depends(provide_knowledge_service),
) -> KnowledgeCardResponse:
    """Read one structured knowledge card."""
    try:
        card = await service.get_card(card_id)
    except KnowledgeCardNotFoundError as error:
        raise _not_found(str(error)) from error
    except KnowledgeUnavailableError as error:
        raise _unavailable(str(error)) from error
    return KnowledgeCardResponse(card=card)


@router.patch("/knowledge/cards/{card_id}", response_model=KnowledgeCardResponse)
async def api_patch_knowledge_card(
    card_id: str,
    request: PatchKnowledgeCardRequest,
    service: KnowledgeService = Depends(provide_knowledge_service),
) -> KnowledgeCardResponse:
    """Patch author-editable fields without changing lifecycle directly."""
    try:
        card = await service.patch_card(card_id, request.updates)
    except KnowledgeCardNotFoundError as error:
        raise _not_found(str(error)) from error
    except (KnowledgeConcurrentUpdateError, KnowledgeIdentityConflictError) as error:
        raise _conflict(str(error)) from error
    except KnowledgeUnavailableError as error:
        raise _unavailable(str(error)) from error
    except (ValidationError, ValueError) as error:
        raise _bad_request(_validation_message(error)) from error
    return KnowledgeCardResponse(card=card)


@router.post(
    "/knowledge/cards/{card_id}/confirm",
    response_model=KnowledgeCardResponse,
)
async def api_confirm_knowledge_card(
    card_id: str,
    service: KnowledgeService = Depends(provide_knowledge_service),
) -> KnowledgeCardResponse:
    """Confirm one complete draft as a structured fact."""
    try:
        card = await service.confirm_card(card_id)
    except KnowledgeCardNotFoundError as error:
        raise _not_found(str(error)) from error
    except (KnowledgeConcurrentUpdateError, KnowledgeIdentityConflictError) as error:
        raise _conflict(str(error)) from error
    except KnowledgeUnavailableError as error:
        raise _unavailable(str(error)) from error
    except KnowledgeCardValidationError as error:
        raise _bad_request(str(error)) from error
    return KnowledgeCardResponse(card=card)


@router.post(
    "/knowledge/cards/{card_id}/reject",
    response_model=KnowledgeCardResponse,
)
async def api_reject_knowledge_card(
    card_id: str,
    service: KnowledgeService = Depends(provide_knowledge_service),
) -> KnowledgeCardResponse:
    """Soft-delete one knowledge card."""
    try:
        card = await service.reject_card(card_id)
    except KnowledgeCardNotFoundError as error:
        raise _not_found(str(error)) from error
    except KnowledgeConcurrentUpdateError as error:
        raise _conflict(str(error)) from error
    except KnowledgeUnavailableError as error:
        raise _unavailable(str(error)) from error
    return KnowledgeCardResponse(card=card)


@router.post(
    "/knowledge/cards/{card_id}/merge",
    response_model=KnowledgeCardMergeResponse,
)
async def api_merge_knowledge_cards(
    card_id: str,
    request: MergeKnowledgeCardsRequest,
    service: KnowledgeService = Depends(provide_knowledge_service),
) -> KnowledgeCardMergeResponse:
    """Keep one confirmed card and retire a duplicate after merging its facts."""
    try:
        primary_card, merged_card = await service.merge_confirmed_cards(
            card_id,
            request.merged_card_id,
        )
    except KnowledgeCardNotFoundError as error:
        raise _not_found(str(error)) from error
    except (KnowledgeConcurrentUpdateError, KnowledgeIdentityConflictError) as error:
        raise _conflict(str(error)) from error
    except KnowledgeUnavailableError as error:
        raise _unavailable(str(error)) from error
    except (ValidationError, ValueError) as error:
        raise _bad_request(_validation_message(error)) from error
    return KnowledgeCardMergeResponse(
        primary_card=primary_card,
        merged_card=merged_card,
    )


def _knowledge_type(value: str) -> StructuredKnowledgeType:
    try:
        return StructuredKnowledgeType(value)
    except ValueError as error:
        raise ValueError("未知的知识卡类型") from error


def _validation_message(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "知识卡内容不完整或格式不正确，请检查后再保存。"
    return str(error) or "知识卡内容不完整或格式不正确，请检查后再保存。"


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


def _not_found(message: str) -> HTTPException:
    return _error(404, "NOT_FOUND", message)


def _bad_request(message: str) -> HTTPException:
    return _error(422, "VALIDATION_ERROR", message)


def _conflict(message: str) -> HTTPException:
    return _error(409, "KNOWLEDGE_CONFLICT", message)


def _unavailable(message: str) -> HTTPException:
    return _error(503, "KNOWLEDGE_UNAVAILABLE", message or "知识库暂时不可用。")
