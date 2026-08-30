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
from taichu.infrastructure.vector_graph.hybrid_backend import (
    HybridVectorGraphBackend,
    _bound_parent_context,
    _deduplicate_context_windows,
    _knowledge_card_context,
    _manuscript_fact_context,
    _project_context_relations,
    _relevant_relation_indexes,
    _select_context_evidences,
)
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


def test_hybrid_retrieval_keeps_top_10_trace_and_assembles_top_3_contexts() -> None:
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
            assert len(evidences) == 3
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
            assert top_k == 30
            return [
                item.model_copy(update={"rank": index + 1})
                for index, item in enumerate(evidences[:top_k])
            ]

    backend = HybridVectorGraphBackend(
        milvus=MilvusFake(),  # type: ignore[arg-type]
        reranker=RerankerFake(),  # type: ignore[arg-type]
    )
    result = asyncio.run(backend.retrieve("主角获得了什么", top_k=10))

    assert len(result.evidences) == 3
    assert [item.rank for item in result.evidences] == list(range(1, 4))
    assert result.reranked_source_ids == [f"rrf-{index}" for index in range(10)]
    assert result.reranked_relations == []
    assert result.evidences[0].context_content == "上下文：Milvus RRF 证据0"
    assert result.evidences[2].context_content == "上下文：Milvus RRF 证据2"


def test_reconstructed_overlapping_windows_are_merged_without_losing_relations() -> (
    None
):
    first = _evidence("chapter-1", "片段一", rank=1).model_copy(
        update={
            "context_start_char": 0,
            "context_end_char": 1_000,
            "relation_texts": ["甲 认识 乙"],
            "retrieval_channels": ["bm25_dense_rrf"],
        }
    )
    second = _evidence("chapter-1", "片段二", rank=2).model_copy(
        update={
            "context_start_char": 200,
            "context_end_char": 1_100,
            "relation_texts": ["乙 前往 丙"],
            "retrieval_channels": ["graph_expansion"],
        }
    )

    deduplicated = _deduplicate_context_windows([first, second])

    assert len(deduplicated) == 1
    assert deduplicated[0].relation_texts == ["甲 认识 乙", "乙 前往 丙"]
    assert deduplicated[0].retrieval_channels == [
        "bm25_dense_rrf",
        "graph_expansion",
    ]


def test_parent_context_keeps_child_and_bounds_adjacent_text() -> None:
    context = "前" * 600 + "命中" * 400 + "后" * 600
    evidence = _evidence("chapter-1", "命中" * 400).model_copy(
        update={
            "start_char": 600,
            "end_char": 1_400,
            "context_content": context,
            "context_start_char": 0,
            "context_end_char": len(context),
        }
    )

    bounded = _bound_parent_context(evidence)

    assert bounded.context_content is not None
    assert len(bounded.context_content) == 1_400
    assert "命中" * 400 in bounded.context_content
    assert bounded.context_start_char == 300
    assert bounded.context_end_char == 1_700
    assert bounded.context_source_ref == "manuscript:chapter-1:300-1700"


def test_context_assembly_prefers_complementary_graph_path_over_duplicate() -> None:
    first = _evidence("source-1", "秦浩轩用无形剑击杀耶律齐", rank=1).model_copy(
        update={
            "reranker_score": 0.99,
            "relation_texts": ["秦浩轩 使用无形剑击杀 耶律齐"],
        }
    )
    duplicate = _evidence("source-2", "耶律齐死于无形剑", rank=2).model_copy(
        update={
            "reranker_score": 0.988,
            "relation_texts": ["秦浩轩 击杀 耶律齐"],
        }
    )
    bridge = VectorGraphEvidence(
        source_type=VectorGraphSourceType.KNOWLEDGE_CARD,
        source_id="character-yelvqi",
        source_ref="knowledge:character-yelvqi",
        title="耶律齐",
        content="耶律齐师从夏云子。",
        content_sha256=hashlib.sha256("耶律齐师从夏云子。".encode()).hexdigest(),
        rank=3,
        reranker_score=0.982,
        retrieval_channels=["graph_expansion"],
        relation_texts=["秦浩轩 击杀 耶律齐", "耶律齐 师从 夏云子"],
    )

    selected = _select_context_evidences(
        "被秦浩轩用无形剑击杀的对手是谁的弟子？",
        [first, duplicate, bridge],
    )

    assert [item.source_id for item in selected] == ["source-1", "character-yelvqi"]


