"""MVP source reference contract."""

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from taichu.domain.models.base import DomainModel


class SourceReferenceType(StrEnum):
    """Source types supported by MVP knowledge and AI records."""

    CHAPTER = "chapter"
    KNOWLEDGE_CARD = "knowledge_card"
    AUTHOR_NOTE = "author_note"
    EXTERNAL = "external"


class SourceReference(DomainModel):
    """Unified source reference shown to authors as 来源引用."""

    source_type: SourceReferenceType
    source_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    excerpt: str = Field(min_length=1, max_length=300)
    note: str = ""
    author_note_body: str | None = None

    @field_validator("excerpt")
    @classmethod
    def excerpt_must_not_exceed_contract(cls, value: str) -> str:
        """Keep the excerpt limit explicit for API and UI validation."""
        if len(value) > 300:
            raise ValueError("来源原文摘录不能超过 300 字")
        return value

    @model_validator(mode="after")
    def validate_author_note_body(self) -> "SourceReference":
        """Author notes are source text, so the body must be persisted."""
        if self.source_type is SourceReferenceType.AUTHOR_NOTE:
            if not self.author_note_body or not self.author_note_body.strip():
                raise ValueError("作者说明来源必须保存正文内容")
        return self
