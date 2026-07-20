from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from taichu.application.embeddings.models import (
    EmbeddingModelProfile,
    EmbeddingNormalization,
    EmbeddingPurpose,
    EmbeddingRequest,
    EmbeddingResponse,
)
from taichu.application.retrieval.models import (
    RetrievalFallbackReasonCode,
    RetrievalMode,
    RetrievalRequest,
    RetrievalTraceRecord,
)
from taichu.application.retrieval.vector_documents import knowledge_snapshot_sha256
from taichu.application.retrieval.vector_index_models import (
    VectorIndexCollectionState,
    VectorIndexManifest,
    VectorIndexPoint,
    VectorIndexSearchHit,
    VectorIndexSearchRequest,
)
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeType,
)
from taichu.infrastructure.retrieval.vector_backend import (
    KnowledgeVectorRetrievalBackend,
    KnowledgeVectorRetrievalError,
)
from taichu.application.services.retrieval_service import RetrievalService
from taichu.infrastructure.retrieval.mongo_lexical_backend import (
    MongoLexicalRetrievalBackend,
)


def _card(
    *,
    card_id: str = "character-qin",
    name: str = "秦浩轩",
    lifecycle: StructuredKnowledgeLifecycle = StructuredKnowledgeLifecycle.CONFIRMED,
    updated_at: str = "2026-07-19T00:00:00Z",
) -> StructuredKnowledgeCard:
    return StructuredKnowledgeCard(
        id=card_id,
        type=StructuredKnowledgeType.CHARACTER,
        name=name,
        aliases=["浩轩"] if name == "秦浩轩" else [],
        summary="大田镇少年，能够附体五彩小蛇。",
        lifecycle=lifecycle,
        source_origin=StructuredKnowledgeSourceOrigin.MANUAL,
        source_note="第一章",
        role_type="protagonist",
        created_at="2026-07-18T00:00:00Z",
        updated_at=updated_at,
    )


@dataclass
class _Repository:
    cards: list[StructuredKnowledgeCard]

    def __post_init__(self) -> None:
        self.get_calls: list[str] = []

    async def list_confirmed_cards(
        self,
        type: StructuredKnowledgeType | None = None,
    ) -> list[StructuredKnowledgeCard]:
        return [
            card
            for card in self.cards
            if card.lifecycle is StructuredKnowledgeLifecycle.CONFIRMED
            and (type is None or card.type is type)
        ]

    async def get_card(self, card_id: str) -> StructuredKnowledgeCard | None:
        self.get_calls.append(card_id)
        return next((card for card in self.cards if card.id == card_id), None)


class _Embedding:
    def __init__(self) -> None:
        self.requests: list[EmbeddingRequest] = []

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
        return EmbeddingResponse(
            call_id="embedding_" + "a" * 32,
            model_id="test-model",
            dimensions=2,
            normalization=EmbeddingNormalization.L2,
            vectors=[[0.6, 0.8]],
            input_tokens=9,
            total_tokens=9,
            duration_ms=7,
        )


class _VectorIndex:
    def __init__(self, hits: list[VectorIndexSearchHit]) -> None:
        self.hits = hits
        self.search_requests: list[VectorIndexSearchRequest] = []

    async def collection_state(
        self, collection_name: str
    ) -> VectorIndexCollectionState | None:
        return VectorIndexCollectionState(
            collection_name=collection_name,
            point_count=3,
            dimensions=2,
        )

    async def get_alias_target(self, alias_name: str) -> str | None:
        return "physical"

    async def search(
        self, request: VectorIndexSearchRequest
    ) -> list[VectorIndexSearchHit]:
        self.search_requests.append(request)
        return self.hits

    async def create_collection(
        self, collection_name: str, *, dimensions: int
    ) -> None:
        raise NotImplementedError

    async def upsert_points(
        self, collection_name: str, points: list[VectorIndexPoint]
    ) -> None:
        raise NotImplementedError

    async def replace_alias(
        self, alias_name: str, collection_name: str | None
    ) -> None:
        raise NotImplementedError

    async def delete_collection(self, collection_name: str) -> None:
        raise NotImplementedError


