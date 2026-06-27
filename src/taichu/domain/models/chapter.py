"""Chapter and manuscript manifest contracts."""

from enum import StrEnum

from pydantic import Field, field_validator

from taichu.domain.models.base import DomainModel


class ChapterStatus(StrEnum):
    """Lifecycle states for manuscript chapters."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class Chapter(DomainModel):
    """Metadata for a chapter whose fact source is a Markdown file."""

    id: str = Field(min_length=1)
    volume_id: str | None = None
    title: str = Field(min_length=1)
    order: int = Field(ge=0)
    markdown_path: str = Field(min_length=1)
    status: ChapterStatus
    word_count: int = Field(ge=0)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)

    @field_validator("markdown_path")
    @classmethod
    def markdown_path_must_not_be_generated(cls, value: str) -> str:
        """Keep chapter metadata pointed at source Markdown only."""
        normalized = value.replace("\\", "/").lower()
        if "project_assets/generated/" in normalized:
            raise ValueError("章节正文路径不能指向派生数据")
        if not normalized.endswith(".md"):
            raise ValueError("章节正文路径必须指向 Markdown 文件")
        return value


class Volume(DomainModel):
    """Minimal volume ordering metadata."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    order: int = Field(ge=0)


class ChapterManifest(DomainModel):
    """Single-novel chapter order and current chapter pointer."""

    schema_version: str = Field(min_length=1)
    current_chapter_id: str | None = None
    volumes: list[Volume] = Field(default_factory=list)
    chapters: list[Chapter] = Field(default_factory=list)
    updated_at: str = Field(min_length=1)
