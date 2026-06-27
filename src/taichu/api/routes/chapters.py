"""Chapter endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from taichu.api.deps import provide_chapter_service
from taichu.api.schemas.chapters import (
    ChapterInfo,
    ChapterListResponse,
    ChapterReadResponse,
    ChapterSaveRequest,
)
from taichu.application.services.chapter_service import (
    ChapterNotFoundError,
    ChapterService,
)
from taichu.domain.models.chapter import Chapter

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
