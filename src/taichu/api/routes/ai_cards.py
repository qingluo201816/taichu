"""AI card endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query

from taichu.api.deps import (
    provide_ai_card_service,
    provide_selection_ai_service,
)
from taichu.api.schemas.ai_cards import (
    AICardAction,
    AICardActionRequest,
    AICardListResponse,
    AICardResponse,
    AIResultCardInfo,
    SelectionAIRequest,
)
from taichu.application.services.ai_card_service import (
    AICardNotFoundError,
    AICardService,
    InvalidCardActionError,
)
from taichu.application.services.selection_ai_service import (
    SelectionAIRequest as ServiceSelectionAIRequest,
)
from taichu.application.services.selection_ai_service import (
    SelectionAIService,
    SelectionMode,
)
from taichu.domain.exceptions import InvalidStateTransitionError
from taichu.domain.models.ai_card import AIResultCard

router = APIRouter(prefix="/api")


@router.get("/ai-cards", response_model=AICardListResponse)
async def api_list_ai_cards(
    chapter_id: str | None = Query(default=None),
    service: AICardService = Depends(provide_ai_card_service),
) -> AICardListResponse:
    """List persisted AI cards for the editor side panel."""
    cards = await service.list_cards(chapter_id=chapter_id)
    return AICardListResponse(cards=[_card_info(card) for card in cards])


@router.post(
    "/ai-cards/selection",
    response_model=AICardResponse,
)
async def api_create_selection_ai_card(
    request: SelectionAIRequest,
    service: SelectionAIService = Depends(provide_selection_ai_service),
) -> AICardResponse:
    """Run Selection AI and persist the resulting AIResultCard."""
    selection_context = request.selection_context
    try:
        card = await service.run_selection(
            ServiceSelectionAIRequest(
                mode=SelectionMode(request.mode.value),
                chapter_id=selection_context.chapter_id,
                selected_text=selection_context.selected_text,
                surrounding_text=selection_context.surrounding_text,
                selection_range=selection_context.selection_range.model_dump(
                    by_alias=True
                ),
                selection_ref=selection_context.source_ref,
                user_prompt=request.user_prompt,
                target_words=request.target_words,
                parent_card_id=request.parent_card_id,
            )
        )
    except (AICardNotFoundError, InvalidStateTransitionError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return AICardResponse(card=_card_info(card))


@router.post(
    "/ai-cards/{card_id}/actions",
    response_model=AICardResponse,
)
async def api_apply_ai_card_action(
    card_id: str,
    request: AICardActionRequest,
    service: AICardService = Depends(provide_ai_card_service),
) -> AICardResponse:
    """Apply a persisted card lifecycle action."""
    try:
        if request.action is AICardAction.INSERTED:
            card = await service.mark_inserted(card_id)
        elif request.action is AICardAction.SAVE_TO_IDEA:
            card = (await service.save_suggestion_as_idea(card_id)).card
        else:
            card = await service.discard_card(card_id)
    except AICardNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (InvalidCardActionError, InvalidStateTransitionError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return AICardResponse(card=_card_info(card))


def _card_info(card: AIResultCard) -> AIResultCardInfo:
    return AIResultCardInfo(
        id=card.id,
        type=card.type.value,
        workflow=card.workflow.value,
        status=card.status.value,
        chapter_id=card.chapter_id,
        input_context=card.input_context,
        content=card.content,
        source_refs=card.source_refs,
        parent_card_id=card.parent_card_id,
        created_at=card.created_at,
        updated_at=card.updated_at,
    )
