"""MVP writing outline endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from taichu.api.deps import provide_outline_service
from taichu.api.schemas.mvp import (
    CreateChapterRequest,
    CreateVolumeRequest,
    OutlineResponse,
    RenameChapterRequest,
    RenameVolumeRequest,
)
from taichu.application.services.outline_service import (
    OutlineNotFoundError,
    OutlineService,
)

router = APIRouter(prefix="/api")


@router.get("/outline", response_model=OutlineResponse)
async def api_get_outline(
    service: OutlineService = Depends(provide_outline_service),
) -> OutlineResponse:
    """Return the single-novel volume and chapter outline."""
    return OutlineResponse(outline=await service.get_outline())


@router.post("/outline/volumes", response_model=OutlineResponse)
async def api_create_volume(
    request: CreateVolumeRequest,
    service: OutlineService = Depends(provide_outline_service),
) -> OutlineResponse:
    """Create one volume."""
    return OutlineResponse(outline=await service.create_volume(request.name))


@router.patch("/outline/volumes/{volume_id}", response_model=OutlineResponse)
async def api_rename_volume(
    volume_id: str,
    request: RenameVolumeRequest,
    service: OutlineService = Depends(provide_outline_service),
) -> OutlineResponse:
    """Rename one volume."""
    try:
        outline = await service.rename_volume(volume_id, request.name)
    except OutlineNotFoundError as error:
        raise _not_found(str(error)) from error
    return OutlineResponse(outline=outline)


@router.post("/outline/chapters", response_model=OutlineResponse)
async def api_create_chapter(
    request: CreateChapterRequest,
    service: OutlineService = Depends(provide_outline_service),
) -> OutlineResponse:
    """Create one chapter under a volume."""
    try:
        outline = await service.create_chapter(
            request.volume_id,
            request.display_title,
        )
    except OutlineNotFoundError as error:
        raise _not_found(str(error)) from error
    return OutlineResponse(outline=outline)


@router.patch("/outline/chapters/{chapter_id}", response_model=OutlineResponse)
async def api_rename_chapter(
    chapter_id: str,
    request: RenameChapterRequest,
    service: OutlineService = Depends(provide_outline_service),
) -> OutlineResponse:
    """Rename one chapter."""
    try:
        outline = await service.rename_chapter(chapter_id, request.display_title)
    except OutlineNotFoundError as error:
        raise _not_found(str(error)) from error
    return OutlineResponse(outline=outline)


def _not_found(message: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "NOT_FOUND", "message": message}},
    )
