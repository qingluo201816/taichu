"""Chapter API schemas."""

from pydantic import BaseModel, Field


class ChapterInfo(BaseModel):
    """Chapter metadata exposed by the API."""

    id: str
    volume_id: str | None = None
    title: str
    order: int
    markdown_path: str
    status: str
    word_count: int
    created_at: str
    updated_at: str


class ChapterListResponse(BaseModel):
    """Chapter list response."""

    chapters: list[ChapterInfo] = Field(default_factory=list)


class ChapterReadResponse(BaseModel):
    """One chapter plus its Markdown body."""

    chapter: ChapterInfo
    markdown: str


class ChapterSaveRequest(BaseModel):
    """Request body for Markdown persistence."""

    markdown: str
