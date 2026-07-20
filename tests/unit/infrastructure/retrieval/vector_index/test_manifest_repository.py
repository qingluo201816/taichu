from __future__ import annotations

import asyncio
import json

import pytest

from taichu.application.embeddings.models import EmbeddingNormalization
from taichu.application.retrieval.vector_index_models import VectorIndexManifest
from taichu.infrastructure.retrieval.vector_index.manifest_repository import (
    JsonVectorIndexManifestRepository,
    VectorIndexManifestStoreError,
)


def _manifest() -> VectorIndexManifest:
    return VectorIndexManifest(
        index_id="knowledge_vectors_20260719_010203_a1b2c3",
        knowledge_snapshot_sha256="a" * 64,
        embedding_model_id="test-model",
        vector_dimensions=2,
        document_projection_strategy_id="structured_card_fields",
        vector_normalization=EmbeddingNormalization.L2,
        card_count=1,
        document_count=3,
        estimated_vector_bytes=24,
        built_at="2026-07-19T01:02:03Z",
        build_duration_ms=10,
        physical_collection_name="physical",
        active_alias="active",
    ).finalized()


def test_saves_active_and_history_atomically_and_detects_corruption(tmp_path) -> None:
    async def scenario() -> None:
        repository = JsonVectorIndexManifestRepository(tmp_path)
        manifest = _manifest()
        await repository.save_active(manifest)
        assert await repository.load_active() == manifest

        root = tmp_path / "generated" / "vector_indexes" / "knowledge_cards"
        assert (root / f"{manifest.index_id}.json").exists()
        active_path = root / "active_manifest.json"
        payload = json.loads(active_path.read_text(encoding="utf-8"))
        payload["document_count"] = 999
        active_path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(VectorIndexManifestStoreError, match="损坏或校验失败"):
            await repository.load_active()

    asyncio.run(scenario())
