"""Knowledge and PendingFact confirmation endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from taichu.api.deps import (
    provide_knowledge_service,
    provide_pending_fact_confirmation_service,
)
from taichu.api.schemas.knowledge import (
    ConfirmEditedPendingFactRequest,
    KnowledgeCardInfo,
    KnowledgeListResponse,
    PendingFactConfirmationResponse,
    PendingFactInfo,
    PendingFactRejectionResponse,
)
from taichu.application.services.knowledge_service import (
    KnowledgeIdentityConflictError,
    KnowledgeService,
    KnowledgeWriteError,
)
from taichu.application.services.pending_fact_confirmation_service import (
    PendingFactConfirmationEdits,
    PendingFactConfirmationError,
    PendingFactConfirmationService,
    PendingFactNotFoundError,
    UnsupportedPendingFactTypeError,
)
from taichu.domain.exceptions import InvalidStateTransitionError
from taichu.domain.models.knowledge import KnowledgeCard
from taichu.domain.models.pending_fact import PendingFact

router = APIRouter(prefix="/api")


@router.get("/knowledge", response_model=KnowledgeListResponse)
async def api_list_knowledge(
    service: KnowledgeService = Depends(provide_knowledge_service),
) -> KnowledgeListResponse:
    """List author-confirmed KnowledgeCards."""
    cards = await service.list_cards()
    return KnowledgeListResponse(cards=[_knowledge_info(card) for card in cards])


@router.post(
    "/pending-facts/{pending_fact_id}/confirm",
    response_model=PendingFactConfirmationResponse,
)
async def api_confirm_pending_fact(
    pending_fact_id: str,
    service: PendingFactConfirmationService = Depends(
        provide_pending_fact_confirmation_service
    ),
) -> PendingFactConfirmationResponse:
    """Confirm a PendingFact into a confirmed KnowledgeCard."""
    try:
        result = await service.confirm_pending_fact(pending_fact_id)
    except PendingFactNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except KnowledgeIdentityConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (
        KnowledgeWriteError,
        PendingFactConfirmationError,
        UnsupportedPendingFactTypeError,
    ) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except InvalidStateTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return PendingFactConfirmationResponse(
        pending_fact=_pending_fact_info(result.pending_fact),
        knowledge_card=_knowledge_info(result.knowledge_card),
        created=result.created,
    )


@router.post(
    "/pending-facts/{pending_fact_id}/confirm-edited",
    response_model=PendingFactConfirmationResponse,
)
async def api_confirm_pending_fact_with_edits(
    pending_fact_id: str,
    request: ConfirmEditedPendingFactRequest,
    service: PendingFactConfirmationService = Depends(
        provide_pending_fact_confirmation_service
    ),
) -> PendingFactConfirmationResponse:
    """Confirm a PendingFact after explicit author edits."""
    try:
        result = await service.confirm_pending_fact_with_edits(
            pending_fact_id,
            PendingFactConfirmationEdits(
                name=request.name,
                summary=request.summary,
                aliases=request.aliases,
                fields=request.fields,
            ),
        )
    except PendingFactNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except KnowledgeIdentityConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (
        KnowledgeWriteError,
        PendingFactConfirmationError,
        UnsupportedPendingFactTypeError,
    ) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except InvalidStateTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return PendingFactConfirmationResponse(
        pending_fact=_pending_fact_info(result.pending_fact),
        knowledge_card=_knowledge_info(result.knowledge_card),
        created=result.created,
    )


@router.post(
    "/pending-facts/{pending_fact_id}/reject",
    response_model=PendingFactRejectionResponse,
)
async def api_reject_pending_fact(
    pending_fact_id: str,
    service: PendingFactConfirmationService = Depends(
        provide_pending_fact_confirmation_service
    ),
) -> PendingFactRejectionResponse:
    """Reject a PendingFact without writing Knowledge."""
    try:
        result = await service.reject_pending_fact(pending_fact_id)
    except PendingFactNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidStateTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return PendingFactRejectionResponse(
        pending_fact=_pending_fact_info(result.pending_fact)
    )


def _knowledge_info(card: KnowledgeCard) -> KnowledgeCardInfo:
    return KnowledgeCardInfo(
        id=card.id,
        type=card.type.value,
        name=card.name,
        aliases=card.aliases,
        summary=card.summary,
        fields=card.fields,
        source_refs=card.source_refs,
        status=card.status.value,
        created_at=card.created_at,
        updated_at=card.updated_at,
    )


def _pending_fact_info(pending_fact: PendingFact) -> PendingFactInfo:
    return PendingFactInfo(
        id=pending_fact.id,
        fact_type=pending_fact.fact_type.value,
        title=pending_fact.title,
        content=pending_fact.content,
        proposed_by=pending_fact.proposed_by.value,
        source_refs=pending_fact.source_refs,
        status=pending_fact.status.value,
        target_knowledge_id=pending_fact.target_knowledge_id,
        created_at=pending_fact.created_at,
        confirmed_at=pending_fact.confirmed_at,
    )
