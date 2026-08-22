"""面向小说高连接实体的 Query-aware 受控图扩展。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, fields
from typing import Any

from vector_graph_rag.graph.retriever import (  # type: ignore[import-untyped]
    GraphRetriever,
    RetrievalResult,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ControlledExpansionSettings:
    """Graph Expansion 的查询级硬预算。"""

    max_seed_entities: int = 3
    initial_relations_per_entity: int = 20
    initial_beam_width: int = 20
    max_hop: int = 2
    max_entities_per_hop: int = 12
    relations_per_entity: int = 8
    hub_relations_per_entity: int = 5
    hub_degree_threshold: int = 100
    beam_width: int = 20
    max_total_relations: int = 60

    def __post_init__(self) -> None:
        for item in fields(self):
            name = item.name
            value = getattr(self, name)
            if value < 1:
                raise ValueError(f"Graph Expansion 配置 {name} 必须大于零。")
        if self.hub_relations_per_entity > self.relations_per_entity:
            raise ValueError("Hub 实体关系预算不得大于普通实体关系预算。")


@dataclass(frozen=True, slots=True)
class _RelationCandidate:
    relation_id: str
    text: str
    entity_ids: tuple[str, ...]
    passage_ids: tuple[str, ...]
    edge_score: float
    path_score: float


class ControlledGraphRetriever(GraphRetriever):
    """保留上游种子检索，仅替换无界 ``SubGraph.expand``。"""

    def __init__(self, *args: Any, expansion: ControlledExpansionSettings, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.expansion = expansion

    def retrieve(  # noqa: PLR0913
        self,
        query: str,
        entity_top_k: int | None = None,
        relation_top_k: int | None = None,
        entity_similarity_threshold: float | None = None,
        relation_similarity_threshold: float | None = None,
        expansion_degree: int | None = None,
        relation_number_threshold: int | None = None,
        filter: str | None = None,
    ) -> RetrievalResult:
        allowed_passage_ids = self._get_allowed_passage_ids(filter)
        query_entities = self._extract_query_entities(query)
        entity_ids, entity_texts, entity_scores = self._retrieve_entities(
            query_entities,
            top_k=entity_top_k,
            similarity_threshold=entity_similarity_threshold,
        )
        relation_ids, relation_texts, relation_scores = self._retrieve_relations(
            query,
            top_k=relation_top_k,
            similarity_threshold=relation_similarity_threshold,
        )
        relation_ids, relation_texts, relation_scores = (
            self._filter_relation_results_by_passage_ids(
                relation_ids,
                relation_texts,
                relation_scores,
                allowed_passage_ids,
            )
        )

        configured_total = relation_number_threshold or self.settings.relation_number_threshold
        total_budget = min(configured_total, self.expansion.max_total_relations)
        hop_budget = min(
            expansion_degree if expansion_degree is not None else self.expansion.max_hop,
            self.expansion.max_hop,
        )
        expanded = self._expand_controlled(
            query=query,
            seed_entity_ids=entity_ids[: self.expansion.max_seed_entities],
            relation_ids=relation_ids,
            relation_texts=relation_texts,
            relation_scores=relation_scores,
            allowed_passage_ids=allowed_passage_ids,
            max_hop=max(0, hop_budget),
            total_budget=total_budget,
        )
        expanded_ids = [item.relation_id for item in expanded]
        expanded_texts = [item.text for item in expanded]

        return RetrievalResult(
            entity_ids=entity_ids,
            entity_texts=entity_texts,
            entity_scores=entity_scores,
            relation_ids=relation_ids,
            relation_texts=relation_texts,
            relation_scores=relation_scores,
            subgraph=None,
            expanded_relation_ids=expanded_ids,
            expanded_relation_texts=expanded_texts,
            query=query,
            query_entities=query_entities,
            eviction_before_count=len(expanded_ids),
            eviction_after_count=len(expanded_ids),
            eviction_occurred=False,
        )

    def _expand_controlled(
        self,
        *,
        query: str,
        seed_entity_ids: list[str],
        relation_ids: list[str],
        relation_texts: list[str],
        relation_scores: list[float],
        allowed_passage_ids: set[str] | None,
        max_hop: int,
        total_budget: int,
    ) -> list[_RelationCandidate]:
        query_embedding = self.embedding_model.embed(query)
        candidates: dict[str, _RelationCandidate] = {}

        direct_records = {
            str(item["id"]): item
            for item in self.store._get_relations_by_ids(relation_ids)
        }
        for relation_id, text, score in zip(
            relation_ids,
            relation_texts,
            relation_scores,
            strict=True,
        ):
            record = direct_records.get(relation_id, {})
            candidate = _candidate_from_record(
                record,
                relation_id=relation_id,
                fallback_text=text,
                edge_score=score,
                path_score=score,
            )
            if _is_allowed(candidate, allowed_passage_ids):
                _keep_best(candidates, candidate)

        seed_records = self.store._get_entities_by_ids(seed_entity_ids)
        for record in seed_records:
            neighbor_results = self.store.search_neighbor_relations(
                query_embedding,
                list(record.get("relation_ids", [])),
                top_k=self.expansion.initial_relations_per_entity,
            )
            for result in neighbor_results:
                candidate = _candidate_from_search_result(result)
                if _is_allowed(candidate, allowed_passage_ids):
                    _keep_best(candidates, candidate)

        initial = _ranked(candidates.values())[: min(self.expansion.initial_beam_width, total_budget)]
        accepted: dict[str, _RelationCandidate] = {
            item.relation_id: item for item in initial
        }
        visited_entities = set(seed_entity_ids)
        frontier = _frontier_from_relations(initial, visited_entities)
        hop_counts: list[int] = []

        for _hop in range(max_hop):
            if len(accepted) >= total_budget or not frontier:
                break
            selected_frontier = sorted(
                frontier.items(),
                key=lambda item: (-item[1], item[0]),
            )[: self.expansion.max_entities_per_hop]
            frontier_ids = [entity_id for entity_id, _score in selected_frontier]
            visited_entities.update(frontier_ids)
            entity_records = {
                str(item["id"]): item
                for item in self.store._get_entities_by_ids(frontier_ids)
            }
            next_candidates: dict[str, _RelationCandidate] = {}

            for entity_id, parent_score in selected_frontier:
                entity = entity_records.get(entity_id)
                if entity is None:
                    continue
                relation_neighbors = list(entity.get("relation_ids", []))
                per_entity_limit = (
                    self.expansion.hub_relations_per_entity
                    if len(relation_neighbors) >= self.expansion.hub_degree_threshold
                    else self.expansion.relations_per_entity
                )
                results = self.store.search_neighbor_relations(
                    query_embedding,
                    relation_neighbors,
                    top_k=per_entity_limit,
                )
                for result in results:
                    candidate = _candidate_from_search_result(
                        result,
                        parent_score=parent_score,
                    )
                    if candidate.relation_id in accepted:
                        continue
                    if _is_allowed(candidate, allowed_passage_ids):
                        _keep_best(next_candidates, candidate)

            beam = _ranked(next_candidates.values())[: self.expansion.beam_width]
            remaining = total_budget - len(accepted)
            admitted = beam[:remaining]
            for candidate in admitted:
                accepted[candidate.relation_id] = candidate
            hop_counts.append(len(admitted))
            frontier = _frontier_from_relations(admitted, visited_entities)

        ordered = _ranked(accepted.values())[:total_budget]
        logger.info(
            "Controlled Graph Expansion: seeds=%d direct=%d initial=%d hops=%s total=%d budget=%d",
            len(seed_entity_ids),
            len(relation_ids),
            len(initial),
            hop_counts,
            len(ordered),
            total_budget,
        )
        return ordered


def _candidate_from_search_result(
    result: dict[str, Any],
    *,
    parent_score: float | None = None,
) -> _RelationCandidate:
    record = result["entity"]
    edge_score = float(result["distance"])
    path_score = edge_score if parent_score is None else (0.7 * edge_score) + (0.3 * parent_score)
    return _candidate_from_record(
        record,
        relation_id=str(record["id"]),
        fallback_text=str(record.get("text", "")),
        edge_score=edge_score,
        path_score=path_score,
    )


def _candidate_from_record(
    record: dict[str, Any],
    *,
    relation_id: str,
    fallback_text: str,
    edge_score: float,
    path_score: float,
) -> _RelationCandidate:
    return _RelationCandidate(
        relation_id=relation_id,
        text=str(record.get("text", fallback_text)),
        entity_ids=tuple(str(item) for item in record.get("entity_ids", [])),
        passage_ids=tuple(str(item) for item in record.get("passage_ids", [])),
        edge_score=edge_score,
        path_score=path_score,
    )


def _frontier_from_relations(
    relations: list[_RelationCandidate],
    visited_entities: set[str],
) -> dict[str, float]:
    frontier: dict[str, float] = {}
    for relation in relations:
        for entity_id in relation.entity_ids:
            if entity_id in visited_entities:
                continue
            frontier[entity_id] = max(frontier.get(entity_id, float("-inf")), relation.path_score)
    return frontier


def _is_allowed(
    candidate: _RelationCandidate,
    allowed_passage_ids: set[str] | None,
) -> bool:
    return allowed_passage_ids is None or bool(
        set(candidate.passage_ids) & allowed_passage_ids
    )


def _keep_best(
    candidates: dict[str, _RelationCandidate],
    candidate: _RelationCandidate,
) -> None:
    current = candidates.get(candidate.relation_id)
    if current is None or candidate.path_score > current.path_score:
        candidates[candidate.relation_id] = candidate


def _ranked(candidates: Any) -> list[_RelationCandidate]:
    return sorted(
        candidates,
        key=lambda item: (-item.path_score, -item.edge_score, item.relation_id),
    )
