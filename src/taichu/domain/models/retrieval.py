"""Retrieval result and generated embedding projection contracts."""

from enum import StrEnum

from pydantic import Field

from taichu.domain.models.base import DomainModel
from taichu.domain.models.source_ref import SourceRef


class RetrievalSourceType(StrEnum):
    """Sources that retrieval can surface with evidence."""

    CHAPTER = "chapter"
    KNOWLEDGE = "knowledge"
    SUMMARY = "summary"


class RetrievalReason(StrEnum):
    """Retrieval strategy labels."""

    EXACT = "exact"
    FTS = "fts"
    VECTOR = "vector"
    HYBRID = "hybrid"


class RetrievalHit(DomainModel):
    """A retrieval hit that always carries SourceRef evidence."""

    source_type: RetrievalSourceType
    source_id: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    score: float
    reason: RetrievalReason
    source_ref: SourceRef


class EmbeddingChunk(DomainModel):
    """Generated projection chunk that is not a fact source."""

    id: str = Field(min_length=1)
    source_type: RetrievalSourceType
    source_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_ref: SourceRef
    embedding: list[float] | str
    updated_at: str = Field(min_length=1)
