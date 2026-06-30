"""MVP writing outline contracts."""

from pydantic import Field

from taichu.domain.models.base import DomainModel


class OutlineChapter(DomainModel):
    """Chapter entry inside the single-novel writing outline."""

    chapter_id: str = Field(min_length=1)
    display_title: str = Field(min_length=1)
    order: int = Field(ge=0)
    markdown_path: str = Field(min_length=1)


class OutlineVolume(DomainModel):
    """Volume entry that owns an ordered chapter list."""

    volume_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    order: int = Field(ge=0)
    chapters: list[OutlineChapter] = Field(default_factory=list)


class WritingOutline(DomainModel):
    """Persistent volume and chapter tree for the only active novel."""

    volumes: list[OutlineVolume] = Field(default_factory=list)
    current_volume_id: str | None = None
    current_chapter_id: str | None = None
    updated_at: str = Field(min_length=1)
