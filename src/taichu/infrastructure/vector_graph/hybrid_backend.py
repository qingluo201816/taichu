"""BM25、Milvus Vector Graph RAG 与 BGE 重排的统一后端。"""

from __future__ import annotations

import re
import unicodedata

from taichu.application.vector_graph.models import (
    VectorGraphBuildPlan,
    VectorGraphBuildResult,
    VectorGraphEvidence,
    VectorGraphExtractedTriplets,
    VectorGraphIndexStatus,
    VectorGraphRetrievalResult,
    VectorGraphSourceDocument,
    VectorGraphSourceType,
)
from taichu.infrastructure.vector_graph.backend import MilvusVectorGraphBackend
from taichu.infrastructure.vector_graph.reranker import BGEReranker


_CONTEXT_RECONSTRUCTION_LIMIT = 3
_CONTEXT_EVIDENCE_LIMIT = 3
_PARENT_CONTEXT_MAX_CHARS = 1_400
_KNOWLEDGE_CONTEXT_RELATION_LIMIT = 2
_KNOWLEDGE_CONTEXT_CLAUSE_LIMIT = 1
_KNOWLEDGE_CONTEXT_MAX_CHARS = 700
_KNOWLEDGE_CONTEXT_MIN_CLAUSE_RELEVANCE = 3
_MANUSCRIPT_FACT_SENTENCE_WINDOW = 3
_MANUSCRIPT_FACT_CONTEXT_MAX_CHARS = 700
_MANUSCRIPT_FACT_MIN_SUPPORT_SCORE = 4
_CONTEXT_RERANKER_SCORE_MARGIN = 0.015
_CONTEXT_RELATION_REFINEMENT_SCORE_MARGIN = 0.05
_CONTEXT_RELATION_MIN_RELEVANCE = 2

_RELATION_QUERY_EXPANSIONS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("弟子", "师父", "师尊"), ("师从", "拜师", "收徒")),
    (("宗门", "势力", "门派"), ("属于", "隶属于", "归属")),
    (("指使", "谁让", "谁叫"), ("命令", "授意", "派遣")),
    (("被困", "困在"), ("被困于", "困住", "囚禁")),
    (("名字", "取名", "命名"), ("取名", "命名", "起名")),
    (("针对", "敌视", "敌对"), ("敌视", "敌对", "怨恨")),
    (("传给", "传授"), ("传给", "传授", "教授")),
    (("驯服", "驯养"), ("驯服", "驯养")),
)

_PREDICATE_CONCEPTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("mentor", ("师从", "拜师", "收徒", "弟子")),
    ("membership", ("属于", "隶属", "归属")),
    ("instruction", ("指使", "命令", "授意", "派遣")),
    ("trapped", ("被困", "困住", "囚禁")),
    ("naming", ("取名", "命名", "起名")),
    ("hostility", ("针对", "敌视", "敌对", "怨恨")),
    ("killing", ("击杀", "杀死", "杀害", "斩杀")),
    ("warning", ("警告", "威胁")),
    ("formation", ("形成", "导致", "造就")),
    ("transmission", ("传给", "传授", "教授")),
)


