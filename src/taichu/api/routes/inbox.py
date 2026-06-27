"""Creative inbox endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from taichu.api.deps import provide_inbox_service
from taichu.api.schemas.inbox import (
    ChapterIssueInfo,
    ConvertPendingFactResponse,
    IdeaCardInfo,
    InboxResponse,
    PendingFactActionResponse,
    PendingFactInfo,
    SaveIdeaResponse,
    SavedAICardInfo,
)
from taichu.application.services.ai_card_service import (
    AICardNotFoundError,
    InvalidCardActionError,
)
from taichu.application.services.inbox_service import (
    InboxService,
    PendingFactNotFoundError,
)
from taichu.domain.exceptions import InvalidStateTransitionError
from taichu.domain.models.ai_card import AIResultCard
from taichu.domain.models.inbox import ChapterIssue, IdeaCard
from taichu.domain.models.pending_fact import PendingFact

router = APIRouter(prefix="/api")


@router.get("/inbox", response_model=InboxResponse)
async def api_read_inbox(
    service: InboxService = Depends(provide_inbox_service),
) -> InboxResponse:
    """Return the four non-fact creative inbox lanes."""
    snapshot = await service.list_inbox()
    return InboxResponse(
        ideas=[_idea_info(idea) for idea in snapshot.ideas],
        pending_facts=[
            _pending_fact_info(pending_fact)
            for pending_fact in snapshot.pending_facts
        ],
        saved_ai_cards=[
            _saved_ai_card_info(card) for card in snapshot.saved_ai_cards
        ],
        chapter_issues=[
            _chapter_issue_info(issue) for issue in snapshot.chapter_issues
        ],
    )


@router.post(
    "/inbox/cards/{card_id}/save-idea",
    response_model=SaveIdeaResponse,
)
async def api_save_card_as_idea(
    card_id: str,
    service: InboxService = Depends(provide_inbox_service),
) -> SaveIdeaResponse:
    """Save a SuggestionCard into ideas."""
    try:
        result = await service.save_card_as_idea(card_id)
    except AICardNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (InvalidCardActionError, InvalidStateTransitionError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return SaveIdeaResponse(
        idea=_idea_info(result.idea),
        card=_saved_ai_card_info(result.card),
    )


@router.post(
    "/inbox/cards/{card_id}/convert-pending-fact",
    response_model=ConvertPendingFactResponse,
)
async def api_convert_card_to_pending_fact(
    card_id: str,
    service: InboxService = Depends(provide_inbox_service),
) -> ConvertPendingFactResponse:
    """Convert a PendingFactCard into a pending workspace record."""
    try:
        result = await service.convert_card_to_pending_fact(card_id)
    except AICardNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (InvalidCardActionError, InvalidStateTransitionError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ConvertPendingFactResponse(
        pending_fact=_pending_fact_info(result.pending_fact),
        card=_saved_ai_card_info(result.card),
    )


@router.post(
    "/inbox/pending-facts/{pending_fact_id}/ignore",
    response_model=PendingFactActionResponse,
)
async def api_ignore_pending_fact(
    pending_fact_id: str,
    service: InboxService = Depends(provide_inbox_service),
) -> PendingFactActionResponse:
    """Ignore a PendingFact without writing Knowledge."""
    try:
        pending_fact = await service.ignore_pending_fact(pending_fact_id)
    except PendingFactNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidStateTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return PendingFactActionResponse(
        pending_fact=_pending_fact_info(pending_fact)
    )


def _idea_info(idea: IdeaCard) -> IdeaCardInfo:
    return IdeaCardInfo(
        id=idea.id,
        content=idea.content,
        source=idea.source.value,
        linked_chapter_id=idea.linked_chapter_id,
        status=idea.status.value,
        source_card_id=idea.source_card_id,
        tags=idea.tags,
        created_at=idea.created_at,
        updated_at=idea.updated_at,
        source_href=_editor_href(idea.linked_chapter_id),
    )


def _pending_fact_info(pending_fact: PendingFact) -> PendingFactInfo:
    chapter_id = _chapter_id_from_pending_fact(pending_fact)
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
        source_href=_editor_href(chapter_id),
    )


def _saved_ai_card_info(card: AIResultCard) -> SavedAICardInfo:
    return SavedAICardInfo(
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
        source_href=_editor_href(card.chapter_id),
    )


def _chapter_issue_info(issue: ChapterIssue) -> ChapterIssueInfo:
    return ChapterIssueInfo(
        id=issue.id,
        title=issue.title,
        description=issue.description,
        chapter_id=issue.chapter_id,
        status=issue.status.value,
        source=issue.source.value,
        source_card_id=issue.source_card_id,
        source_refs=issue.source_refs,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
        source_href=_editor_href(issue.chapter_id),
    )


def _chapter_id_from_pending_fact(pending_fact: PendingFact) -> str | None:
    for source_ref in pending_fact.source_refs:
        if source_ref.chapter_id:
            return source_ref.chapter_id
    return None


def _editor_href(chapter_id: str | None) -> str | None:
    if not chapter_id:
        return None
    return f"/editor?chapter_id={chapter_id}"
