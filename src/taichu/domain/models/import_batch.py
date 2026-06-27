"""Corpus import batch contract."""

from pydantic import Field

from taichu.domain.models.base import DomainModel


class ImportBatch(DomainModel):
    """Result metadata for a bounded corpus import."""

    id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    chapter_ids: list[str] = Field(default_factory=list)
    chapter_count: int = Field(ge=0)
    skipped_chapter_count: int = Field(ge=0)
    created_at: str = Field(min_length=1)