class HybridVectorGraphBackend:
    def __init__(
        self,
        *,
        milvus: MilvusVectorGraphBackend,
        reranker: BGEReranker,
        candidate_top_k: int = 30,
        final_top_k: int = 10,
    ) -> None:
        self._milvus = milvus
        self._reranker = reranker
        self.candidate_top_k = candidate_top_k
        self.final_top_k = final_top_k

    async def update(
        self,
        documents: list[VectorGraphSourceDocument],
        *,
        plan: VectorGraphBuildPlan,
        extracted_triplets: VectorGraphExtractedTriplets | None = None,
    ) -> VectorGraphBuildResult:
        result = await self._milvus.update(
            documents,
            plan=plan,
            extracted_triplets=extracted_triplets,
        )
        return result

    async def inspect(self, plan: VectorGraphBuildPlan) -> VectorGraphIndexStatus:
        return await self._milvus.inspect(plan)

    async def retrieve(self, query: str, *, top_k: int) -> VectorGraphRetrievalResult:
        graph_result = await self._milvus.retrieve(
            query,
            top_k=self.candidate_top_k,
        )
        final_top_k = min(top_k, self.final_top_k)
        all_reranked_evidences = await self._reranker.rerank(
            query,
            graph_result.evidences,
            top_k=len(graph_result.evidences),
        )
        reranked_evidences = all_reranked_evidences[:final_top_k]
        evidences = _select_context_evidences(query, all_reranked_evidences)
        reconstruction_candidates = [
            evidence
            for evidence in evidences
            if evidence.source_type is VectorGraphSourceType.MANUSCRIPT_CHUNK
        ][:_CONTEXT_RECONSTRUCTION_LIMIT]
        reconstructed = await self._milvus.expand_context(reconstruction_candidates)
        reconstructed_by_ref = {item.source_ref: item for item in reconstructed}
        evidences = [
            reconstructed_by_ref.get(evidence.source_ref, evidence)
            for evidence in evidences
        ]
        evidences = _deduplicate_context_windows(evidences)
        evidences = [
            _project_context_evidence(
                query,
                _project_context_relations(
                    query,
                    _bound_parent_context(evidence),
                ),
            )
            for evidence in evidences
        ]
        context_relations = list(
            dict.fromkeys(
                relation
                for evidence in evidences
                for relation in evidence.relation_texts
            )
        )
        return graph_result.model_copy(
            update={
                "evidences": evidences,
                "context_relations": context_relations,
                "reranked_passage_ids": [
                    item.passage_id for item in reranked_evidences
                ],
                "reranked_source_ids": [item.source_id for item in reranked_evidences],
                "reranked_relations": list(
                    dict.fromkeys(
                        relation
                        for item in reranked_evidences
                        for relation in item.relation_texts
                    )
                ),
                "source_refs": list(
                    dict.fromkeys(item.source_ref for item in evidences)
                ),
            }
        )

    async def close(self) -> None:
        await self._milvus.close()


def _deduplicate_context_windows(
    evidences: list[VectorGraphEvidence],
) -> list[VectorGraphEvidence]:
    """合并重建后高度重叠的上下文，保留不同情节窗口。"""

    output: list[VectorGraphEvidence] = []
    for evidence in evidences:
        duplicate_index = next(
            (
                index
                for index, current in enumerate(output)
                if _same_context_window(current, evidence)
            ),
            None,
        )
        if duplicate_index is None:
            output.append(evidence)
            continue
        current = output[duplicate_index]
        output[duplicate_index] = current.model_copy(
            update={
                "relation_ids": list(
                    dict.fromkeys([*current.relation_ids, *evidence.relation_ids])
                ),
                "relation_texts": list(
                    dict.fromkeys([*current.relation_texts, *evidence.relation_texts])
                ),
                "retrieval_channels": list(
                    dict.fromkeys(
                        [*current.retrieval_channels, *evidence.retrieval_channels]
                    )
                ),
            }
        )
    return [
        evidence.model_copy(update={"rank": rank})
        for rank, evidence in enumerate(output, start=1)
    ]


