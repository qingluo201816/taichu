"""Generated projection maintenance contracts."""

from enum import StrEnum

from pydantic import Field

from taichu.domain.models.base import DomainModel


class IndexBuildJobAction(StrEnum):
    """Supported generated projection maintenance actions."""

    CLEAR = "clear"
    REBUILD = "rebuild"


class IndexBuildJobStatus(StrEnum):
    """Synchronous MVP status for generated maintenance jobs."""

    COMPLETED = "completed"
    FAILED = "failed"


class IndexBuildJob(DomainModel):
    """Result of clearing or rebuilding generated projections."""

    id: str = Field(min_length=1)
    action: IndexBuildJobAction
    status: IndexBuildJobStatus
    generated_path: str = "project_assets/generated"
    created_at: str = Field(min_length=1)
    completed_at: str = Field(min_length=1)
    message: str = Field(min_length=1)
