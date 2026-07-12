"""Export endpoint."""

from fastapi import APIRouter, Depends

from taichu.api.deps import provide_export_service
from taichu.api.schemas.export import (
    ExportBundleResponse,
    ExportFileInfo,
)
from taichu.application.services.export_service import ExportService
from taichu.domain.models.export import ExportBundle

router = APIRouter(prefix="/api")


@router.get("/export/bundle", response_model=ExportBundleResponse)
async def api_export_bundle(
    service: ExportService = Depends(provide_export_service),
) -> ExportBundleResponse:
    """Build a readable source asset export bundle."""
    return _bundle_response(await service.build_bundle())


def _bundle_response(bundle: ExportBundle) -> ExportBundleResponse:
    return ExportBundleResponse(
        id=bundle.id,
        schema_version=bundle.schema_version,
        created_at=bundle.created_at,
        files=[
            ExportFileInfo(
                path=file.path,
                media_type=file.media_type,
                content=file.content,
            )
            for file in bundle.files
        ],
    )
