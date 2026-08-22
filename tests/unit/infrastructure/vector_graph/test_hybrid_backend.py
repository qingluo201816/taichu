import asyncio
import hashlib
from types import SimpleNamespace
from unittest.mock import Mock

from taichu.application.vector_graph.models import (
    VectorGraphBuildPlan,
    VectorGraphBuildResult,
    VectorGraphExtractedTriplets,
    VectorGraphEvidence,
    VectorGraphRetrievalResult,
    VectorGraphSourceDocument,
    VectorGraphSourceType,
)
from taichu.infrastructure.vector_graph.backend import _merge_context_sources
from taichu.infrastructure.vector_graph.hybrid_backend import HybridVectorGraphBackend
from taichu.infrastructure.vector_graph.milvus_store import TaichuHNSWMilvusStore


def _evidence(source_ref: str, content: str, rank: int = 1) -> VectorGraphEvidence:
    return VectorGraphEvidence(
        source_type=VectorGraphSourceType.MANUSCRIPT_CHUNK,
        source_id=source_ref,
        source_ref=source_ref,
        title="章节",
        content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        rank=rank,
    )


def test_hybrid_update_delegates_source_level_plan_to_milvus() -> None:
    document = VectorGraphSourceDocument(
        source_type=VectorGraphSourceType.KNOWLEDGE_CARD,
        source_id="card-1",
        source_ref="knowledge-card:card-1",
        title="测试卡",
        content="测试内容",
        content_sha256="a" * 64,
        updated_at="2026-08-16T00:00:00Z",
    )
    plan = VectorGraphBuildPlan(
        snapshot_sha256="b" * 64,
        manuscript_count=0,
        manuscript_chunk_count=0,
        knowledge_card_count=1,
        document_count=1,
        total_content_chars=4,
    )

    class MilvusFake:
        async def update(
            self,
            documents: list[VectorGraphSourceDocument],
            *,
            plan: VectorGraphBuildPlan,
            extracted_triplets: VectorGraphExtractedTriplets | None = None,
        ) -> VectorGraphBuildResult:
            assert documents == [document]
            assert plan == expected_plan
            assert extracted_triplets is None
            return VectorGraphBuildResult(status="completed", plan=plan)

    expected_plan = plan
    backend = HybridVectorGraphBackend(
        milvus=MilvusFake(),  # type: ignore[arg-type]
        reranker=Mock(),  # type: ignore[arg-type]
    )

    result = asyncio.run(backend.update([document], plan=plan))

    assert result.status == "completed"
    assert result.plan == plan


def test_hybrid_retrieval_uses_30_candidates_and_reranks_to_10() -> None:
    rrf_evidences = [
        _evidence(f"rrf-{index}", f"Milvus RRF 证据{index}") for index in range(30)
    ]

    class MilvusFake:
        async def retrieve(
            self, query: str, *, top_k: int
        ) -> VectorGraphRetrievalResult:
            assert query == "主角获得了什么"
            assert top_k == 30
            return VectorGraphRetrievalResult(query=query, evidences=rrf_evidences)

        async def expand_context(
            self, evidences: list[VectorGraphEvidence]
        ) -> list[VectorGraphEvidence]:
            assert len(evidences) == 10
            return [
                item.model_copy(update={"context_content": f"上下文：{item.content}"})
                for item in evidences
            ]

        async def close(self) -> None:
            return None

    class RerankerFake:
        async def rerank(
            self,
            query: str,
            evidences: list[VectorGraphEvidence],
            *,
            top_k: int,
        ) -> list[VectorGraphEvidence]:
            assert query == "主角获得了什么"
            assert len(evidences) == 30
            assert top_k == 10
            return [
                item.model_copy(update={"rank": index + 1})
                for index, item in enumerate(evidences[:top_k])
            ]

    backend = HybridVectorGraphBackend(
        milvus=MilvusFake(),  # type: ignore[arg-type]
        reranker=RerankerFake(),  # type: ignore[arg-type]
    )
    result = asyncio.run(backend.retrieve("主角获得了什么", top_k=3))

    assert len(result.evidences) == 10
    assert [item.rank for item in result.evidences] == list(range(1, 11))
    assert result.evidences[0].context_content == "上下文：Milvus RRF 证据0"


def test_hybrid_retrieval_without_graph_keeps_same_rerank_pipeline() -> None:
    candidates = [_evidence(f"plain-{index}", f"普通召回{index}") for index in range(30)]

    class MilvusFake:
        async def retrieve_without_graph(
            self, query: str, *, top_k: int
        ) -> VectorGraphRetrievalResult:
            assert top_k == 30
            return VectorGraphRetrievalResult(query=query, evidences=candidates)

        async def expand_context(
            self, evidences: list[VectorGraphEvidence]
        ) -> list[VectorGraphEvidence]:
            return evidences

    class RerankerFake:
        async def rerank(
            self,
            query: str,
            evidences: list[VectorGraphEvidence],
            *,
            top_k: int,
        ) -> list[VectorGraphEvidence]:
            assert len(evidences) == 30
            return evidences[:top_k]

    backend = HybridVectorGraphBackend(
        milvus=MilvusFake(),  # type: ignore[arg-type]
        reranker=RerankerFake(),  # type: ignore[arg-type]
    )

    result = asyncio.run(backend.retrieve_without_graph("问题", top_k=3))

    assert len(result.evidences) == 10
    assert result.retrieved_relations == []
    assert result.expanded_relations == []
    assert result.reranked_relations == []


def test_milvus_hybrid_search_uses_bm25_dense_top_30_and_rrf() -> None:
    store = object.__new__(TaichuHNSWMilvusStore)
    store.ef_search = 150
    store.rrf_k = 60
    store.client = Mock()
    store.client.hybrid_search.return_value = [[]]
    store.passage_collection = "passages"
    store.settings = SimpleNamespace(final_top_k=30)

    store.hybrid_search_passages(
        lexical_query="主角",
        query_embedding=[0.1, 0.2],
        top_k=30,
    )

    kwargs = store.client.hybrid_search.call_args.kwargs
    assert kwargs["limit"] == 30
    assert kwargs["ranker"]._k == 60
    sparse_request, dense_request = kwargs["reqs"]
    assert sparse_request.limit == dense_request.limit == 30
    assert sparse_request.anns_field == "sparse"
    assert dense_request.anns_field == "vector"
    assert dense_request.param == {
        "metric_type": "IP",
        "params": {"ef": 150},
    }


def test_three_neighbor_chunks_merge_overlap_only_once() -> None:
    context = _merge_context_sources(
        [
            {
                "source_id": "chapter-1",
                "chunk_index": 0,
                "start_char": 0,
                "end_char": 6,
                "content": "abcdef",
            },
            {
                "source_id": "chapter-1",
                "chunk_index": 1,
                "start_char": 4,
                "end_char": 10,
                "content": "efghij",
            },
            {
                "source_id": "chapter-1",
                "chunk_index": 2,
                "start_char": 8,
                "end_char": 14,
                "content": "ijklmn",
            },
        ]
    )

    assert context == {
        "context_content": "abcdefghijklmn",
        "context_source_ref": "manuscript:chapter-1:0-14",
        "context_start_char": 0,
        "context_end_char": 14,
        "context_chunk_indexes": [0, 1, 2],
    }
