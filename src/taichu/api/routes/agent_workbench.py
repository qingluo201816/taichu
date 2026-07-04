"""Agent workbench endpoints for knowledge extraction."""

from pydantic import ValidationError
from fastapi import APIRouter, Depends, HTTPException, Query

from taichu.api.deps import provide_knowledge_extraction_service
from taichu.api.schemas.agent_workbench import (
    CreateKnowledgeExtractionRunRequest,
    EditConfirmCandidateRequest,
    KnowledgeExtractionCandidateActionResponse,
    KnowledgeExtractionCandidateListResponse,
    KnowledgeExtractionRunCreateResponse,
    KnowledgeExtractionRunDetailResponse,
    KnowledgeExtractionRunListResponse,
    KnowledgeExtractionRunSummary,
)
from taichu.application.services.knowledge_extraction_service import (
    KnowledgeExtractionError,
    KnowledgeExtractionNotFoundError,
    KnowledgeExtractionService,
)
from taichu.infrastructure.agent_runs.json_store import AgentRunStoreError
from taichu.infrastructure.knowledge.json_repository import (
    KnowledgeRepositoryError,
    KnowledgeRepositoryNotFoundError,
)

router = APIRouter(prefix="/api/agent-workbench/knowledge-extraction")


@router.post("/runs", response_model=KnowledgeExtractionRunCreateResponse)
async def api_create_knowledge_extraction_run(
    request: CreateKnowledgeExtractionRunRequest,
    service: KnowledgeExtractionService = Depends(
        provide_knowledge_extraction_service
    ),
) -> KnowledgeExtractionRunCreateResponse:
    """Create one synchronous current-chapter knowledge extraction run."""
    try:
        run = await service.create_run(
            chapter_id=request.chapter_id,
            model_name=request.model_name,
            force=request.force,
        )
    except KnowledgeExtractionError as error:
        raise _bad_request(str(error)) from error
    return KnowledgeExtractionRunCreateResponse(run=_run_summary(run))


