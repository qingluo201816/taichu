"""基于 RRF Passage 种子的 Query-aware 有界图扩展。"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, fields
from typing import Any, Protocol


logger = logging.getLogger(__name__)


class GraphExpansionStore(Protocol):
    def _get_entities_by_ids(self, entity_ids: list[str]) -> list[dict[str, Any]]: ...

    def _get_relations_by_ids(
        self,
        relation_ids: list[str],
    ) -> list[dict[str, Any]]: ...

    def search_neighbor_relations(
        self,
        query_embedding: list[float],
        relation_ids: list[str],
        *,
        top_k: int,
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class ControlledExpansionSettings:
    """Passage-first Graph Expansion 的查询级硬预算。"""

    max_seed_entities: int = 5
    max_seed_relations: int = 32
    max_hop: int = 1
    max_entities_per_hop: int = 20
    relations_per_entity: int = 10
    hub_relations_per_entity: int = 5
    candidate_pool_multiplier: int = 4
    hub_degree_threshold: int = 100
    beam_width: int = 24
    max_total_relations: int = 56
    max_graph_passages: int = 20

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if value < 1:
                raise ValueError(f"Graph Expansion 配置 {item.name} 必须大于零。")
        if self.hub_relations_per_entity > self.relations_per_entity:
            raise ValueError("Hub 实体关系预算不得大于普通实体关系预算。")
        if self.max_seed_relations > self.max_total_relations:
            raise ValueError("种子关系预算不得大于全局关系预算。")


@dataclass(frozen=True, slots=True)
class PassageGraphSeed:
    """一条已经过 BM25 + Dense + RRF 融合的 Passage。"""

    passage_id: str
    rank: int
    score: float
    entity_ids: tuple[str, ...]
    relation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExpandedGraphRelation:
    relation_id: str
    text: str
    entity_ids: tuple[str, ...]
    passage_ids: tuple[str, ...]
    query_score: float
    path_score: float
    hop: int
    path_relation_ids: tuple[str, ...]
    adds_new_endpoint: bool = False


@dataclass(frozen=True, slots=True)
class PassageSeededExpansionResult:
    seed_passage_ids: tuple[str, ...]
    seed_entity_ids: tuple[str, ...]
    seed_relation_ids: tuple[str, ...]
    relations: tuple[ExpandedGraphRelation, ...]
    graph_passage_ids: tuple[str, ...]


class PassageSeededGraphExpander:
    """只沿 RRF Passage 携带的图元数据做有界扩展。"""

    def __init__(
        self,
        *,
        store: GraphExpansionStore,
        settings: ControlledExpansionSettings,
    ) -> None:
        self.store = store
        self.settings = settings

    def expand(
        self,
        *,
        query: str,
        query_embedding: list[float],
        seed_passages: list[PassageGraphSeed],
    ) -> PassageSeededExpansionResult:
        ordered_passages = sorted(seed_passages, key=lambda item: item.rank)
        seed_relation_ids = _unique(
            relation_id
            for passage in ordered_passages
            for relation_id in passage.relation_ids
        )
        seed_entity_ids = _unique(
            entity_id
            for passage in ordered_passages
            for entity_id in passage.entity_ids
        )
        if not seed_relation_ids and not seed_entity_ids:
            return PassageSeededExpansionResult(
                seed_passage_ids=tuple(item.passage_id for item in ordered_passages),
                seed_entity_ids=(),
                seed_relation_ids=(),
                relations=(),
                graph_passage_ids=(),
            )

        relation_support = _support_ranks(ordered_passages, kind="relation")
        entity_support = _support_ranks(ordered_passages, kind="entity")
        direct_candidates = self._rank_seed_relations(
            query=query,
            query_embedding=query_embedding,
            relation_ids=seed_relation_ids,
            relation_support=relation_support,
        )
        initial = self._select_seed_relations(
            direct_candidates,
            ordered_passages,
        )
        accepted = {item.relation_id: item for item in initial}
        selected_seed_entities = self._select_seed_entities(
            query=query,
            entity_ids=seed_entity_ids,
            entity_support=entity_support,
        )

        visited_entities: set[str] = set()
        frontier: dict[
            str,
            tuple[float, ExpandedGraphRelation | None],
        ] = _initial_frontier(
            initial,
            selected_seed_entities,
            query=query,
            entity_support=entity_support,
        )
        hop_counts: list[int] = []
        for hop in range(1, self.settings.max_hop + 1):
            if len(accepted) >= self.settings.max_total_relations or not frontier:
                break
            frontier_records = {
                str(item["id"]): item
                for item in self.store._get_entities_by_ids(list(frontier))
            }
            expandable_frontier = (
                (entity_id, state)
                for entity_id, state in frontier.items()
                if entity_id in frontier_records
                and any(
                    str(relation_id) not in accepted
                    for relation_id in frontier_records[entity_id].get(
                        "relation_ids", []
                    )
                )
            )
            selected_frontier = sorted(
                expandable_frontier,
                key=lambda item: (-item[1][0], item[0]),
            )[: self.settings.max_entities_per_hop]
            frontier_ids = [entity_id for entity_id, _state in selected_frontier]
            visited_entities.update(frontier_ids)
            records = {
                entity_id: frontier_records[entity_id]
                for entity_id in frontier_ids
            }
            next_candidates: dict[str, ExpandedGraphRelation] = {}
            local_candidates_by_entity: dict[
                str, list[ExpandedGraphRelation]
            ] = {}
            for entity_id, (_priority, parent) in selected_frontier:
                entity = records.get(entity_id)
                if entity is None:
                    continue
                neighbor_ids = [
                    str(item) for item in entity.get("relation_ids", [])
                ]
                per_entity_limit = (
                    self.settings.hub_relations_per_entity
                    if len(neighbor_ids) >= self.settings.hub_degree_threshold
                    else self.settings.relations_per_entity
                )
                results = self.store.search_neighbor_relations(
                    query_embedding,
                    neighbor_ids,
                    top_k=min(
                        len(set(neighbor_ids)),
                        per_entity_limit * self.settings.candidate_pool_multiplier,
                    ),
                )
                local_candidates: list[ExpandedGraphRelation] = []
                for result in results:
                    candidate = _candidate_from_search_result(
                        result,
                        query=query,
                        hop=hop,
                        parent=parent,
                    )
                    if candidate.relation_id in accepted:
                        continue
                    local_candidates.append(candidate)
                local_candidates.sort(
                    key=lambda item: (
                        -int(_adds_new_endpoint(item, parent)),
                        -item.path_score,
                        -item.query_score,
                        item.relation_id,
                    )
                )
                admitted_local = local_candidates[:per_entity_limit]
                local_candidates_by_entity[entity_id] = admitted_local
                for candidate in admitted_local:
                    _keep_best(next_candidates, candidate)

            beam = _select_balanced_beam(
                frontier_ids=frontier_ids,
                local_candidates_by_entity=local_candidates_by_entity,
                candidates=next_candidates,
                width=self.settings.beam_width,
            )
            remaining = self.settings.max_total_relations - len(accepted)
            admitted = beam[:remaining]
            for candidate in admitted:
                accepted[candidate.relation_id] = candidate
            hop_counts.append(len(admitted))
            frontier = _next_frontier(admitted, visited_entities)

        relations = _path_aware_rank(accepted)
        graph_passage_ids = _select_graph_passage_ids(
            relations,
            seed_passage_ids={item.passage_id for item in ordered_passages},
            limit=self.settings.max_graph_passages,
        )
        logger.info(
            "Passage-first Graph Expansion: passages=%d seed_entities=%d "
            "seed_relations=%d initial=%d hops=%s total=%d graph_passages=%d",
            len(ordered_passages),
            len(selected_seed_entities),
            len(seed_relation_ids),
            len(initial),
            hop_counts,
            len(relations),
            len(graph_passage_ids),
        )
        return PassageSeededExpansionResult(
            seed_passage_ids=tuple(item.passage_id for item in ordered_passages),
            seed_entity_ids=tuple(selected_seed_entities),
            seed_relation_ids=tuple(item.relation_id for item in initial),
            relations=tuple(relations),
            graph_passage_ids=tuple(graph_passage_ids),
        )

    def _rank_seed_relations(
        self,
        *,
        query: str,
        query_embedding: list[float],
        relation_ids: list[str],
        relation_support: dict[str, int],
    ) -> list[ExpandedGraphRelation]:
        search_results = self.store.search_neighbor_relations(
            query_embedding,
            relation_ids,
            top_k=len(relation_ids),
        )
        query_scores = {
            str(item["entity"]["id"]): _bounded_similarity(item.get("distance"))
            for item in search_results
        }
        records = self.store._get_relations_by_ids(relation_ids)
        candidates: list[ExpandedGraphRelation] = []
        for record in records:
            relation_id = str(record["id"])
            text = str(record.get("text", ""))
            query_score = query_scores.get(relation_id, 0.0)
            lexical_score = _relation_lexical_relevance(query, text)
            passage_score = _rank_score(relation_support.get(relation_id, 10_000))
            path_score = (
                (0.45 * query_score)
                + (0.30 * lexical_score)
                + (0.25 * passage_score)
            )
            candidates.append(
                _candidate_from_record(
                    record,
                    query_score=query_score,
                    path_score=path_score,
                    hop=0,
                    path_relation_ids=(relation_id,),
                )
            )
        return _ranked(candidates)

    def _select_seed_relations(
        self,
        candidates: list[ExpandedGraphRelation],
        passages: list[PassageGraphSeed],
    ) -> list[ExpandedGraphRelation]:
        if not candidates:
            return []
        by_id = {item.relation_id: item for item in candidates}
        selected: dict[str, ExpandedGraphRelation] = {}
        coverage_passage_count = min(
            len(passages),
            self.settings.max_seed_relations,
        )
        for passage in passages[:coverage_passage_count]:
            local = _ranked(
                by_id[relation_id]
                for relation_id in passage.relation_ids
                if relation_id in by_id
            )
            for candidate in local[:1]:
                selected.setdefault(candidate.relation_id, candidate)
                if len(selected) >= self.settings.max_seed_relations:
                    return _ranked(selected.values())
        for candidate in candidates:
            selected.setdefault(candidate.relation_id, candidate)
            if len(selected) >= self.settings.max_seed_relations:
                break
        return _ranked(selected.values())

    def _select_seed_entities(
        self,
        *,
        query: str,
        entity_ids: list[str],
        entity_support: dict[str, int],
    ) -> list[str]:
        records = self.store._get_entities_by_ids(entity_ids)
        normalized_query = _compact_text(query)
        ranked = sorted(
            records,
            key=lambda item: (
                -int(
                    len(_compact_text(str(item.get("text", "")))) >= 2
                    and _compact_text(str(item.get("text", "")))
                    in normalized_query
                ),
                entity_support.get(str(item["id"]), 10_000),
                len(item.get("relation_ids", [])),
                str(item["id"]),
            ),
        )
        return [
            str(item["id"])
            for item in ranked[: self.settings.max_seed_entities]
        ]


def _candidate_from_search_result(
    result: dict[str, Any],
    *,
    query: str,
    hop: int,
    parent: ExpandedGraphRelation | None,
) -> ExpandedGraphRelation:
    record = result["entity"]
    relation_id = str(record["id"])
    text = str(record.get("text", ""))
    query_score = _bounded_similarity(result.get("distance"))
    lexical_score = _relation_lexical_relevance(query, text)
    if parent is None:
        path_score = (0.65 * query_score) + (0.35 * lexical_score)
        path_relation_ids: tuple[str, ...] = (relation_id,)
    else:
        path_score = (
            (0.45 * query_score)
            + (0.30 * lexical_score)
            + (0.25 * parent.path_score)
        )
        path_relation_ids = (*parent.path_relation_ids, relation_id)
    return _candidate_from_record(
        record,
        query_score=query_score,
        path_score=path_score,
        hop=hop,
        path_relation_ids=path_relation_ids,
        adds_new_endpoint=(
            parent is not None
            and bool(set(str(item) for item in record.get("entity_ids", [])).difference(parent.entity_ids))
        ),
    )


def _candidate_from_record(
    record: dict[str, Any],
    *,
    query_score: float,
    path_score: float,
    hop: int,
    path_relation_ids: tuple[str, ...],
    adds_new_endpoint: bool = False,
) -> ExpandedGraphRelation:
    return ExpandedGraphRelation(
        relation_id=str(record["id"]),
        text=str(record.get("text", "")),
        entity_ids=tuple(str(item) for item in record.get("entity_ids", [])),
        passage_ids=tuple(str(item) for item in record.get("passage_ids", [])),
        query_score=query_score,
        path_score=path_score,
        hop=hop,
        path_relation_ids=path_relation_ids,
        adds_new_endpoint=adds_new_endpoint,
    )


def _adds_new_endpoint(
    candidate: ExpandedGraphRelation,
    parent: ExpandedGraphRelation | None,
) -> bool:
    if parent is None:
        return False
    return bool(set(candidate.entity_ids).difference(parent.entity_ids))


def _initial_frontier(
    relations: list[ExpandedGraphRelation],
    seed_entity_ids: list[str],
    *,
    query: str,
    entity_support: dict[str, int],
) -> dict[str, tuple[float, ExpandedGraphRelation | None]]:
    frontier: dict[str, tuple[float, ExpandedGraphRelation | None]] = {}
    for entity_id in seed_entity_ids:
        priority = 1.0 + (0.25 * _rank_score(entity_support.get(entity_id, 10_000)))
        frontier[entity_id] = (priority, None)
    for relation in relations:
        for entity_id in relation.entity_ids:
            priority = relation.path_score
            current = frontier.get(entity_id)
            if current is not None and current[1] is None:
                frontier[entity_id] = (max(current[0], priority), relation)
            elif current is None or priority > current[0]:
                frontier[entity_id] = (priority, relation)
    del query
    return frontier


def _next_frontier(
    relations: list[ExpandedGraphRelation],
    visited_entities: set[str],
) -> dict[str, tuple[float, ExpandedGraphRelation | None]]:
    frontier: dict[str, tuple[float, ExpandedGraphRelation | None]] = {}
    for relation in relations:
        for entity_id in relation.entity_ids:
            if entity_id in visited_entities:
                continue
            current = frontier.get(entity_id)
            if current is None or relation.path_score > current[0]:
                frontier[entity_id] = (relation.path_score, relation)
    return frontier


def _path_aware_rank(
    accepted: dict[str, ExpandedGraphRelation],
) -> list[ExpandedGraphRelation]:
    ordered: list[ExpandedGraphRelation] = []
    seen: set[str] = set()
    path_candidates = sorted(
        accepted.values(),
        key=lambda item: (-len(item.path_relation_ids), -item.path_score, item.relation_id),
    )
    for candidate in path_candidates:
        for relation_id in candidate.path_relation_ids:
            relation = accepted.get(relation_id)
            if relation is None or relation_id in seen:
                continue
            seen.add(relation_id)
            ordered.append(relation)
    for candidate in _ranked(accepted.values()):
        if candidate.relation_id not in seen:
            seen.add(candidate.relation_id)
            ordered.append(candidate)
    return ordered


def _select_graph_passage_ids(
    relations: list[ExpandedGraphRelation],
    *,
    seed_passage_ids: set[str],
    limit: int,
) -> list[str]:
    """先为不同关系各保留一个新 Passage，再用剩余预算补充同关系证据。"""

    selected: list[str] = []
    seen = set(seed_passage_ids)
    for relation in relations:
        passage_id = next(
            (item for item in relation.passage_ids if item not in seen),
            None,
        )
        if passage_id is None:
            continue
        selected.append(passage_id)
        seen.add(passage_id)
        if len(selected) >= limit:
            return selected
    for relation in relations:
        for passage_id in relation.passage_ids:
            if passage_id in seen:
                continue
            selected.append(passage_id)
            seen.add(passage_id)
            if len(selected) >= limit:
                return selected
    return selected


def _support_ranks(
    passages: list[PassageGraphSeed],
    *,
    kind: str,
) -> dict[str, int]:
    support: dict[str, int] = {}
    for passage in passages:
        values = passage.relation_ids if kind == "relation" else passage.entity_ids
        for value in values:
            support[value] = min(support.get(value, passage.rank), passage.rank)
    return support


def _keep_best(
    candidates: dict[str, ExpandedGraphRelation],
    candidate: ExpandedGraphRelation,
) -> None:
    current = candidates.get(candidate.relation_id)
    if current is None or candidate.path_score > current.path_score:
        candidates[candidate.relation_id] = candidate


def _ranked(candidates: Any) -> list[ExpandedGraphRelation]:
    return sorted(
        candidates,
        key=lambda item: (
            -int(item.adds_new_endpoint),
            -item.path_score,
            -item.query_score,
            item.relation_id,
        ),
    )


def _select_balanced_beam(
    *,
    frontier_ids: list[str],
    local_candidates_by_entity: dict[str, list[ExpandedGraphRelation]],
    candidates: dict[str, ExpandedGraphRelation],
    width: int,
) -> list[ExpandedGraphRelation]:
    """先让每个前沿实体贡献一条边，再按全局相关性填满 Beam。"""

    selected: dict[str, ExpandedGraphRelation] = {}
    for entity_id in frontier_ids:
        for candidate in local_candidates_by_entity.get(entity_id, []):
            if candidate.relation_id in selected:
                continue
            selected[candidate.relation_id] = candidate
            break
        if len(selected) >= width:
            return list(selected.values())
    for candidate in _ranked(candidates.values()):
        selected.setdefault(candidate.relation_id, candidate)
        if len(selected) >= width:
            break
    return list(selected.values())


def _rank_score(rank: int) -> float:
    if rank < 1 or rank >= 10_000:
        return 0.0
    return 1.0 / (1.0 + (0.12 * (rank - 1)))


def _bounded_similarity(value: object) -> float:
    try:
        score = float(str(value))
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, (score + 1.0) / 2.0))


def _lexical_recall(query: str, text: str) -> float:
    query_terms = _terms(query)
    text_terms = _terms(text)
    if not query_terms or not text_terms:
        return 0.0
    return len(query_terms & text_terms) / len(text_terms)


def _relation_lexical_relevance(query: str, text: str) -> float:
    """优先识别问题中明确出现的关系谓词，避免实体名称主导邻边排序。"""

    base_score = _lexical_recall(query, text)
    parts = text.split()
    if len(parts) < 3:
        return base_score
    predicate = "".join(parts[1:-1])
    predicate_terms = _terms(predicate)
    query_terms = _terms(query)
    if not predicate_terms or not query_terms:
        return base_score
    predicate_score = len(predicate_terms & query_terms) / len(predicate_terms)
    if len(_compact_text(predicate)) >= 2 and _compact_text(predicate) in _compact_text(
        query
    ):
        predicate_score = 1.0
    return max(base_score, predicate_score)


def _terms(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    bigrams = {
        chinese[index : index + 2]
        for index in range(max(0, len(chinese) - 1))
    }
    words = set(re.findall(r"[a-z0-9]+", normalized))
    return bigrams | words


def _compact_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(re.findall(r"[\w\u4e00-\u9fff]", normalized)).replace("_", "")


def _unique(values: Any) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))