def test_context_assembly_drops_same_entity_pair_details_for_single_fact() -> None:
    first = _evidence("source-1", "秦浩轩给小猴取名小金", rank=1).model_copy(
        update={
            "reranker_score": 0.99,
            "relation_texts": ["秦浩轩 命名 小金"],
        }
    )
    duplicate_detail = _evidence("source-2", "小金跟随秦浩轩", rank=2).model_copy(
        update={
            "reranker_score": 0.989,
            "relation_texts": ["小金 跟随 秦浩轩"],
        }
    )

    selected = _select_context_evidences(
        "秦浩轩驯服并取名的小猴子叫什么？",
        [first, duplicate_detail],
    )

    assert [item.source_id for item in selected] == ["source-1"]


def test_context_assembly_keeps_lower_ranked_relation_that_supplies_answer_detail() -> (
    None
):
    identity = _evidence("source-1", "耶律齐是夏云子的弟子", rank=1).model_copy(
        update={
            "reranker_score": 0.99,
            "relation_texts": [
                "耶律齐 师从 夏云子",
                "秦浩轩 击杀 耶律齐",
            ],
        }
    )
    weapon = _evidence("source-2", "秦浩轩用无形剑击杀耶律齐", rank=2).model_copy(
        update={
            "reranker_score": 0.96,
            "relation_texts": ["秦浩轩 使用无形剑击杀 耶律齐"],
        }
    )

    selected = _select_context_evidences(
        "秦浩轩用哪件武器击杀了夏云子的弟子？",
        [identity, weapon],
    )

    assert [item.source_id for item in selected] == ["source-1", "source-2"]


def test_relation_projection_keeps_anchor_and_connected_answer_edge() -> None:
    relations = [
        "万毒魔尊 自爆形成 绝仙毒谷",
        "绝仙毒谷 位于 大屿山",
        "绝仙毒谷 困住 不死巫魔",
        "不死巫魔 被困于 绝仙毒谷",
        "秦浩轩 前往 绝仙毒谷",
    ]

    indexes = _relevant_relation_indexes(
        "被困在万毒魔尊自爆形成的毒谷中的魔头是谁？",
        relations,
    )

    assert indexes == [0, 3]


def test_knowledge_card_context_keeps_query_relations_and_drops_unrelated_clauses() -> (
    None
):
    content = (
        "知识类型：角色\n"
        "名称：秦浩轩\n"
        "摘要：秦浩轩早年在小屿山采药；秦浩轩驯养小金；"
        "秦浩轩后来修炼其他功法。\n"
        "来源方式：正文提取"
    )
    evidence = VectorGraphEvidence(
        source_type=VectorGraphSourceType.KNOWLEDGE_CARD,
        source_id="character-1",
        source_ref="knowledge:character-1",
        title="秦浩轩",
        content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        rank=1,
        relation_texts=["秦浩轩 修炼 天河道法", "秦浩轩 驯养 小金"],
    )

    projected = _knowledge_card_context("那只猴子是谁驯养的？", evidence)

    assert "秦浩轩 驯养 小金" in projected
    assert "秦浩轩驯养小金" in projected
    assert "小屿山采药" not in projected


def test_direct_fact_context_keeps_minimal_contiguous_relation_support_window() -> None:
    content = (
        "谷中还有其他法宝。"
        "不死巫魔向秦浩轩发出一道法诀。"
        "这是道心种魔大法。"
        "为了不让功法失传，我现在传授给你。"
        "远处还有一株金色植物。"
    )
    evidence = _evidence("chapter-1", content).model_copy(
        update={
            "context_content": content,
            "relation_texts": ["不死巫魔 向秦浩轩传授 道心种魔大法"],
        }
    )

    projected = _manuscript_fact_context(
        "秦浩轩修炼的核心魔功，最初是谁传给他的？",
        evidence,
    )

    assert "不死巫魔向秦浩轩发出一道法诀" in projected
    assert "这是道心种魔大法" in projected
    assert "我现在传授给你" in projected
    assert "其他法宝" not in projected
    assert "金色植物" not in projected


def test_context_relation_projection_keeps_only_the_query_relevant_band() -> None:
    evidence = _evidence("chapter-1", "正文").model_copy(
        update={
            "relation_ids": ["r1", "r2", "r3"],
            "relation_texts": [
                "李靖 指使 严冬毒害小金",
                "李靖 是 翔龙国三皇子",
                "李靖 竞争 张狂",
            ],
        }
    )

    projected = _project_context_relations(
        "李靖指使严冬毒害的猴子是谁驯养的？",
        evidence,
    )

    assert projected.relation_ids == ["r1"]
    assert projected.relation_texts == ["李靖 指使 严冬毒害小金"]


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
