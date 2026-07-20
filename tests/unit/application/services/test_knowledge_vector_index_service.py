from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from taichu.application.embeddings.models import (
    EmbeddingModelProfile,
    EmbeddingNormalization,
    EmbeddingRequest,
    EmbeddingResponse,
)
from taichu.application.retrieval.vector_index_models import (
    VectorIndexCollectionState,
    VectorIndexManifest,
    VectorIndexPoint,
    VectorIndexSearchHit,
    VectorIndexSearchRequest,
)
from taichu.application.services.knowledge_vector_index_service import (
    KnowledgeVectorIndexBuildError,
    KnowledgeVectorIndexService,
)
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeType,
)


def _card(
    card_id: str = "character-qin",
    *,
    updated_at: str = "2026-07-19T00:00:00Z",
) -> StructuredKnowledgeCard:
    return StructuredKnowledgeCard(
        id=card_id,
        type=StructuredKnowledgeType.CHARACTER,
        name="秦浩轩",
        aliases=["浩轩"],
        summary="大田镇少年，能够附体五彩小蛇。",
        lifecycle=StructuredKnowledgeLifecycle.CONFIRMED,
        source_origin=StructuredKnowledgeSourceOrigin.MANUAL,
        source_note="第一章",
        role_type="protagonist",
        identity="猎户少年",
        created_at="2026-07-18T00:00:00Z",
        updated_at=updated_at,
    )


@dataclass
class _KnowledgeRepository:
    cards: list[StructuredKnowledgeCard]

    async def list_confirmed_cards(
        self,
        type: StructuredKnowledgeType | None = None,
    ) -> list[StructuredKnowledgeCard]:
        if type is None:
            return list(self.cards)
        return [card for card in self.cards if card.type is type]


class _EmbeddingGateway:
    def __init__(self, *, fail: bool = False) -> None:
        self.requests: list[EmbeddingRequest] = []
        self.fail = fail

    def profile(self) -> EmbeddingModelProfile:
        return EmbeddingModelProfile(
            model_id="test-model",
            dimensions=2,
            max_input_tokens=8192,
            supports_chinese=True,
            supports_multilingual=True,
            transport="openai_compatible_http",
            normalization=EmbeddingNormalization.L2,
        )

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        self.requests.append(request)
        if self.fail:
            raise RuntimeError("simulated failure")
        return EmbeddingResponse(
            call_id="embedding_" + "a" * 32,
            model_id="test-model",
            dimensions=2,
            normalization=EmbeddingNormalization.L2,
            vectors=[[0.6, 0.8] for _ in request.texts],
            duration_ms=1,
        )


class _VectorIndex:
    def __init__(self) -> None:
        self.collections: dict[str, list[VectorIndexPoint]] = {"old": []}
        self.aliases: dict[str, str] = {"taichu_knowledge_vectors": "old"}
        self.deleted: list[str] = []

    async def create_collection(
        self, collection_name: str, *, dimensions: int
    ) -> None:
        assert dimensions == 2
        self.collections[collection_name] = []

    async def upsert_points(
        self, collection_name: str, points: list[VectorIndexPoint]
    ) -> None:
        self.collections[collection_name].extend(points)

    async def collection_state(
        self, collection_name: str
    ) -> VectorIndexCollectionState | None:
        if collection_name not in self.collections:
            return None
        return VectorIndexCollectionState(
            collection_name=collection_name,
            point_count=len(self.collections[collection_name]),
            dimensions=2,
        )

    async def get_alias_target(self, alias_name: str) -> str | None:
        return self.aliases.get(alias_name)

    async def replace_alias(
        self, alias_name: str, collection_name: str | None
    ) -> None:
        if collection_name is None:
            self.aliases.pop(alias_name, None)
        else:
            self.aliases[alias_name] = collection_name

    async def delete_collection(self, collection_name: str) -> None:
        self.collections.pop(collection_name, None)
        self.deleted.append(collection_name)

    async def search(
        self, request: VectorIndexSearchRequest
    ) -> list[VectorIndexSearchHit]:
        raise NotImplementedError


