"""向量索引、清单、检索命中和重建校验模型。"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from taichu.application.embeddings.models import EmbeddingNormalization
from taichu.domain.models.structured_knowledge import StructuredKnowledgeType


class VectorIndexModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class VectorIndexPoint(VectorIndexModel):
    point_id: str = Field(min_length=1, max_length=128)
    vector: list[float] = Field(min_length=1)
    payload: dict[str, str | list[str]]

    @model_validator(mode="after")
    def validate_finite_vector(self) -> Self:
        if any(not math.isfinite(value) for value in self.vector):
            raise ValueError("向量索引点包含 NaN 或 Infinity。")
        return self


class VectorIndexSearchRequest(VectorIndexModel):
    collection_name: str = Field(min_length=1, max_length=255)
    vector: list[float] = Field(min_length=1)
    top_k: int = Field(ge=1, le=200)
    knowledge_types: frozenset[StructuredKnowledgeType] = Field(
        default_factory=frozenset
    )
    score_threshold: float | None = Field(default=None, ge=-1, le=1)

    @model_validator(mode="after")
    def validate_finite_vector(self) -> Self:
        if any(not math.isfinite(value) for value in self.vector):
            raise ValueError("向量查询包含 NaN 或 Infinity。")
        return self


class VectorIndexSearchHit(VectorIndexModel):
    point_id: str = Field(min_length=1, max_length=128)
    score: float = Field(ge=-1, le=1)
    card_id: str = Field(min_length=1)
    knowledge_type: StructuredKnowledgeType
    document_kind: str = Field(min_length=1, max_length=64)
    field_paths: list[str] = Field(min_length=1)
    content_sha256: str = Field(min_length=64, max_length=64)
    card_updated_at: str = Field(min_length=1)
    source_lifecycle: Literal["confirmed"] = "confirmed"
    projection_strategy_id: str = Field(min_length=1, max_length=128)


class VectorIndexCollectionState(VectorIndexModel):
    collection_name: str = Field(min_length=1, max_length=255)
    point_count: int = Field(ge=0)
    dimensions: int = Field(ge=1)
    distance: Literal["cosine"] = "cosine"


class VectorIndexManifest(VectorIndexModel):
    """active 向量索引的可审计、可校验清单。"""

    format_version: Literal[1] = 1
    lifecycle: Literal["confirmed"] = "confirmed"
    index_id: str = Field(
        pattern=r"^knowledge_vectors_\d{8}_\d{6}_[a-f0-9]{6}$"
    )
    knowledge_snapshot_sha256: str = Field(min_length=64, max_length=64)
    embedding_model_id: str = Field(min_length=1, max_length=200)
    vector_dimensions: int = Field(ge=1)
    document_projection_strategy_id: str = Field(min_length=1, max_length=128)
    vector_normalization: EmbeddingNormalization
    card_count: int = Field(ge=0)
    document_count: int = Field(ge=0)
    estimated_vector_bytes: int = Field(ge=0)
    built_at: str = Field(min_length=1)
    build_duration_ms: int = Field(ge=0)
    physical_collection_name: str = Field(min_length=1, max_length=255)
    active_alias: str = Field(min_length=1, max_length=255)
    manifest_checksum: str = Field(default="", max_length=64)

    @model_validator(mode="after")
    def validate_manifest_checksum(self) -> Self:
        if self.manifest_checksum and self.manifest_checksum != self.calculated_checksum():
            raise ValueError("向量索引清单校验和不匹配。")
        return self

    def finalized(self) -> VectorIndexManifest:
        return self.model_copy(update={"manifest_checksum": self.calculated_checksum()})

    def calculated_checksum(self) -> str:
        payload = self.model_dump(mode="json", exclude={"manifest_checksum"})
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class VectorIndexBuildPlan(VectorIndexModel):
    card_count: int = Field(ge=0)
    document_count: int = Field(ge=0)
    knowledge_snapshot_sha256: str = Field(min_length=64, max_length=64)
    embedding_model_id: str = Field(min_length=1, max_length=200)
    vector_dimensions: int = Field(ge=1)
    active_alias: str = Field(min_length=1, max_length=255)


class VectorIndexVerification(VectorIndexModel):
    valid: bool
    manifest: VectorIndexManifest | None = None
    current_knowledge_snapshot_sha256: str = Field(min_length=64, max_length=64)
    alias_target: str | None = None
    collection_point_count: int | None = Field(default=None, ge=0)
    issues: list[str] = Field(default_factory=list)


class VectorIndexBuildResult(VectorIndexModel):
    status: Literal["dry_run", "completed"]
    plan: VectorIndexBuildPlan
    manifest: VectorIndexManifest | None = None
    previous_alias_target: str | None = None
