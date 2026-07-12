"""Export API schemas."""

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