@dataclass
class _Manifests:
    manifest: VectorIndexManifest | None

    async def load_active(self) -> VectorIndexManifest | None:
        return self.manifest

    async def save_active(self, manifest: VectorIndexManifest) -> None:
        self.manifest = manifest

    async def delete_active(self) -> None:
        self.manifest = None


class _Traces:
    def __init__(self) -> None:
        self.records: list[RetrievalTraceRecord] = []

    async def append(self, record: RetrievalTraceRecord) -> None:
        self.records.append(record)


def _manifest(cards: list[StructuredKnowledgeCard]) -> VectorIndexManifest:
    return VectorIndexManifest(
        index_id="knowledge_vectors_20260719_010203_a1b2c3",
        knowledge_snapshot_sha256=knowledge_snapshot_sha256(cards),
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


def _hit(
    *,
    kind: str,
    score: float,
    card_id: str = "character-qin",
    updated_at: str = "2026-07-19T00:00:00Z",
) -> VectorIndexSearchHit:
    return VectorIndexSearchHit(
        point_id=f"point-{kind}",
        score=score,
        card_id=card_id,
        knowledge_type=StructuredKnowledgeType.CHARACTER,
        document_kind=kind,
        field_paths=["name"],
        content_sha256="a" * 64,
        card_updated_at=updated_at,
        projection_strategy_id="structured_card_fields",
    )


def test_embeds_query_searches_filtered_index_and_rereads_current_card() -> None:
    async def scenario() -> None:
        card = _card()
        repository = _Repository([card])
        embedding = _Embedding()
        vector_index = _VectorIndex(
            [_hit(kind="identity", score=0.75), _hit(kind="summary", score=0.70)]
        )
        backend = KnowledgeVectorRetrievalBackend(
            knowledge_repository=repository,  # type: ignore[arg-type]
            embedding_gateway=embedding,
            vector_index=vector_index,
            manifests=_Manifests(_manifest([card])),
            candidate_multiplier=3,
            score_threshold=0.5,
            coverage_bonus=0.02,
        )

        result = await backend.retrieve(
            RetrievalRequest(
                query_text="谁能附体五彩小蛇？",
                knowledge_types=frozenset({StructuredKnowledgeType.CHARACTER}),
                top_k=2,
                requested_strategy="knowledge_vector",
            )
        )

        assert result.strategy == "knowledge_vector"
        assert result.index_snapshot_id == _manifest([card]).index_id
        assert result.candidates[0].card is card
        assert result.candidates[0].score == 0.77
        assert repository.get_calls == [card.id]
        assert embedding.requests[0].purpose is EmbeddingPurpose.KNOWLEDGE_QUERY
        assert vector_index.search_requests[0].top_k == 6
        assert vector_index.search_requests[0].knowledge_types == frozenset(
            {StructuredKnowledgeType.CHARACTER}
        )
        assert result.metrics.embedding_call_id is not None
        assert result.metrics.embedding_input_tokens == 9
        assert result.metrics.index_search_duration_ms is not None

    asyncio.run(scenario())


def test_discards_hit_when_card_was_changed_after_indexing() -> None:
    async def scenario() -> None:
        card = _card()
        repository = _Repository([card])
        backend = KnowledgeVectorRetrievalBackend(
            knowledge_repository=repository,  # type: ignore[arg-type]
            embedding_gateway=_Embedding(),
            vector_index=_VectorIndex(
                [_hit(kind="summary", score=0.8, updated_at="stale")]
            ),
            manifests=_Manifests(_manifest([card])),
        )

        result = await backend.retrieve(RetrievalRequest(query_text="查询"))

        assert result.candidates == []
        assert repository.get_calls == [card.id]

    asyncio.run(scenario())


def test_rejects_stale_snapshot_before_embedding_or_search() -> None:
    async def scenario() -> None:
        old_card = _card()
        current_card = _card(updated_at="2026-07-19T01:00:00Z")
        embedding = _Embedding()
        vector_index = _VectorIndex([])
        backend = KnowledgeVectorRetrievalBackend(
            knowledge_repository=_Repository([current_card]),  # type: ignore[arg-type]
            embedding_gateway=embedding,
            vector_index=vector_index,
            manifests=_Manifests(_manifest([old_card])),
        )

        with pytest.raises(KnowledgeVectorRetrievalError) as captured:
            await backend.retrieve(RetrievalRequest(query_text="查询"))

        assert captured.value.code == "VECTOR_INDEX_STALE"
        assert embedding.requests == []
        assert vector_index.search_requests == []

    asyncio.run(scenario())


def test_exact_identity_keeps_only_exact_card_and_relation_query_excludes_anchor() -> None:
    async def scenario() -> None:
        qin = _card()
        mentor = _card(card_id="character-mentor", name="陈老头")
        cards = [qin, mentor]
        repository = _Repository(cards)
        vector_index = _VectorIndex(
            [
                _hit(kind="summary", score=0.9, card_id=qin.id),
                _hit(kind="summary", score=0.8, card_id=mentor.id),
            ]
        )
        backend = KnowledgeVectorRetrievalBackend(
            knowledge_repository=repository,  # type: ignore[arg-type]
            embedding_gateway=_Embedding(),
            vector_index=vector_index,
            manifests=_Manifests(_manifest(cards)),
        )

        exact = await backend.retrieve(
            RetrievalRequest(
                query_text="秦浩轩",
                knowledge_types=frozenset({StructuredKnowledgeType.CHARACTER}),
            )
        )
        relation = await backend.retrieve(
            RetrievalRequest(
                query_text="谁曾教秦浩轩辨识草药？",
                knowledge_types=frozenset({StructuredKnowledgeType.CHARACTER}),
            )
        )

        assert [item.card.id for item in exact.candidates] == [qin.id]
        assert [item.card.id for item in relation.candidates] == [mentor.id]

    asyncio.run(scenario())


def test_unconfirmed_scope_request_returns_empty_without_embedding_or_search() -> None:
    async def scenario() -> None:
        card = _card()
        embedding = _Embedding()
        vector_index = _VectorIndex([_hit(kind="summary", score=0.9)])
        backend = KnowledgeVectorRetrievalBackend(
            knowledge_repository=_Repository([card]),  # type: ignore[arg-type]
            embedding_gateway=embedding,
            vector_index=vector_index,
            manifests=_Manifests(_manifest([card])),
        )

        result = await backend.retrieve(
            RetrievalRequest(query_text="把未确认角色当成主角师父。")
        )

        assert result.candidates == []
        assert embedding.requests == []
        assert vector_index.search_requests == []

    asyncio.run(scenario())


def test_stale_vector_index_falls_back_to_lexical_in_evaluation_runtime() -> None:
    async def scenario() -> None:
        old_card = _card()
        current_card = _card(updated_at="2026-07-19T01:00:00Z")
        repository = _Repository([current_card])
        vector_backend = KnowledgeVectorRetrievalBackend(
            knowledge_repository=repository,  # type: ignore[arg-type]
            embedding_gateway=_Embedding(),
            vector_index=_VectorIndex([]),
            manifests=_Manifests(_manifest([old_card])),
        )
        service = RetrievalService(
            MongoLexicalRetrievalBackend(repository),  # type: ignore[arg-type]
            _Traces(),
            additional_backends={"knowledge_vector": vector_backend},
        )

        result = await service.retrieve(
            RetrievalRequest(
                query_text="秦浩轩",
                requested_strategy="knowledge_vector",
            )
        )

        assert result.effective_strategy == "mongo_lexical"
        assert result.fallback_used is True
        assert result.fallback_reason_code is RetrievalFallbackReasonCode.BACKEND_ERROR

    asyncio.run(scenario())


def test_rejects_identity_mode() -> None:
    card = _card()
    backend = KnowledgeVectorRetrievalBackend(
        knowledge_repository=_Repository([card]),  # type: ignore[arg-type]
        embedding_gateway=_Embedding(),
        vector_index=_VectorIndex([]),
        manifests=_Manifests(_manifest([card])),
    )
    with pytest.raises(KnowledgeVectorRetrievalError, match="只支持相关性"):
        asyncio.run(
            backend.retrieve(
                RetrievalRequest(
                    mode=RetrievalMode.CATALOG,
                    requested_strategy=None,
                )
            )
        )
