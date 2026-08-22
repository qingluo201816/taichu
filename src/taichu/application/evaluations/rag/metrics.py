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
    retrieved_sources = list(dict.fromkeys(item.source_id for item in evidences))
    expected_sources = set(case.expected_source_ids)
    if expected_sources:
        matched_sources = expected_sources.intersection(retrieved_sources)
        recall = len(matched_sources) / len(expected_sources)
        first_rank = next(
            (
                index
                for index, evidence in enumerate(evidences, start=1)
                if evidence.source_id in expected_sources
            ),
            None,
        )
        mrr = 0.0 if first_rank is None else 1.0 / first_rank
    else:
        recall = None
        mrr = None

    relation_ids = list(
        dict.fromkeys(stable_relation_id(text) for text in result.reranked_relations[:top_k])
    )
    expected_relation_ids = {item.relation_id for item in case.expected_relations}
    if expected_relation_ids:
        matched_relations = expected_relation_ids.intersection(relation_ids)
        relation_recall = len(matched_relations) / len(expected_relation_ids)
        complete_path = float(set(case.expected_path).issubset(relation_ids))
        noise = (
            len(set(relation_ids).difference(expected_relation_ids)) / len(relation_ids)
            if relation_ids
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
        retrieved_relation_ids=relation_ids,
    )
