"""Export and generated projection API schemas."""

from pydantic import BaseModel, Field


class ExportFileInfo(BaseModel):
    """One readable file in an export bundle."""

    path: str
    media_type: str
    content: str


class ExportBundleResponse(BaseModel):
    """Source asset export bundle response."""

    id: str
    schema_version: str
    created_at: str
    files: list[ExportFileInfo] = Field(default_factory=list)


class IndexBuildJobInfo(BaseModel):
    """Generated projection maintenance result."""

    id: str
    action: str
    status: str
    generated_path: str
    created_at: str
    completed_at: str
    message: str


class IndexBuildJobResponse(BaseModel):
    """One generated projection maintenance response."""

    job: IndexBuildJobInfo