def _select_context_evidences(
    query: str,
    evidences: list[VectorGraphEvidence],
) -> list[VectorGraphEvidence]:
    """从一次 BGE 排序中选择最多三条互补证据，避免重复上下文。"""

    if not evidences:
        return []
    if not any(evidence.relation_texts for evidence in evidences):
        return list(evidences[:_CONTEXT_EVIDENCE_LIMIT])

    selected = [evidences[0]]
    covered_signatures = _evidence_relation_signatures(query, evidences[0])
    covered_relations = {
        evidences[0].relation_texts[index]
        for index in _relevant_relation_indexes(query, evidences[0].relation_texts)
    }
    covered_nodes = _signature_nodes(covered_signatures)
    covered_edges = {(subject, object_) for subject, object_, _ in covered_signatures}
    frontier_nodes = _initial_context_frontier(query, evidences[0])
    follows_unknown_frontier = bool(frontier_nodes)
    allows_same_edge_detail = _query_requests_multiple_aspects(query)
    best_score = evidences[0].reranker_score

    while len(selected) < _CONTEXT_EVIDENCE_LIMIT:
        candidates: list[
            tuple[
                tuple[int, int, int, float, int],
                VectorGraphEvidence,
                set[tuple[str, str, str]],
                set[str],
            ]
        ] = []
        for evidence in evidences[1:]:
            if evidence in selected:
                continue
            indexes = _relevant_relation_indexes(query, evidence.relation_texts)
            if not indexes:
                continue
            relations = [evidence.relation_texts[index] for index in indexes]
            relation_relevances = [
                _query_relation_relevance(query, relation) for relation in relations
            ]
            if max(relation_relevances, default=0) < _CONTEXT_RELATION_MIN_RELEVANCE:
                continue
            signatures = {_relation_signature(relation) for relation in relations}
            novel_signatures = signatures.difference(covered_signatures)
            refinements = {
                relation
                for relation in relations
                if _relation_adds_detail(relation, covered_relations)
            }
            if not novel_signatures and not refinements:
                continue
            within_default_band = _within_context_score_band(
                evidence.reranker_score,
                best_score,
            )
            within_refinement_band = bool(refinements) and _within_context_score_band(
                evidence.reranker_score,
                best_score,
                margin=_CONTEXT_RELATION_REFINEMENT_SCORE_MARGIN,
            )
            if not within_default_band and not within_refinement_band:
                continue
            has_novel_edge = any(
                not _edge_is_covered(subject, object_, covered_edges)
                for subject, object_, _predicate in novel_signatures
            )
            if not has_novel_edge and not allows_same_edge_detail and not refinements:
                continue
            candidate_signatures = novel_signatures or signatures
            novel_nodes = _signature_nodes(candidate_signatures)
            connected = int(_node_sets_intersect(covered_nodes, novel_nodes))
            if frontier_nodes and not _node_sets_intersect(
                frontier_nodes,
                novel_nodes,
            ):
                continue
            compact = int(evidence.source_type is VectorGraphSourceType.KNOWLEDGE_CARD)
            candidates.append(
                (
                    (
                        connected,
                        compact,
                        max(relation_relevances),
                        evidence.reranker_score or 0.0,
                        -evidence.rank,
                    ),
                    evidence,
                    novel_signatures,
                    set(relations),
                )
            )
        if not candidates:
            break
        _, evidence, novel_signatures, candidate_relations = max(
            candidates,
            key=lambda item: item[0],
        )
        selected.append(evidence)
        previous_nodes = set(covered_nodes)
        covered_signatures.update(novel_signatures)
        covered_relations.update(candidate_relations)
        covered_edges.update(
            (subject, object_) for subject, object_, _predicate in novel_signatures
        )
        covered_nodes.update(_signature_nodes(novel_signatures))
        new_nodes = covered_nodes.difference(previous_nodes)
        new_frontier = _unmatched_query_nodes(query, new_nodes)
        if follows_unknown_frontier and new_frontier:
            frontier_nodes = new_frontier

    return selected


def _within_context_score_band(
    score: float | None,
    best_score: float | None,
    *,
    margin: float = _CONTEXT_RERANKER_SCORE_MARGIN,
) -> bool:
    if score is None or best_score is None:
        return True
    return score >= best_score - margin


def _evidence_relation_signatures(
    query: str,
    evidence: VectorGraphEvidence,
) -> set[tuple[str, str, str]]:
    return {
        _relation_signature(evidence.relation_texts[index])
        for index in _relevant_relation_indexes(query, evidence.relation_texts)
    }


