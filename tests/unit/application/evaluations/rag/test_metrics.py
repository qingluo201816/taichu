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


def _evidence(
    source_id: str,
    rank: int,
    *,
    verified: bool = True,
    relation_texts: list[str] | None = None,
) -> VectorGraphEvidence:
    return VectorGraphEvidence(
        source_type=VectorGraphSourceType.KNOWLEDGE_CARD,
        source_id=source_id,
        source_ref=f"knowledge:{source_id}",
        title=source_id,
        content="事实",
        content_sha256="a" * 64,
        rank=rank,
        relation_texts=relation_texts or [],
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


def test_retrieval_metrics_use_bge_top_10_trace_before_context_budget() -> None:
    case = RAGGoldenCase(
        case_id="single-002",
        query="问题",
        category=RAGGoldenCategory.SINGLE_FACT,
        expected_source_ids=["source-a"],
        expected_claims=["事实"],
        reference_answer="答案",
    )
    result = VectorGraphRetrievalResult(
        query=case.query,
        evidences=[_evidence("noise", 1)],
        reranked_source_ids=["noise", "source-a"],
    )

    score = evaluate_case_retrieval(case, result, top_k=10)

    assert score.recall_at_k == 1.0
    assert score.mrr_at_k == 0.5


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
        evidences=[
            _evidence(
                "source-a",
                1,
                relation_texts=["秦浩轩  修炼 道心种魔大法", "无关 关系 噪声"],
            )
        ],
    )

    score = evaluate_case_retrieval(case, result, top_k=10)

    assert score.relation_recall_at_k == 0.5
    assert score.complete_path_recall == 0.0
    assert score.graph_expansion_noise_rate == 0.5


def test_graph_metrics_use_bge_top_10_relation_trace_before_context_budget() -> None:
    expected = RAGExpectedRelation(subject="秦浩轩", predicate="驯养", object="小金")
    case = RAGGoldenCase(
        case_id="graph-002",
        query="小金是谁驯养的？",
        category=RAGGoldenCategory.GRAPH_MULTI_HOP,
        graph_required=True,
        expected_source_ids=["source-a"],
        expected_relations=[expected],
        expected_path=[expected.relation_id],
        expected_claims=["秦浩轩驯养小金"],
        reference_answer="小金由秦浩轩驯养。",
    )
    result = VectorGraphRetrievalResult(
        query=case.query,
        evidences=[_evidence("source-a", 1)],
        reranked_relations=["秦浩轩 驯养 小金"],
    )

    score = evaluate_case_retrieval(case, result, top_k=10)

    assert score.relation_recall_at_k == 1.0
    assert score.complete_path_recall == 1.0


def test_complete_path_uses_bounded_graph_expansion_before_passage_rerank() -> None:
    first = RAGExpectedRelation(subject="秦浩轩", predicate="师从", object="璇玑子")
    second = RAGExpectedRelation(
        subject="璇玑子",
        predicate="亲自迎接",
        object="蒲汉忠",
    )
    case = RAGGoldenCase(
        case_id="graph-003",
        query="秦浩轩的师父亲自迎接了谁？",
        category=RAGGoldenCategory.GRAPH_MULTI_HOP,
        graph_required=True,
        expected_source_ids=["source-a"],
        expected_relations=[first, second],
        expected_path=[first.relation_id, second.relation_id],
        expected_claims=["璇玑子亲自迎接蒲汉忠"],
        reference_answer="璇玑子亲自迎接了蒲汉忠。",
    )
    result = VectorGraphRetrievalResult(
        query=case.query,
        evidences=[_evidence("source-a", 1)],
        reranked_relations=[first.text],
        expanded_relations=[first.text, second.text, "无关 关系 噪声"],
    )

    score = evaluate_case_retrieval(case, result, top_k=10)

    assert score.relation_recall_at_k == 0.5
    assert score.complete_path_recall == 1.0
    assert score.graph_expansion_noise_rate == 1 / 3


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