class _Manifests:
    def __init__(self, *, fail_save: bool = False) -> None:
        self.active: VectorIndexManifest | None = None
        self.fail_save = fail_save

    async def load_active(self) -> VectorIndexManifest | None:
        return self.active

    async def save_active(self, manifest: VectorIndexManifest) -> None:
        if self.fail_save:
            raise RuntimeError("simulated manifest failure")
        self.active = manifest

    async def delete_active(self) -> None:
        self.active = None


def _service(
    *,
    cards: list[StructuredKnowledgeCard] | None = None,
    embedding: _EmbeddingGateway | None = None,
    vector_index: _VectorIndex | None = None,
    manifests: _Manifests | None = None,
) -> tuple[
    KnowledgeVectorIndexService,
    _EmbeddingGateway,
    _VectorIndex,
    _Manifests,
    _KnowledgeRepository,
]:
    repository = _KnowledgeRepository(cards or [_card()])
    embedding = embedding or _EmbeddingGateway()
    vector_index = vector_index or _VectorIndex()
    manifests = manifests or _Manifests()
    return (
        KnowledgeVectorIndexService(
            knowledge_repository=repository,  # type: ignore[arg-type]
            embedding_gateway=embedding,
            vector_index=vector_index,
            manifests=manifests,
            active_alias="taichu_knowledge_vectors",
            document_batch_size=2,
            embedding_input_char_budget=1_000,
        ),
        embedding,
        vector_index,
        manifests,
        repository,
    )


def test_rebuild_switches_alias_only_after_validated_collection_and_manifest() -> None:
    async def scenario() -> None:
        service, embedding, vector_index, manifests, _ = _service()

        result = await service.rebuild()

        assert result.status == "completed"
        assert result.previous_alias_target == "old"
        assert result.manifest is manifests.active
        assert result.manifest is not None
        assert result.manifest.manifest_checksum
        assert result.manifest.document_count == 3
        assert vector_index.aliases["taichu_knowledge_vectors"] == (
            result.manifest.physical_collection_name
        )
        points = vector_index.collections[result.manifest.physical_collection_name]
        assert len(points) == 3
        assert all("content" not in point.payload for point in points)
        assert len(embedding.requests) == 2

        verification = await service.verify()
        assert verification.valid is True
        assert verification.issues == []

    asyncio.run(scenario())


def test_dry_run_has_no_embedding_or_qdrant_mutation() -> None:
    async def scenario() -> None:
        service, embedding, vector_index, _, _ = _service()
        result = await service.rebuild(dry_run=True)

        assert result.status == "dry_run"
        assert result.plan.card_count == 1
        assert result.plan.document_count == 3
        assert embedding.requests == []
        assert vector_index.collections == {"old": []}
        assert vector_index.aliases == {"taichu_knowledge_vectors": "old"}

    asyncio.run(scenario())


@pytest.mark.parametrize("manifest_failure", [False, True])
def test_failure_keeps_or_rolls_back_old_alias(manifest_failure: bool) -> None:
    async def scenario() -> None:
        embedding = _EmbeddingGateway(fail=not manifest_failure)
        manifests = _Manifests(fail_save=manifest_failure)
        service, _, vector_index, _, _ = _service(
            embedding=embedding,
            manifests=manifests,
        )

        with pytest.raises(KnowledgeVectorIndexBuildError):
            await service.rebuild()

        assert vector_index.aliases["taichu_knowledge_vectors"] == "old"
        assert vector_index.collections == {"old": []}
        assert vector_index.deleted

    asyncio.run(scenario())


def test_verify_detects_stale_mongo_snapshot() -> None:
    async def scenario() -> None:
        service, _, _, _, repository = _service()
        await service.rebuild()
        repository.cards = [_card(updated_at="2026-07-19T01:00:00Z")]

        verification = await service.verify()

        assert verification.valid is False
        assert any("已过期" in issue for issue in verification.issues)

    asyncio.run(scenario())
