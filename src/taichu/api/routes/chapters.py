"""Chapter endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from taichu.api.deps import (
    provide_chapter_service,
    provide_chapter_summary_service,
)
from taichu.api.schemas.ai_cards import AIResultCardInfo
from taichu.api.schemas.chapters import (
    ChapterInfo,
    ChapterListResponse,
    ChapterReadResponse,
    ChapterSaveRequest,
    ChapterSummaryAction,
    ChapterSummaryActionRequest,
    ChapterSummaryInfo,
    ChapterSummaryListResponse,
    ChapterSummaryResponse,
    ChapterSummaryRunResponse,
    PendingFactInfo,
    PendingFactResponse,
)
from taichu.application.services.chapter_summary_service import (
    ChapterSummaryEdit,
    ChapterSummaryNotFoundError,
    ChapterSummaryService,
    SummaryCandidateNotFoundError,
)
from taichu.application.services.chapter_service import (
    ChapterNotFoundError,
    ChapterService,
)
from taichu.domain.models.ai_card import AIResultCard
from taichu.domain.models.chapter import Chapter
from taichu.domain.models.pending_fact import PendingFact
from taichu.domain.models.summary import ChapterSummary

router = APIRouter(prefix="/api")


@router.get("/chapters", response_model=ChapterListResponse)
async def api_list_chapters(
    service: ChapterService = Depends(provide_chapter_service),
) -> ChapterListResponse:
    """List manuscript chapters from the active source manifest."""
    chapters = await service.list_chapters()
    return ChapterListResponse(
        chapters=[_chapter_info(chapter) for chapter in chapters]
    )


@router.get(
    "/chapters/{chapter_id}",
    response_model=ChapterReadResponse,
)
async def api_read_chapter(
    chapter_id: str,
    service: ChapterService = Depends(provide_chapter_service),
) -> ChapterReadResponse:
    """Read a manuscript chapter by id."""
    try:
        content = await service.read_chapter(chapter_id)
    except ChapterNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return ChapterReadResponse(
        chapter=_chapter_info(content.chapter),
        markdown=content.markdown,
    )


@router.put(
    "/chapters/{chapter_id}",
    response_model=ChapterReadResponse,
)
async def api_save_chapter(
    chapter_id: str,
    request: ChapterSaveRequest,
    service: ChapterService = Depends(provide_chapter_service),
) -> ChapterReadResponse:
    """Persist Markdown for an existing manuscript chapter."""
    try:
        content = await service.save_chapter(chapter_id, request.markdown)
    except ChapterNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return ChapterReadResponse(
        chapter=_chapter_info(content.chapter),
        markdown=content.markdown,
    )


@router.post(
    "/chapters/{chapter_id}/summary",
    response_model=ChapterSummaryRunResponse,
)
async def api_summarize_chapter(
    chapter_id: str,
    service: ChapterSummaryService = Depends(provide_chapter_summary_service),
) -> ChapterSummaryRunResponse:
    """Run chapter summary workflow and persist a summary card."""
    try:
        result = await service.summarize_chapter(chapter_id)
    except ChapterNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return ChapterSummaryRunResponse(
        summary=_summary_info(result.summary),
        card=_card_info(result.card),
    )


@router.get(
    "/chapters/{chapter_id}/summaries",
    response_model=ChapterSummaryListResponse,
)
async def api_list_chapter_summaries(
    chapter_id: str,
    service: ChapterSummaryService = Depends(provide_chapter_summary_service),
) -> ChapterSummaryListResponse:
    """List workspace chapter summaries for one chapter."""
    summaries = await service.list_summaries(chapter_id=chapter_id)
    return ChapterSummaryListResponse(
        summaries=[_summary_info(summary) for summary in summaries]
    )


@router.post(
    "/chapter-summaries/{summary_id}/actions",
    response_model=ChapterSummaryResponse,
)
async def api_apply_summary_action(
    summary_id: str,
    request: ChapterSummaryActionRequest,
    service: ChapterSummaryService = Depends(provide_chapter_summary_service),
) -> ChapterSummaryResponse:
    """Confirm or ignore one chapter summary draft."""
    try:
        if request.action is ChapterSummaryAction.CONFIRM:
            summary = await service.confirm_summary(
                summary_id,
                _summary_edit(request.edits),
            )
        else:
            summary = await service.ignore_summary(summary_id)
    except ChapterSummaryNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return ChapterSummaryResponse(summary=_summary_info(summary))


@router.post(
    "/chapter-summaries/{summary_id}/pending-facts/{pending_fact_id}",
    response_model=PendingFactResponse,
)
async def api_convert_summary_candidate(
    summary_id: str,
    pending_fact_id: str,
    service: ChapterSummaryService = Depends(provide_chapter_summary_service),
) -> PendingFactResponse:
    """Persist a summary setting candidate as a non-fact PendingFact."""
    try:
        pending_fact = await service.convert_candidate_to_pending_fact(
            summary_id,
            pending_fact_id,
        )
    except (ChapterSummaryNotFoundError, SummaryCandidateNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return PendingFactResponse(pending_fact=_pending_fact_info(pending_fact))


def _chapter_info(chapter: Chapter) -> ChapterInfo:
    return ChapterInfo(
        id=chapter.id,
        volume_id=chapter.volume_id,
        title=chapter.title,
        order=chapter.order,
        markdown_path=chapter.markdown_path,
        status=chapter.status.value,
        word_count=chapter.word_count,
        created_at=chapter.created_at,
        updated_at=chapter.updated_at,
    )


def _summary_info(summary: ChapterSummary) -> ChapterSummaryInfo:
    return ChapterSummaryInfo(
        id=summary.id,
        chapter_id=summary.chapter_id,
        status=summary.status.value,
        summary=summary.summary,
        key_events=summary.key_events,
        character_changes=summary.character_changes,
        new_setting_candidates=[
            _pending_fact_info(candidate)
            for candidate in summary.new_setting_candidates
        ],
        foreshadow_candidates=summary.foreshadow_candidates,
        next_chapter_hooks=summary.next_chapter_hooks,
        source_refs=summary.source_refs,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
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


def _summary_edit(
    edits: object,
) -> ChapterSummaryEdit | None:
    if edits is None:
        return None
    return ChapterSummaryEdit(
        summary=getattr(edits, "summary"),
        key_events=getattr(edits, "key_events"),
        character_changes=getattr(edits, "character_changes"),
        foreshadow_candidates=getattr(edits, "foreshadow_candidates"),
        next_chapter_hooks=getattr(edits, "next_chapter_hooks"),
    )