def _signature_nodes(signatures: set[tuple[str, str, str]]) -> set[str]:
    return {
        node
        for subject, object_, _predicate in signatures
        for node in (subject, object_)
        if node
    }


def _unmatched_query_nodes(query: str, nodes: set[str]) -> set[str]:
    return {node for node in nodes if _text_relevance(query, node) == 0}


def _initial_context_frontier(
    query: str,
    evidence: VectorGraphEvidence,
) -> set[str]:
    indexes = _relevant_relation_indexes(query, evidence.relation_texts)
    if not indexes:
        return set()
    return _unmatched_query_nodes(
        query, _relation_nodes(evidence.relation_texts[indexes[0]])
    )


def _node_sets_intersect(left: set[str], right: set[str]) -> bool:
    return any(
        _nodes_match(left_node, right_node)
        for left_node in left
        for right_node in right
    )


def _nodes_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right or left in right or right in left:
        return True
    left_bigrams = {left[index : index + 2] for index in range(len(left) - 1)}
    right_bigrams = {right[index : index + 2] for index in range(len(right) - 1)}
    return len(left_bigrams.intersection(right_bigrams)) >= 2


def _edge_is_covered(
    subject: str,
    object_: str,
    covered_edges: set[tuple[str, str]],
) -> bool:
    return any(
        (
            _nodes_match(subject, covered_subject)
            and _nodes_match(object_, covered_object)
        )
        or (
            _nodes_match(subject, covered_object)
            and _nodes_match(object_, covered_subject)
        )
        for covered_subject, covered_object in covered_edges
    )


def _relation_adds_detail(relation: str, covered_relations: set[str]) -> bool:
    compact_relation = _compact_text(relation)
    if any(_compact_text(covered) == compact_relation for covered in covered_relations):
        return False
    signature = _relation_signature(relation)
    predicate = _relation_predicate(relation)
    if not predicate:
        return False
    return any(
        _relation_signature(covered) == signature
        and (covered_predicate := _relation_predicate(covered))
        and covered_predicate in predicate
        and len(predicate) >= len(covered_predicate) + 2
        for covered in covered_relations
    )


def _query_requests_multiple_aspects(query: str) -> bool:
    compact_query = _compact_text(query)
    return "，" in query or ("为什么" in compact_query and "做了什么" in compact_query)


def _project_context_evidence(
    query: str,
    evidence: VectorGraphEvidence,
) -> VectorGraphEvidence:
    """知识卡投影摘要；直接事实问句从 Parent–Child 窗口提取连续原文。"""

    if evidence.source_type is VectorGraphSourceType.KNOWLEDGE_CARD:
        return evidence.model_copy(
            update={"context_content": _knowledge_card_context(query, evidence)}
        )
    if (
        evidence.source_type is VectorGraphSourceType.MANUSCRIPT_CHUNK
        and evidence.relation_texts
        and _is_direct_fact_query(query)
    ):
        return evidence.model_copy(
            update={"context_content": _manuscript_fact_context(query, evidence)}
        )
    return evidence


def _project_context_relations(
    query: str,
    evidence: VectorGraphEvidence,
) -> VectorGraphEvidence:
    selected_indexes = _relevant_relation_indexes(query, evidence.relation_texts)
    if not selected_indexes:
        return evidence.model_copy(update={"relation_ids": [], "relation_texts": []})
    relation_ids = (
        [evidence.relation_ids[index] for index in selected_indexes]
        if len(evidence.relation_ids) == len(evidence.relation_texts)
        else evidence.relation_ids
    )
    return evidence.model_copy(
        update={
            "relation_ids": relation_ids,
            "relation_texts": [
                evidence.relation_texts[index] for index in selected_indexes
            ],
        }
    )


