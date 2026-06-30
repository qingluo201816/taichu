"""MVP structured knowledge endpoints."""

from pydantic import ValidationError
from fastapi import APIRouter, Depends, HTTPException, Query

from taichu.api.deps import provide_mvp_knowledge_service
from taichu.api.schemas.mvp import (
    CreateKnowledgeCardRequest,
    KnowledgeCardListResponse,
    KnowledgeCardResponse,
    KnowledgeTypeInfo,
    KnowledgeTypesResponse,
    PatchKnowledgeCardRequest,
)
from taichu.application.services.mvp_knowledge_service import (
    KnowledgeCardNotFoundError,
    KnowledgeCardValidationError,
    MVPKnowledgeService,
)
from taichu.domain.models import StructuredKnowledgeType

router = APIRouter(prefix="/api")

KNOWLEDGE_TYPE_LABELS: dict[str, str] = {
    "character": "角色",
    "realm": "境界",
    "technique": "功法",
    "location": "地点",
    "faction": "势力",
    "item": "物品",
    "rule": "规则",
    "event": "事件",
    "foreshadow": "伏笔",
}


@router.get("/knowledge/types", response_model=KnowledgeTypesResponse)
async def api_list_knowledge_types(
    service: MVPKnowledgeService = Depends(provide_mvp_knowledge_service),
) -> KnowledgeTypesResponse:
    """Return structured knowledge types with Chinese labels."""
    return KnowledgeTypesResponse(
        types=[
            KnowledgeTypeInfo(value=item.value, label=KNOWLEDGE_TYPE_LABELS[item.value])
            for item in service.list_types()
        ]
    )


@router.get("/knowledge/cards", response_model=KnowledgeCardListResponse)
async def api_list_knowledge_cards(
    type: str = Query(...),
    status: str = "all",
    q: str | None = None,
    service: MVPKnowledgeService = Depends(provide_mvp_knowledge_service),
) -> KnowledgeCardListResponse:
    """List cards for one structured knowledge type."""
    try:
        cards = await service.list_cards(_knowledge_type(type), status=status, q=q)
    except ValueError as error:
        raise _bad_request(str(error) or "知识库筛选条件不正确") from error
    return KnowledgeCardListResponse(cards=cards)


@router.post("/knowledge/cards", response_model=KnowledgeCardResponse)
async def api_create_knowledge_card(
    request: CreateKnowledgeCardRequest,
    service: MVPKnowledgeService = Depends(provide_mvp_knowledge_service),
) -> KnowledgeCardResponse:
    """Create one structured knowledge card."""
    try:
        card = await service.create_card(
            _knowledge_type(request.type),
            request.data,
        )
    except (ValidationError, ValueError) as error:
        raise _bad_request(_validation_message(error)) from error
    return KnowledgeCardResponse(card=card)


@router.get("/knowledge/cards/{card_id}", response_model=KnowledgeCardResponse)
async def api_get_knowledge_card(
    card_id: str,
    service: MVPKnowledgeService = Depends(provide_mvp_knowledge_service),
) -> KnowledgeCardResponse:
    """Read one structured knowledge card."""
    try:
        card = await service.get_card(card_id)
    except KnowledgeCardNotFoundError as error:
        raise _not_found(str(error)) from error
    return KnowledgeCardResponse(card=card)


@router.patch("/knowledge/cards/{card_id}", response_model=KnowledgeCardResponse)
async def api_patch_knowledge_card(
    card_id: str,
    request: PatchKnowledgeCardRequest,
    service: MVPKnowledgeService = Depends(provide_mvp_knowledge_service),
) -> KnowledgeCardResponse:
    """Patch one structured knowledge card."""
    try:
        card = await service.patch_card(card_id, request.updates)
    except KnowledgeCardNotFoundError as error:
        raise _not_found(str(error)) from error
    except (ValidationError, ValueError) as error:
        raise _bad_request(_validation_message(error)) from error
    return KnowledgeCardResponse(card=card)


@router.post(
    "/knowledge/cards/{card_id}/mark-active",
    response_model=KnowledgeCardResponse,
)
async def api_mark_knowledge_card_active(
    card_id: str,
    service: MVPKnowledgeService = Depends(provide_mvp_knowledge_service),
) -> KnowledgeCardResponse:
    """Mark one complete card as effective knowledge."""
    try:
        card = await service.mark_active(card_id)
    except KnowledgeCardNotFoundError as error:
        raise _not_found(str(error)) from error
    except KnowledgeCardValidationError as error:
        raise _bad_request(str(error)) from error
    return KnowledgeCardResponse(card=card)


@router.post(
    "/knowledge/cards/{card_id}/mark-deprecated",
    response_model=KnowledgeCardResponse,
)
async def api_mark_knowledge_card_deprecated(
    card_id: str,
    service: MVPKnowledgeService = Depends(provide_mvp_knowledge_service),
) -> KnowledgeCardResponse:
    """Mark one card as deprecated without physical deletion."""
    try:
        card = await service.mark_deprecated(card_id)
    except KnowledgeCardNotFoundError as error:
        raise _not_found(str(error)) from error
    return KnowledgeCardResponse(card=card)


def _knowledge_type(value: str) -> StructuredKnowledgeType:
    try:
        return StructuredKnowledgeType(value)
    except ValueError as error:
        raise ValueError("未知的知识卡类型") from error


def _validation_message(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "知识卡内容不完整或格式不正确，请检查后再保存。"
    message = str(error)
    return message if message else "知识卡内容不完整或格式不正确，请检查后再保存。"


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
