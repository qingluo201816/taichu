"""Export and generated projection maintenance endpoints."""

from fastapi import APIRouter, Depends

from taichu.api.deps import provide_export_service, provide_index_service
from taichu.api.schemas.export import (
    ExportBundleResponse,
    ExportFileInfo,
    IndexBuildJobInfo,
    IndexBuildJobResponse,
)
from taichu.application.services.export_service import ExportService
from taichu.application.services.index_service import IndexService
from taichu.domain.models.export import ExportBundle
from taichu.domain.models.indexing import IndexBuildJob

router = APIRouter(prefix="/api")


@router.get("/export/bundle", response_model=ExportBundleResponse)
async def api_export_bundle(
    service: ExportService = Depends(provide_export_service),
) -> ExportBundleResponse:
    """Build a readable source asset export bundle."""
    return _bundle_response(await service.build_bundle())


@router.post(
    "/generated/rebuild",
    response_model=IndexBuildJobResponse,
)
async def api_rebuild_generated(
    service: IndexService = Depends(provide_index_service),
) -> IndexBuildJobResponse:
    """Clear and rebuild generated retrieval projections from source."""
    return IndexBuildJobResponse(
        job=_job_info(await service.rebuild_generated_projection())
    )


@router.post(
    "/generated/clear",
    response_model=IndexBuildJobResponse,
)
async def api_clear_generated(
    service: IndexService = Depends(provide_index_service),
) -> IndexBuildJobResponse:
    """Clear generated projections without touching source assets."""
    return IndexBuildJobResponse(job=_job_info(await service.clear_generated()))


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


def _job_info(job: IndexBuildJob) -> IndexBuildJobInfo:
    return IndexBuildJobInfo(
        id=job.id,
        action=job.action.value,
        status=job.status.value,
        generated_path=job.generated_path,
        created_at=job.created_at,
        completed_at=job.completed_at,
        message=job.message,
    )