def _bound_parent_context(evidence: VectorGraphEvidence) -> VectorGraphEvidence:
    """保留命中子块及相邻文本，但不把三个完整子块全部送入模型。"""

    context = evidence.context_content
    context_start = evidence.context_start_char
    context_end = evidence.context_end_char
    child_start = evidence.start_char
    child_end = evidence.end_char
    if (
        context is None
        or len(context) <= _PARENT_CONTEXT_MAX_CHARS
        or context_start is None
        or context_end is None
        or child_start is None
        or child_end is None
    ):
        return evidence
    relative_child_start = max(0, child_start - context_start)
    relative_child_end = min(len(context), child_end - context_start)
    if relative_child_end <= relative_child_start:
        return evidence
    surrounding_budget = max(
        0,
        _PARENT_CONTEXT_MAX_CHARS - (relative_child_end - relative_child_start),
    )
    slice_start = max(0, relative_child_start - surrounding_budget // 2)
    slice_end = min(len(context), slice_start + _PARENT_CONTEXT_MAX_CHARS)
    if slice_end < relative_child_end:
        slice_end = relative_child_end
        slice_start = max(0, slice_end - _PARENT_CONTEXT_MAX_CHARS)
    if slice_end - slice_start < _PARENT_CONTEXT_MAX_CHARS:
        slice_start = max(0, slice_end - _PARENT_CONTEXT_MAX_CHARS)
    bounded_start = context_start + slice_start
    bounded_end = context_start + slice_end
    return evidence.model_copy(
        update={
            "context_content": context[slice_start:slice_end],
            "context_source_ref": (
                f"manuscript:{evidence.source_id}:{bounded_start}-{bounded_end}"
            ),
            "context_start_char": bounded_start,
            "context_end_char": bounded_end,
        }
    )


def _knowledge_card_context(query: str, evidence: VectorGraphEvidence) -> str:
    relevant_relations = [
        evidence.relation_texts[index]
        for index in _relevant_relation_indexes(query, evidence.relation_texts)
    ]
    focus = " ".join([query, *relevant_relations])
    clauses = _knowledge_clauses(evidence.content)
    ranked_clauses = sorted(
        enumerate(clauses),
        key=lambda item: (-_text_relevance(focus, item[1]), item[0]),
    )
    selected_indexes = sorted(
        index
        for index, clause in ranked_clauses[:_KNOWLEDGE_CONTEXT_CLAUSE_LIMIT]
        if _text_relevance(focus, clause) >= _KNOWLEDGE_CONTEXT_MIN_CLAUSE_RELEVANCE
    )
    selected_clauses = [clauses[index] for index in selected_indexes]
    sections = [f"标题：{evidence.title}"]
    if relevant_relations:
        sections.append("相关图关系：" + "；".join(relevant_relations))
    if selected_clauses:
        sections.append("相关内容：" + "；".join(selected_clauses))
    projected = "\n".join(sections)
    return projected[:_KNOWLEDGE_CONTEXT_MAX_CHARS].rstrip("；")


def _knowledge_clauses(content: str) -> list[str]:
    return [
        clause.strip()
        for clause in re.split(r"[，；。！？\n]+", content)
        if clause.strip()
        and not clause.startswith(("知识类型：", "来源方式：", "来源说明："))
    ]


def _manuscript_fact_context(query: str, evidence: VectorGraphEvidence) -> str:
    source = evidence.context_content or evidence.content
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[。！？])|[\r\n]+", source)
        if len(_compact_text(sentence)) >= 2
    ]
    if not sentences:
        return source[:_MANUSCRIPT_FACT_CONTEXT_MAX_CHARS]

    candidates: list[tuple[tuple[int, int, int, int], str]] = []
    for start in range(len(sentences)):
        for size in range(1, _MANUSCRIPT_FACT_SENTENCE_WINDOW + 1):
            window_sentences = sentences[start : start + size]
            if not window_sentences:
                continue
            window = "\n".join(window_sentences)
            candidates.append(
                (
                    (
                        _relation_support_score(evidence.relation_texts, window),
                        _text_relevance(query, window),
                        -len(window),
                        -start,
                    ),
                    window,
                )
            )
    score, selected = max(candidates, key=lambda item: item[0])
    if score[0] < _MANUSCRIPT_FACT_MIN_SUPPORT_SCORE:
        return source[:_MANUSCRIPT_FACT_CONTEXT_MAX_CHARS]
    return selected[:_MANUSCRIPT_FACT_CONTEXT_MAX_CHARS]


