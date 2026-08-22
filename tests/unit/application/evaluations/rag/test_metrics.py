from taichu.application.evaluations.rag.metrics import evaluate_case_retrieval
from taichu.application.evaluations.rag.models import (
    RAGExpectedRelation,
    RAGGoldenCase,
    RAGGoldenCategory,
)
from taichu.application.vector_graph.models import (
    VectorGraphEvidence,
    VectorGraphRetrievalResult,
    VectorGraphSourceType,
)


def _evidence(source_id: str, rank: int, *, verified: bool = True) -> VectorGraphEvidence:
    return VectorGraphEvidence(
        source_type=VectorGraphSourceType.KNOWLEDGE_CARD,
        source_id=source_id,
        source_ref=f"knowledge:{source_id}",
        title=source_id,
        content="事实",
        content_sha256="a" * 64,
        rank=rank,
        authority_verified=verified,
    )


def test_retrieval_metrics_use_unique_sources_and_first_relevant_rank() -> None:
    case = RAGGoldenCase(
        case_id="single-001",
        query="问题",
        category=RAGGoldenCategory.SINGLE_FACT,
        expected_source_ids=["source-a", "source-b"],
        expected_claims=["事实"],
        reference_answer="答案",
    )
    result = VectorGraphRetrievalResult(
        query=case.query,
        evidences=[
            _evidence("noise", 1),
            _evidence("source-a", 2),
            _evidence("source-a", 3),
            _evidence("source-b", 4),
        ],
    )

    score = evaluate_case_retrieval(case, result, top_k=10)

    assert score.recall_at_k == 1.0
    assert score.mrr_at_k == 0.5
    assert score.authority_verified is True


def test_graph_metrics_require_every_expected_relation_in_the_complete_path() -> None:
    first = RAGExpectedRelation(subject="秦浩轩", predicate="修炼", object="道心种魔大法")
    second = RAGExpectedRelation(subject="道心种魔大法", predicate="传自", object="蒲汉忠")
    case = RAGGoldenCase(
        case_id="graph-001",
        query="问题",
        category=RAGGoldenCategory.GRAPH_MULTI_HOP,
        graph_required=True,
        expected_source_ids=["source-a"],
        expected_relations=[first, second],
        expected_path=[first.relation_id, second.relation_id],
        expected_claims=["事实"],
        reference_answer="答案",
    )
    result = VectorGraphRetrievalResult(
        query=case.query,
        evidences=[_evidence("source-a", 1)],
        reranked_relations=["秦浩轩  修炼 道心种魔大法", "无关 关系 噪声"],
    )

    score = evaluate_case_retrieval(case, result, top_k=10)

    assert score.relation_recall_at_k == 0.5
    assert score.complete_path_recall == 0.0
    assert score.graph_expansion_noise_rate == 0.5


def test_hard_negative_with_no_expected_source_marks_retrieval_metrics_not_applicable() -> None:
    case = RAGGoldenCase(
        case_id="negative-001",
        query="不存在的事实？",
        category=RAGGoldenCategory.HARD_NEGATIVE,
        expected_source_ids=[],
        expected_claims=["证据不足"],
        reference_answer="现有资料无法确认。",
    )

    score = evaluate_case_retrieval(
        case,
        VectorGraphRetrievalResult(query=case.query),
        top_k=10,
    )

    assert score.recall_at_k is None
    assert score.mrr_at_k is None
    assert score.authority_verified is True
