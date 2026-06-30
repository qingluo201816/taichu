"""Creative inbox endpoints."""

from pydantic import ValidationError
from fastapi import APIRouter, Depends, HTTPException, Query

from taichu.api.deps import provide_inbox_service, provide_mvp_inbox_service
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
from taichu.api.schemas.mvp import (
    ConfirmPendingFactRequest,
    ConfirmPendingFactResponse,
    CreateInboxItemRequest,
    MVPInboxIdeaResponse,
    MVPInboxIssueResponse,
    MVPInboxListResponse,
    MVPInboxPendingFactResponse,
    PatchInboxItemRequest,
)
from taichu.application.services.ai_card_service import (
    AICardNotFoundError,
    InvalidCardActionError,
)
from taichu.application.services.inbox_service import (
    InboxService,
    PendingFactNotFoundError,
)
from taichu.application.services.mvp_inbox_service import (
    InboxItemNotFoundError,
    InboxValidationError,
    MVPInboxService,
)
from taichu.domain.exceptions import InvalidStateTransitionError
from taichu.domain.models.ai_card import AIResultCard
from taichu.domain.models.inbox import ChapterIssue, IdeaCard
from taichu.domain.models import StructuredKnowledgeType
from taichu.domain.models.pending_fact import PendingFact

router = APIRouter(prefix="/api")


@router.get("/inbox")
async def api_read_inbox(
    service: InboxService = Depends(provide_inbox_service),
    mvp_service: MVPInboxService = Depends(provide_mvp_inbox_service),
    tab: str | None = Query(default=None),
) -> InboxResponse | MVPInboxListResponse:
    """Return the legacy inbox snapshot or one MVP Inbox tab."""
    if tab is not None:
        try:
            return MVPInboxListResponse(items=await mvp_service.list_items(tab))
        except InboxValidationError as error:
            raise _bad_request(str(error)) from error
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


@router.get("/inbox/pending-facts", response_model=MVPInboxListResponse)
async def api_list_mvp_pending_facts(
    service: MVPInboxService = Depends(provide_mvp_inbox_service),
) -> MVPInboxListResponse:
    """List manual pending facts."""
    return MVPInboxListResponse(
        items=await service.list_items("pending-facts")
    )


@router.post("/inbox/ideas", response_model=MVPInboxIdeaResponse)
async def api_create_mvp_idea(
    request: CreateInboxItemRequest,
    service: MVPInboxService = Depends(provide_mvp_inbox_service),
) -> MVPInboxIdeaResponse:
    """Create a manual inspiration item."""
    try:
        item = await service.create_idea(request.data)
    except ValidationError as error:
        raise _bad_request(_validation_message(error)) from error
    return MVPInboxIdeaResponse(item=item)


@router.patch("/inbox/ideas/{item_id}", response_model=MVPInboxIdeaResponse)
async def api_patch_mvp_idea(
    item_id: str,
    request: PatchInboxItemRequest,
    service: MVPInboxService = Depends(provide_mvp_inbox_service),
) -> MVPInboxIdeaResponse:
    """Patch a manual inspiration item."""
    try:
        item = await service.patch_idea(item_id, request.updates)
    except InboxItemNotFoundError as error:
        raise _not_found(str(error)) from error
    except ValidationError as error:
        raise _bad_request(_validation_message(error)) from error
    return MVPInboxIdeaResponse(item=item)


@router.post("/inbox/pending-facts", response_model=MVPInboxPendingFactResponse)
async def api_create_mvp_pending_fact(
    request: CreateInboxItemRequest,
    service: MVPInboxService = Depends(provide_mvp_inbox_service),
) -> MVPInboxPendingFactResponse:
    """Create a manual pending fact."""
    try:
        item = await service.create_pending_fact(request.data)
    except ValidationError as error:
        raise _bad_request(_validation_message(error)) from error
    return MVPInboxPendingFactResponse(item=item)


@router.patch(
    "/inbox/pending-facts/{item_id}",
    response_model=MVPInboxPendingFactResponse,
)
async def api_patch_mvp_pending_fact(
    item_id: str,
    request: PatchInboxItemRequest,
    service: MVPInboxService = Depends(provide_mvp_inbox_service),
) -> MVPInboxPendingFactResponse:
    """Patch a manual pending fact."""
    try:
        item = await service.patch_pending_fact(item_id, request.updates)
    except InboxItemNotFoundError as error:
        raise _not_found(str(error)) from error
    except ValidationError as error:
        raise _bad_request(_validation_message(error)) from error
    return MVPInboxPendingFactResponse(item=item)


@router.post(
    "/inbox/pending-facts/{item_id}/confirm",
    response_model=ConfirmPendingFactResponse,
)
async def api_confirm_mvp_pending_fact(
    item_id: str,
    request: ConfirmPendingFactRequest,
    service: MVPInboxService = Depends(provide_mvp_inbox_service),
) -> ConfirmPendingFactResponse:
    """Confirm a manual pending fact into a draft knowledge card."""
    try:
        result = await service.confirm_pending_fact(
            item_id,
            _knowledge_type(request.knowledge_type),
            request.card_preview,
        )
    except InboxItemNotFoundError as error:
        raise _not_found(str(error)) from error
    except (ValidationError, ValueError) as error:
        raise _bad_request(_validation_message(error)) from error
    return ConfirmPendingFactResponse(
        pending_fact=result.pending_fact,
        knowledge_card=result.knowledge_card,
    )


@router.get("/inbox/issues", response_model=MVPInboxListResponse)
async def api_list_mvp_issues(
    service: MVPInboxService = Depends(provide_mvp_inbox_service),
) -> MVPInboxListResponse:
    """List manual issue items."""
    return MVPInboxListResponse(items=await service.list_items("issues"))


@router.post("/inbox/issues", response_model=MVPInboxIssueResponse)
async def api_create_mvp_issue(
    request: CreateInboxItemRequest,
    service: MVPInboxService = Depends(provide_mvp_inbox_service),
) -> MVPInboxIssueResponse:
    """Create a manual issue item."""
    try:
        item = await service.create_issue(request.data)
    except ValidationError as error:
        raise _bad_request(_validation_message(error)) from error
    return MVPInboxIssueResponse(item=item)


@router.patch("/inbox/issues/{item_id}", response_model=MVPInboxIssueResponse)
async def api_patch_mvp_issue(
    item_id: str,
    request: PatchInboxItemRequest,
    service: MVPInboxService = Depends(provide_mvp_inbox_service),
) -> MVPInboxIssueResponse:
    """Patch a manual issue item."""
    try:
        item = await service.patch_issue(item_id, request.updates)
    except InboxItemNotFoundError as error:
        raise _not_found(str(error)) from error
    except ValidationError as error:
        raise _bad_request(_validation_message(error)) from error
    return MVPInboxIssueResponse(item=item)


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


def _knowledge_type(value: str) -> StructuredKnowledgeType:
    try:
        return StructuredKnowledgeType(value)
    except ValueError as error:
        raise ValueError("未知的知识卡类型") from error


def _validation_message(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "Inbox 内容不完整或格式不正确，请检查后再保存。"
    message = str(error)
    return message if message else "Inbox 内容不完整或格式不正确，请检查后再保存。"


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