def _relation_support_score(relations: list[str], text: str) -> int:
    compact_text = _compact_text(text)
    score = 0
    for relation in relations:
        parts = relation.split()
        if len(parts) < 3:
            continue
        subject = _compact_text(parts[0])
        object_ = _compact_text(parts[-1])
        predicate = _relation_predicate(relation)
        score += 2 if subject and subject in compact_text else 0
        score += 2 if object_ and object_ in compact_text else 0
        if predicate and predicate in compact_text:
            score += 4
            continue
        for _concept, aliases in _PREDICATE_CONCEPTS:
            if any(
                (compact_alias := _compact_text(alias)) in predicate
                and compact_alias in compact_text
                for alias in aliases
            ):
                score += 3
                break
    return score


def _is_direct_fact_query(query: str) -> bool:
    compact_query = _compact_text(query)
    if not any(
        marker in compact_query
        for marker in ("谁", "什么", "哪", "何时", "什么时候", "多少", "是否")
    ):
        return False
    return not any(
        marker in compact_query
        for marker in (
            "为什么",
            "为何",
            "原因",
            "动机",
            "如何",
            "怎样",
            "经历",
            "过程",
            "变化",
            "做了什么",
            "对此",
        )
    )


def _relevant_relation_indexes(query: str, relations: list[str]) -> list[int]:
    ranked = sorted(
        (
            (_query_relation_relevance(query, relation), index)
            for index, relation in enumerate(relations)
        ),
        key=lambda item: (-item[0], item[1]),
    )
    if not ranked or ranked[0][0] <= 0:
        return []
    selected = [ranked[0][1]]
    selected_signatures = {_relation_signature(relations[selected[0]])}
    selected_nodes = _relation_nodes(relations[selected[0]])
    frontier = _least_query_matched_nodes(query, selected_nodes)
    allows_multiple_aspects = _query_requests_multiple_aspects(query)

    while len(selected) < _KNOWLEDGE_CONTEXT_RELATION_LIMIT:
        choices: list[tuple[tuple[int, int, int, int], int]] = []
        for score, index in ranked:
            if index in selected:
                continue
            if score < _CONTEXT_RELATION_MIN_RELEVANCE:
                continue
            if (
                _query_predicate_relevance(query, relations[index])
                < _CONTEXT_RELATION_MIN_RELEVANCE
                and not allows_multiple_aspects
            ):
                continue
            signature = _relation_signature(relations[index])
            if signature in selected_signatures:
                continue
            nodes = _relation_nodes(relations[index])
            shared_frontier = _node_sets_intersect(frontier, nodes)
            shared_path = _node_sets_intersect(selected_nodes, nodes)
            if not shared_path and score < max(
                _CONTEXT_RELATION_MIN_RELEVANCE,
                ranked[0][0] - 1,
            ):
                continue
            if frontier and not shared_frontier:
                continue
            new_nodes = nodes.difference(selected_nodes)
            choices.append(
                (
                    (
                        int(shared_frontier),
                        int(shared_path),
                        score,
                        len(new_nodes),
                    ),
                    index,
                )
            )
        if not choices:
            break
        _, index = max(choices, key=lambda item: (item[0], -item[1]))
        nodes = _relation_nodes(relations[index])
        new_nodes = nodes.difference(selected_nodes)
        selected.append(index)
        selected_signatures.add(_relation_signature(relations[index]))
        selected_nodes.update(nodes)
        frontier = new_nodes or nodes

    return selected


