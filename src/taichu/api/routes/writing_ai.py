"""写作页 AI 普通与流式运行接口。"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from taichu.api.deps import provide_chapter_service, provide_writing_ai_service
from taichu.api.schemas.writing_ai import (
    CreateWritingAIRunRequest,
    WritingAIRunListResponse,
)
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.writing_ai_service import (
    WritingAICreateRunCommand,
    WritingAIListFilters,
    WritingAIRunNotFoundError,
    WritingAIService,
)
from taichu.domain.models import (
    WritingAIButtonType,
    WritingAIRun,
    WritingAIRunStatus,
)

router = APIRouter(prefix="/api")


@router.post("/writing-ai/runs", response_model=WritingAIRun)
async def api_create_writing_ai_run(
    request: CreateWritingAIRunRequest,
    service: WritingAIService = Depends(provide_writing_ai_service),
) -> WritingAIRun:
    """Create one writing AI run through the unified real LLM workflow."""
    try:
        return await service.create_run(
            WritingAICreateRunCommand(
                button_type=request.button_type,
                chapter_id=request.chapter_id,
                reference_scope=request.reference_scope,
                user_input=request.user_input,
                selected_text=request.selected_text,
                selection_range=request.selection_range,
                target_words=request.target_words,
                draft_chapter_text=request.draft_chapter_text,
                model_id=request.model_id,
            )
        )
    except ValueError as error:
        raise _bad_request(str(error)) from error


@router.post("/writing-ai/runs/stream")
async def api_stream_writing_ai_run(
    payload: CreateWritingAIRunRequest,
    http_request: Request,
    service: WritingAIService = Depends(provide_writing_ai_service),
) -> StreamingResponse:
    """以 NDJSON 输出真实模型增量，同时保存最终完整运行记录。"""
    command = WritingAICreateRunCommand(
        button_type=payload.button_type,
        chapter_id=payload.chapter_id,
        reference_scope=payload.reference_scope,
        user_input=payload.user_input,
        selected_text=payload.selected_text,
        selection_range=payload.selection_range,
        target_words=payload.target_words,
        draft_chapter_text=payload.draft_chapter_text,
        model_id=payload.model_id,
    )

    async def event_lines():
        async for event in service.stream_run(command):
            if await http_request.is_disconnected():
                break
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(
        event_lines(), media_type="application/x-ndjson; charset=utf-8"
    )


@router.get("/writing-ai/runs", response_model=WritingAIRunListResponse)
async def api_list_writing_ai_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    chapter_id: str | None = Query(default=None),
    chapter_name: str | None = Query(default=None),
    button_type: WritingAIButtonType | None = Query(default=None),
    status: WritingAIRunStatus | None = Query(default=None),
    service: WritingAIService = Depends(provide_writing_ai_service),
    chapter_service: ChapterService = Depends(provide_chapter_service),
) -> WritingAIRunListResponse:
    """List writing AI runs for the AI history page and editor picker."""
    filters = WritingAIListFilters(
        chapter_id=chapter_id,
        button_type=button_type,
        status=status,
    )
    if chapter_name and chapter_name.strip():
        all_runs, _ = await service.list_runs(
            filters=filters,
            page=1,
            page_size=100_000,
        )
        filtered_runs = await _filter_by_chapter_name(
            all_runs,
            chapter_name.strip(),
            chapter_service,
        )
        total = len(filtered_runs)
        runs = _paginate(filtered_runs, page, page_size)
    else:
        runs, total = await service.list_runs(
            filters=filters,
            page=page,
            page_size=page_size,
        )
    return WritingAIRunListResponse(
        runs=runs,
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/writing-ai/runs/{run_id}", response_model=WritingAIRun)
async def api_get_writing_ai_run(
    run_id: str,
    service: WritingAIService = Depends(provide_writing_ai_service),
) -> WritingAIRun:
    """Read one saved writing AI run trace."""
    try:
        return await service.get_run(run_id)
    except WritingAIRunNotFoundError as error:
        raise _not_found(str(error)) from error


@router.post("/writing-ai/runs/{run_id}/replay", response_model=WritingAIRun)
async def api_replay_writing_ai_run(
    run_id: str,
    service: WritingAIService = Depends(provide_writing_ai_service),
) -> WritingAIRun:
    """Replay a run by returning saved trace without calling the LLM."""
    try:
        return await service.replay_run(run_id)
    except WritingAIRunNotFoundError as error:
        raise _not_found(str(error)) from error


async def _filter_by_chapter_name(
    runs: list[WritingAIRun],
    chapter_name: str,
    chapter_service: ChapterService,
) -> list[WritingAIRun]:
    chapters = await chapter_service.list_chapters()
    matched_ids = {
        chapter.id for chapter in chapters if chapter_name in chapter.title
    }
    return [run for run in runs if run.chapter_id in matched_ids]


def _paginate(runs: list[WritingAIRun], page: int, page_size: int) -> list[WritingAIRun]:
    start = (page - 1) * page_size
    return runs[start : start + page_size]


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