@router.get("/runs", response_model=KnowledgeExtractionRunListResponse)
async def api_list_knowledge_extraction_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str = "all",
    service: KnowledgeExtractionService = Depends(
        provide_knowledge_extraction_service
    ),
) -> KnowledgeExtractionRunListResponse:
    """List persisted knowledge extraction runs."""
    try:
        runs, total = await service.list_runs(
            page=page,
            page_size=page_size,
            status=status,
        )
    except (ValueError, AgentRunStoreError) as error:
        raise _bad_request(_validation_message(error)) from error
    return KnowledgeExtractionRunListResponse(
        runs=[_run_summary(run) for run in runs],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/runs/{run_id}", response_model=KnowledgeExtractionRunDetailResponse)
async def api_get_knowledge_extraction_run(
    run_id: str,
    service: KnowledgeExtractionService = Depends(
        provide_knowledge_extraction_service
    ),
) -> KnowledgeExtractionRunDetailResponse:
    """Return one full run detail."""
    try:
        run = await service.get_run(run_id)
    except (KnowledgeExtractionNotFoundError, AgentRunStoreError) as error:
        raise _not_found(str(error)) from error
    return KnowledgeExtractionRunDetailResponse(run=run)


@router.get(
    "/runs/{run_id}/candidates",
    response_model=KnowledgeExtractionCandidateListResponse,
)
async def api_list_knowledge_extraction_candidates(
    run_id: str,
    status: str = "pending",
    action: str = "all",
    service: KnowledgeExtractionService = Depends(
        provide_knowledge_extraction_service
    ),
) -> KnowledgeExtractionCandidateListResponse:
    """List review candidates for one run."""
    try:
        candidates = await service.list_candidates(
            run_id,
            status=status,
            action=action,
        )
    except KnowledgeExtractionNotFoundError as error:
        raise _not_found(str(error)) from error
    except ValueError as error:
        raise _bad_request(_validation_message(error)) from error
    return KnowledgeExtractionCandidateListResponse(candidates=candidates)


@router.post(
    "/candidates/{candidate_id}/confirm",
    response_model=KnowledgeExtractionCandidateActionResponse,
)
async def api_confirm_knowledge_extraction_candidate(
    candidate_id: str,
    service: KnowledgeExtractionService = Depends(
        provide_knowledge_extraction_service
    ),
) -> KnowledgeExtractionCandidateActionResponse:
    """Confirm one create_card or update_card candidate."""
    try:
        run = await service.confirm_candidate(candidate_id)
    except (KnowledgeExtractionNotFoundError, KnowledgeRepositoryNotFoundError) as error:
        raise _not_found(str(error)) from error
    except (KnowledgeExtractionError, KnowledgeRepositoryError) as error:
        raise _bad_request(str(error)) from error
    return KnowledgeExtractionCandidateActionResponse(run=run)


@router.post(
    "/candidates/{candidate_id}/edit-confirm",
    response_model=KnowledgeExtractionCandidateActionResponse,
)
async def api_edit_confirm_knowledge_extraction_candidate(
    candidate_id: str,
    request: EditConfirmCandidateRequest,
    service: KnowledgeExtractionService = Depends(
        provide_knowledge_extraction_service
    ),
) -> KnowledgeExtractionCandidateActionResponse:
    """Confirm one candidate after author edits."""
    try:
        run = await service.edit_confirm_candidate(
            candidate_id,
            card_updates=request.card_updates,
            target_card_id=request.target_card_id,
        )
    except (KnowledgeExtractionNotFoundError, KnowledgeRepositoryNotFoundError) as error:
        raise _not_found(str(error)) from error
    except (KnowledgeExtractionError, KnowledgeRepositoryError, ValidationError) as error:
        raise _bad_request(_validation_message(error)) from error
    return KnowledgeExtractionCandidateActionResponse(run=run)


@router.post(
    "/candidates/{candidate_id}/reject",
    response_model=KnowledgeExtractionCandidateActionResponse,
)
async def api_reject_knowledge_extraction_candidate(
    candidate_id: str,
    service: KnowledgeExtractionService = Depends(
        provide_knowledge_extraction_service
    ),
) -> KnowledgeExtractionCandidateActionResponse:
    """Reject one candidate."""
    try:
        run = await service.reject_candidate(candidate_id)
    except KnowledgeExtractionNotFoundError as error:
        raise _not_found(str(error)) from error
    except KnowledgeExtractionError as error:
        raise _bad_request(str(error)) from error
    return KnowledgeExtractionCandidateActionResponse(run=run)


@router.post(
    "/candidates/{candidate_id}/defer",
    response_model=KnowledgeExtractionCandidateActionResponse,
)
async def api_defer_knowledge_extraction_candidate(
    candidate_id: str,
    service: KnowledgeExtractionService = Depends(
        provide_knowledge_extraction_service
    ),
) -> KnowledgeExtractionCandidateActionResponse:
    """Defer one candidate."""
    try:
        run = await service.defer_candidate(candidate_id)
    except KnowledgeExtractionNotFoundError as error:
        raise _not_found(str(error)) from error
    except KnowledgeExtractionError as error:
        raise _bad_request(str(error)) from error
    return KnowledgeExtractionCandidateActionResponse(run=run)


def _run_summary(run) -> KnowledgeExtractionRunSummary:
    return KnowledgeExtractionRunSummary(
        run_id=run.run_id,
        agent_name=run.agent_name,
        status=run.status.value,
        chapter_id=run.scope.chapter_id,
        chapter_title=run.scope.chapter_title,
        candidate_count=run.metrics.candidate_total,
        pending_count=run.metrics.pending_count,
        confirmed_count=run.metrics.confirmed_count,
        rejected_count=run.metrics.rejected_count,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


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


def _validation_message(error: Exception) -> str:
    message = str(error)
    return message if message else "请求内容不完整或格式不正确，请检查后再试。"
