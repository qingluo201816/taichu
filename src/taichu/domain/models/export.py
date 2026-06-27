"""Readable export bundle contracts."""

from pydantic import Field

from taichu.domain.models.base import DomainModel


class ExportFile(DomainModel):
    """One readable file in an export bundle."""

    path: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    content: str


class ExportBundle(DomainModel):
    """A source-data export bundle for the active single novel."""

    id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    files: list[ExportFile] = Field(default_factory=list)
