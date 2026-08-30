"""Vector Graph RAG 的技术无关应用模型。"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class VectorGraphModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


VectorGraphDocumentIdentity = tuple[str, int, str]
VectorGraphExtractedTriplets = Mapping[
    VectorGraphDocumentIdentity,
    tuple[tuple[str, str, str], ...],
]


class VectorGraphSourceType(StrEnum):
    MANUSCRIPT_CHUNK = "manuscript_chunk"
    KNOWLEDGE_CARD = "knowledge_card"


class VectorGraphSourceDocument(VectorGraphModel):
    source_type: VectorGraphSourceType
    source_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    content_sha256: str = Field(min_length=64, max_length=64)
    updated_at: str = Field(min_length=1)
    chunk_index: int = Field(default=0, ge=0)
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, ge=0)
    parent_start_char: int | None = Field(default=None, ge=0)
    parent_end_char: int | None = Field(default=None, ge=0)
    parent_chunk_indexes: list[int] = Field(default_factory=list)


class VectorGraphSourceIndexState(VectorGraphModel):
    """一个正文章节或知识卡最近一次成功写入派生索引的状态。"""

    source_key: str = Field(min_length=1)
    source_type: VectorGraphSourceType
    source_id: str = Field(min_length=1)
    source_sha256: str = Field(min_length=64, max_length=64)
    index_configuration_sha256: str = Field(min_length=64, max_length=64)
    document_count: int = Field(ge=0)
    total_content_chars: int = Field(ge=0)
    source_updated_at: str = Field(min_length=1)
    indexed_at: str = Field(min_length=1)


class VectorGraphSourceIndexManifest(VectorGraphModel):
    """逐来源增量索引的成功清单；失败来源不会提前覆盖旧状态。"""

    sources: list[VectorGraphSourceIndexState] = Field(default_factory=list)
    updated_at: str = Field(min_length=1)


class VectorGraphBuildPlan(VectorGraphModel):
    snapshot_sha256: str = Field(min_length=64, max_length=64)
    manuscript_count: int = Field(ge=0)
    manuscript_chunk_count: int = Field(ge=0)
    knowledge_card_count: int = Field(ge=0)
    document_count: int = Field(ge=0)
    total_content_chars: int = Field(ge=0)


class VectorGraphBuildResult(VectorGraphModel):
    status: str
    plan: VectorGraphBuildPlan
    index_configuration_sha256: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
    )
    entity_count: int = Field(default=0, ge=0)
    relation_count: int = Field(default=0, ge=0)
    passage_count: int = Field(default=0, ge=0)
    updated_source_count: int = Field(default=0, ge=0)
    deleted_source_count: int = Field(default=0, ge=0)
    unchanged_source_count: int = Field(default=0, ge=0)


class VectorGraphBuildStage(StrEnum):
    PLANNING = "planning"
    EXTRACTING = "extracting"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


class VectorGraphIndexState(StrEnum):
    NOT_BUILT = "not_built"
    BUILDING = "building"
    READY = "ready"
    STALE = "stale"
    INCOMPLETE = "incomplete"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class VectorGraphBuildProgress(VectorGraphModel):
    stage: VectorGraphBuildStage
    snapshot_sha256: str = Field(min_length=64, max_length=64)
    processed_documents: int = Field(default=0, ge=0)
    total_documents: int = Field(default=0, ge=0)
    processed_sources: int = Field(default=0, ge=0)
    total_sources: int = Field(default=0, ge=0)
    current_source_key: str | None = None
    started_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    error_message: str | None = None


class VectorGraphCollectionStatus(VectorGraphModel):
    role: str = Field(min_length=1)
    name: str = Field(min_length=1)
    exists: bool
    row_count: int | None = Field(default=None, ge=0)


class VectorGraphIndexStatus(VectorGraphModel):
    state: VectorGraphIndexState
    current_plan: VectorGraphBuildPlan
    progress: VectorGraphBuildProgress | None = None
    active_build: VectorGraphBuildResult | None = None
    is_current: bool = False
    collections: list[VectorGraphCollectionStatus] = Field(default_factory=list)
    message: str = Field(min_length=1)


class VectorGraphBuildStartResult(VectorGraphModel):
    accepted: bool
    message: str = Field(min_length=1)
    plan: VectorGraphBuildPlan


class VectorGraphEvidence(VectorGraphModel):
    passage_id: str = ""
    source_type: VectorGraphSourceType
    source_id: str
    source_ref: str
    title: str
    content: str
    content_sha256: str = Field(min_length=64, max_length=64)
    rank: int = Field(ge=1)
    chunk_index: int = Field(default=0, ge=0)
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, ge=0)
    parent_start_char: int | None = Field(default=None, ge=0)
    parent_end_char: int | None = Field(default=None, ge=0)
    parent_chunk_indexes: list[int] = Field(default_factory=list)
    context_content: str | None = None
    context_source_ref: str | None = None
    context_start_char: int | None = Field(default=None, ge=0)
    context_end_char: int | None = Field(default=None, ge=0)
    context_chunk_indexes: list[int] = Field(default_factory=list)
    relation_ids: list[str] = Field(default_factory=list)
    relation_texts: list[str] = Field(default_factory=list)
    retrieval_channels: list[str] = Field(default_factory=list)
    reranker_score: float | None = Field(default=None, ge=0, le=1)
    authority_verified: bool = False


class VectorGraphRetrievalResult(VectorGraphModel):
    query: str
    evidences: list[VectorGraphEvidence] = Field(default_factory=list)
    retrieved_relations: list[str] = Field(default_factory=list)
    expanded_relations: list[str] = Field(default_factory=list)
    context_relations: list[str] = Field(default_factory=list)
    reranked_passage_ids: list[str] = Field(default_factory=list)
    reranked_source_ids: list[str] = Field(default_factory=list)
    reranked_relations: list[str] = Field(default_factory=list)
    seed_passage_ids: list[str] = Field(default_factory=list)
    seed_entity_ids: list[str] = Field(default_factory=list)
    seed_relation_ids: list[str] = Field(default_factory=list)
    graph_passage_ids: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
