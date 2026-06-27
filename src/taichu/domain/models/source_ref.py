"""SourceRef v1 evidence contract."""

from enum import StrEnum

from pydantic import Field, model_validator

from taichu.domain.models.base import DomainModel


class SourceRefSourceType(StrEnum):
    """Supported source categories for evidence references."""

    CHAPTER = "chapter"
    KNOWLEDGE = "knowledge"
    SUMMARY = "summary"
    WORKSPACE = "workspace"
    AI_CARD = "ai_card"
    AUTHOR_MANUAL = "author_manual"


class SourceAnchorType(StrEnum):
    """Supported v1 anchor precision levels."""

    DOCUMENT = "document"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    PARAGRAPH_RANGE = "paragraph_range"
    KNOWLEDGE_FIELD = "knowledge_field"
    CARD = "card"


class SourceRef(DomainModel):
    """Paragraph, field, or card level evidence pointer."""

    source_type: SourceRefSourceType
    source_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    chapter_id: str | None = None

    anchor_type: SourceAnchorType
    heading_path: list[str] | None = None

    paragraph_start: int | None = Field(default=None, ge=0)
    paragraph_end: int | None = Field(default=None, ge=0)

    field_path: str | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    excerpt: str = Field(min_length=1)
    excerpt_hash: str = Field(min_length=1)
    source_hash: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    stale: bool = False

    @model_validator(mode="after")
    def validate_anchor_contract(self) -> "SourceRef":
        """Validate the local SourceRef shape without reading storage."""
        normalized_path = self.path.replace("\\", "/").lower()
        if "project_assets/generated/" in normalized_path:
            raise ValueError("SourceRef must not point to generated assets")
        if normalized_path.endswith(".db") or "/sqlite/" in normalized_path:
            raise ValueError("SourceRef must not point to SQLite rows/files")

        if self.anchor_type is SourceAnchorType.PARAGRAPH:
            if self.paragraph_start is None:
                raise ValueError("paragraph anchor requires paragraph_start")
        if self.anchor_type is SourceAnchorType.PARAGRAPH_RANGE:
            if self.paragraph_start is None or self.paragraph_end is None:
                raise ValueError(
                    "paragraph_range anchor requires start and end"
                )
            if self.paragraph_end < self.paragraph_start:
                raise ValueError("paragraph_end must be >= paragraph_start")
        if self.anchor_type is SourceAnchorType.KNOWLEDGE_FIELD:
            if not self.field_path:
                raise ValueError("knowledge_field anchor requires field_path")
            if self.source_type is not SourceRefSourceType.KNOWLEDGE:
                raise ValueError(
                    "knowledge_field anchor requires knowledge source_type"
                )
        if self.anchor_type is SourceAnchorType.CARD:
            if self.source_type not in {
                SourceRefSourceType.WORKSPACE,
                SourceRefSourceType.AI_CARD,
                SourceRefSourceType.SUMMARY,
            }:
                raise ValueError("card anchor requires workspace-like source")

        if self.char_start is not None or self.char_end is not None:
            if self.paragraph_start is None:
                raise ValueError("char offsets require paragraph_start")
            if self.char_start is None or self.char_end is None:
                raise ValueError("char offsets require both start and end")
            if self.char_end < self.char_start:
                raise ValueError("char_end must be >= char_start")

        return self
