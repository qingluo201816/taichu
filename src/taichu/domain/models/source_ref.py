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
            raise ValueError("证据来源不能指向派生数据目录")
        if normalized_path.endswith(".db") or "/sqlite/" in normalized_path:
            raise ValueError("证据来源不能指向 SQLite 行或数据库文件")

        if self.anchor_type is SourceAnchorType.PARAGRAPH:
            if self.paragraph_start is None:
                raise ValueError("段落证据来源必须包含段落位置")
        if self.anchor_type is SourceAnchorType.PARAGRAPH_RANGE:
            if self.paragraph_start is None or self.paragraph_end is None:
                raise ValueError("段落范围证据来源必须包含起止段落")
            if self.paragraph_end < self.paragraph_start:
                raise ValueError("结束段落不能早于起始段落")
        if self.anchor_type is SourceAnchorType.KNOWLEDGE_FIELD:
            if not self.field_path:
                raise ValueError("知识字段证据来源必须包含字段路径")
            if self.source_type is not SourceRefSourceType.KNOWLEDGE:
                raise ValueError("知识字段证据来源必须指向知识文件")
        if self.anchor_type is SourceAnchorType.CARD:
            if self.source_type not in {
                SourceRefSourceType.WORKSPACE,
                SourceRefSourceType.AI_CARD,
                SourceRefSourceType.SUMMARY,
            }:
                raise ValueError("卡片证据来源必须指向工作区资产")

        if self.char_start is not None or self.char_end is not None:
            if self.paragraph_start is None:
                raise ValueError("选区偏移必须同时包含段落位置")
            if self.char_start is None or self.char_end is None:
                raise ValueError("选区偏移必须同时包含起止位置")
            if self.char_end < self.char_start:
                raise ValueError("选区结束位置不能早于起始位置")

        return self
