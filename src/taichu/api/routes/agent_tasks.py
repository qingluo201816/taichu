"""Agent task monitoring endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from taichu.api.deps import (
    provide_agent_task_event_center,
    provide_knowledge_extraction_service,
)
from taichu.api.schemas.agent_workbench import (
    KnowledgeExtractionRunDeleteResponse,
    KnowledgeExtractionRunDetailResponse,
    KnowledgeExtractionRunListResponse,
    KnowledgeExtractionRunSummary,
)
from taichu.application.services.agent_task_event_service import AgentTaskEventCenter
from taichu.application.services.knowledge_extraction_service import (
    KnowledgeExtractionNotFoundError,
    KnowledgeExtractionService,
)
from taichu.application.agents.models.agent_run import AgentRun, AgentRunStatus
from taichu.infrastructure.agent_runs.json_store import AgentRunStoreError

router = APIRouter(prefix="/api/agent-tasks")


@router.get("", response_model=KnowledgeExtractionRunListResponse)
async def api_list_agent_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    status: str = "all",
    service: KnowledgeExtractionService = Depends(
        provide_knowledge_extraction_service
    ),
    event_center: AgentTaskEventCenter = Depends(provide_agent_task_event_center),
) -> KnowledgeExtractionRunListResponse:
    """List active and persisted Agent tasks."""
    persisted, _ = await service.list_runs(page=1, page_size=10_000, status="all")
    active = await event_center.list_active_tasks()
    by_id = {run.run_id: run for run in persisted}
    for run in active:
        persisted_run = by_id.get(run.run_id)
        if persisted_run is not None and persisted_run.status in {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
        }:
            continue
        if run.status not in {AgentRunStatus.COMPLETED, AgentRunStatus.FAILED}:
            by_id[run.run_id] = run
        elif run.run_id not in by_id:
            by_id[run.run_id] = run
    runs = list(by_id.values())
    if status != "all":
        runs = [run for run in runs if run.status.value == status]
    runs = sorted(runs, key=lambda run: run.started_at, reverse=True)
    start = (page - 1) * page_size
    return KnowledgeExtractionRunListResponse(
        runs=[_run_summary(run) for run in runs[start : start + page_size]],
        page=page,
        page_size=page_size,
        total=len(runs),
    )


@router.get("/stream/events")
async def api_stream_agent_task_events(
    event_center: AgentTaskEventCenter = Depends(provide_agent_task_event_center),
) -> StreamingResponse:
    """Stream future Agent task events as NDJSON."""

    async def event_lines():
        async for event in event_center.subscribe():
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(
        event_lines(),
        media_type="application/x-ndjson; charset=utf-8",
    )


@router.get("/{task_id}", response_model=KnowledgeExtractionRunDetailResponse)
async def api_get_agent_task(
    task_id: str,
    service: KnowledgeExtractionService = Depends(
        provide_knowledge_extraction_service
    ),
    event_center: AgentTaskEventCenter = Depends(provide_agent_task_event_center),
) -> KnowledgeExtractionRunDetailResponse:
    """Return one active or persisted Agent task."""
    active = await event_center.get_active_task(task_id)
    try:
        run = await service.get_run(task_id)
    except (KnowledgeExtractionNotFoundError, AgentRunStoreError) as error:
        if active is not None:
            return KnowledgeExtractionRunDetailResponse(run=active)
        raise HTTPException(status_code=404, detail=str(error)) from error
    if run.status in {AgentRunStatus.COMPLETED, AgentRunStatus.FAILED}:
        return KnowledgeExtractionRunDetailResponse(run=run)
    if active is not None and active.status not in {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED,
    }:
        return KnowledgeExtractionRunDetailResponse(run=active)
    return KnowledgeExtractionRunDetailResponse(run=run)


@router.delete("/{task_id}", response_model=KnowledgeExtractionRunDeleteResponse)
async def api_delete_agent_task(
    task_id: str,
    service: KnowledgeExtractionService = Depends(
        provide_knowledge_extraction_service
    ),
    event_center: AgentTaskEventCenter = Depends(provide_agent_task_event_center),
) -> KnowledgeExtractionRunDeleteResponse:
    """Delete one persisted or in-memory Agent task."""
    try:
        await service.delete_run(task_id)
    except (KnowledgeExtractionNotFoundError, AgentRunStoreError):
        deleted_active = await event_center.delete_task(task_id)
        if not deleted_active:
            raise HTTPException(
                status_code=404,
                detail=f"任务记录“{task_id}”不存在。",
            )
    return KnowledgeExtractionRunDeleteResponse(run_id=task_id, deleted=True)


def _run_summary(run: AgentRun) -> KnowledgeExtractionRunSummary:
    return KnowledgeExtractionRunSummary(
        run_id=run.run_id,
        agent_name=run.agent_name,
        status=run.status.value,
        scope_type=run.scope.scope_type,
        chapter_id=run.scope.chapter_id,
        chapter_title=run.scope.chapter_title,
        chapter_ids=run.scope.chapter_ids,
        chapter_titles=run.scope.chapter_titles,
        candidate_count=run.metrics.candidate_total,
        pending_count=run.metrics.pending_count,
        confirmed_count=run.metrics.confirmed_count,
        rejected_count=run.metrics.rejected_count,
        total_chapter_count=run.total_chapter_count,
        completed_chapter_count=run.completed_chapter_count,
        failed_chapter_count=run.failed_chapter_count,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )
