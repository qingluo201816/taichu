"""Retriever、Graph 与权威来源的确定性指标。"""

from __future__ import annotations

from taichu.application.evaluations.rag.models import (
    RAGCaseScore,
    RAGGoldenCase,
    stable_relation_id,
)
from taichu.application.vector_graph.models import VectorGraphRetrievalResult


def evaluate_case_retrieval(
    case: RAGGoldenCase,
    result: VectorGraphRetrievalResult,
    *,
    top_k: int = 10,
) -> RAGCaseScore:
    evidences = result.evidences[:top_k]
    ranked_source_ids = result.reranked_source_ids[:top_k] or [
        item.source_id for item in evidences
    ]
    retrieved_sources = list(dict.fromkeys(ranked_source_ids))
    expected_sources = set(case.expected_source_ids)
    if expected_sources:
        matched_sources = expected_sources.intersection(retrieved_sources)
        recall = len(matched_sources) / len(expected_sources)
        first_rank = next(
            (
                index
                for index, source_id in enumerate(ranked_source_ids, start=1)
                if source_id in expected_sources
            ),
            None,
        )
        mrr = 0.0 if first_rank is None else 1.0 / first_rank
    else:
        recall = None
        mrr = None

    reranked_relations = result.reranked_relations or list(
        dict.fromkeys(
            relation for evidence in evidences for relation in evidence.relation_texts
        )
    )
    if not reranked_relations:
        reranked_relations = result.context_relations
    reranked_relation_ids = list(
        dict.fromkeys(stable_relation_id(text) for text in reranked_relations)
    )
    expansion_relations = result.expanded_relations or reranked_relations
    expansion_relation_ids = list(
        dict.fromkeys(stable_relation_id(text) for text in expansion_relations)
    )
    expected_relation_ids = {item.relation_id for item in case.expected_relations}
    if expected_relation_ids:
        matched_relations = expected_relation_ids.intersection(reranked_relation_ids)
        relation_recall = len(matched_relations) / len(expected_relation_ids)
        complete_path = float(
            set(case.expected_path).issubset(expansion_relation_ids)
        )
        noise = (
            len(set(expansion_relation_ids).difference(expected_relation_ids))
            / len(expansion_relation_ids)
            if expansion_relation_ids
            else 0.0
        )
    else:
        relation_recall = None
        complete_path = None
        noise = None

    return RAGCaseScore(
        case_id=case.case_id,
        recall_at_k=recall,
        mrr_at_k=mrr,
        authority_verified=all(item.authority_verified for item in evidences),
        relation_recall_at_k=relation_recall,
        complete_path_recall=complete_path,
        graph_expansion_noise_rate=noise,
        retrieved_source_ids=retrieved_sources,
        retrieved_relation_ids=reranked_relation_ids,
    )