def _query_relation_relevance(query: str, relation: str) -> int:
    compact_query = _compact_text(query)
    matched_expansions = [
        aliases
        for triggers, aliases in _RELATION_QUERY_EXPANSIONS
        if any(_compact_text(trigger) in compact_query for trigger in triggers)
    ]
    expansions = [alias for aliases in matched_expansions for alias in aliases]
    score = _text_relevance(" ".join([query, *expansions]), relation)
    compact_relation = _compact_text(relation)
    if any(
        any(_compact_text(alias) in compact_relation for alias in aliases)
        for aliases in matched_expansions
    ):
        score += 2
    return score


def _query_predicate_relevance(query: str, relation: str) -> int:
    predicate = _relation_predicate(relation)
    if not predicate:
        return 0
    compact_query = _compact_text(query)
    matched_expansions = [
        aliases
        for triggers, aliases in _RELATION_QUERY_EXPANSIONS
        if any(_compact_text(trigger) in compact_query for trigger in triggers)
    ]
    expansions = [alias for aliases in matched_expansions for alias in aliases]
    score = _text_relevance(" ".join([query, *expansions]), predicate)
    if any(
        any(_compact_text(alias) in predicate for alias in aliases)
        for aliases in matched_expansions
    ):
        score += 2
    return score


def _least_query_matched_nodes(query: str, nodes: set[str]) -> set[str]:
    if not nodes:
        return set()
    scores = {node: _text_relevance(query, node) for node in nodes}
    return {node for node, score in scores.items() if score == 0}


def _relation_nodes(relation: str) -> set[str]:
    parts = relation.split()
    if len(parts) < 3:
        return set()
    return {_compact_text(parts[0]), _compact_text(parts[-1])}


def _relation_signature(relation: str) -> tuple[str, str, str]:
    parts = relation.split()
    if len(parts) < 3:
        compact = _compact_text(relation)
        return (compact, compact, compact)
    endpoints = sorted((_compact_text(parts[0]), _compact_text(parts[-1])))
    predicate = _relation_predicate(relation)
    predicate_concept = next(
        (
            concept
            for concept, aliases in _PREDICATE_CONCEPTS
            if any(_compact_text(alias) in predicate for alias in aliases)
        ),
        predicate,
    )
    return (endpoints[0], endpoints[1], predicate_concept)


def _text_relevance(focus: str, candidate: str) -> int:
    focus_text = _compact_text(focus)
    candidate_text = _compact_text(candidate)
    if not focus_text or not candidate_text:
        return 0
    focus_bigrams = {
        focus_text[index : index + 2] for index in range(len(focus_text) - 1)
    }
    candidate_bigrams = {
        candidate_text[index : index + 2] for index in range(len(candidate_text) - 1)
    }
    score = len(focus_bigrams.intersection(candidate_bigrams))
    if candidate_text in focus_text or focus_text in candidate_text:
        score += 4
    return score


def _relation_predicate(relation: str) -> str:
    parts = relation.split()
    if len(parts) < 3:
        return ""
    return _compact_text("".join(parts[1:-1]))


def _compact_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(re.findall(r"[\w\u4e00-\u9fff]", normalized)).replace("_", "")


def _same_context_window(
    left: VectorGraphEvidence,
    right: VectorGraphEvidence,
) -> bool:
    if left.source_type is not right.source_type or left.source_id != right.source_id:
        return False
    if left.source_type is not VectorGraphSourceType.MANUSCRIPT_CHUNK:
        return True
    left_start = left.context_start_char
    left_end = left.context_end_char
    right_start = right.context_start_char
    right_end = right.context_end_char
    if None in {left_start, left_end, right_start, right_end}:
        return left.source_ref == right.source_ref
    assert left_start is not None and left_end is not None
    assert right_start is not None and right_end is not None
    overlap = min(left_end, right_end) - max(left_start, right_start)
    if overlap <= 0:
        return False
    shorter = min(left_end - left_start, right_end - right_start)
    return shorter > 0 and (overlap / shorter) >= 0.65
