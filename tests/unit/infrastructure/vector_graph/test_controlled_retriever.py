"""受控 Graph Expansion 回归测试。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import Mock

from taichu.infrastructure.vector_graph.controlled_retriever import (
    ControlledExpansionSettings,
    ControlledGraphRetriever,
)
from taichu.infrastructure.vector_graph.milvus_store import TaichuHNSWMilvusStore


@dataclass
class _EntityExtractor:
    entities: list[str]

    def extract(self, query: str) -> list[str]:
        del query
        return self.entities


class _EmbeddingModel:
    def embed(self, text: str) -> list[float]:
        del text
        return [1.0, 0.0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class _Store:
    def __init__(self) -> None:
        self.entity_records: dict[str, dict[str, Any]] = {}
        self.relation_records: dict[str, dict[str, Any]] = {}
        self.neighbor_searches: list[tuple[int, int]] = []

    def _search_entities(
        self,
        query_embeddings: list[list[float]],
        top_k: int,
    ) -> list[list[dict[str, Any]]]:
        del query_embeddings, top_k
        return [
            [
                {
                    "distance": 0.99,
                    "entity": {
                        "id": "entity-qin",
                        "text": "秦浩轩",
                    },
                }
            ]
        ]

    def _search_relations(
        self,
        query_embedding: list[float],
        top_k: int,
    ) -> list[dict[str, Any]]:
        del query_embedding
        return [
            _search_result(self.relation_records[f"global-{index}"])
            for index in range(top_k)
        ]

    def _get_entities_by_ids(self, entity_ids: list[str]) -> list[dict[str, Any]]:
        return [self.entity_records[item] for item in entity_ids if item in self.entity_records]

    def _get_relations_by_ids(self, relation_ids: list[str]) -> list[dict[str, Any]]:
        return [
            self.relation_records[item]
            for item in relation_ids
            if item in self.relation_records
        ]

    def search_neighbor_relations(
        self,
        query_embedding: list[float],
        relation_ids: list[str],
        *,
        top_k: int,
    ) -> list[dict[str, Any]]:
        del query_embedding
        self.neighbor_searches.append((len(relation_ids), top_k))
        records = sorted(
            (
                self.relation_records[item]
                for item in relation_ids
                if item in self.relation_records
            ),
            key=lambda item: float(item["score"]),
            reverse=True,
        )
        return [_search_result(item) for item in records[:top_k]]


def test_hub_entity_neighbors_are_query_ranked_before_expansion() -> None:
    store = _hub_store()
    retriever = ControlledGraphRetriever(
        store=store,  # type: ignore[arg-type]
        embedding_model=_EmbeddingModel(),  # type: ignore[arg-type]
        entity_extractor=_EntityExtractor(["秦浩轩"]),  # type: ignore[arg-type]
        expansion=ControlledExpansionSettings(
            max_seed_entities=3,
            initial_relations_per_entity=20,
            initial_beam_width=20,
            max_hop=2,
            max_entities_per_hop=12,
            relations_per_entity=8,
            hub_relations_per_entity=5,
            hub_degree_threshold=100,
            beam_width=20,
            max_total_relations=60,
        ),
    )

    result = retriever.retrieve("秦浩轩什么时候飞升仙界", relation_top_k=30)

    assert store.neighbor_searches[0] == (841, 20)
    assert len(result.relation_ids) == 30
    assert len(result.expanded_relation_ids) <= 60
    assert result.eviction_before_count <= 60
    assert result.eviction_after_count <= 60
    assert result.eviction_occurred is False


def test_each_hop_obeys_entity_and_hub_neighbor_budgets() -> None:
    store = _hub_store()
    retriever = ControlledGraphRetriever(
        store=store,  # type: ignore[arg-type]
        embedding_model=_EmbeddingModel(),  # type: ignore[arg-type]
        entity_extractor=_EntityExtractor(["秦浩轩"]),  # type: ignore[arg-type]
        expansion=ControlledExpansionSettings(
            max_seed_entities=1,
            initial_relations_per_entity=4,
            initial_beam_width=4,
            max_hop=2,
            max_entities_per_hop=2,
            relations_per_entity=3,
            hub_relations_per_entity=2,
            hub_degree_threshold=5,
            beam_width=4,
            max_total_relations=9,
        ),
    )

    result = retriever.retrieve("秦浩轩什么时候飞升仙界", relation_top_k=3)

    assert len(result.expanded_relation_ids) <= 9
    assert all(top_k <= 3 for _, top_k in store.neighbor_searches[1:])
    assert any(top_k == 2 for _, top_k in store.neighbor_searches[1:])
    assert len(store.neighbor_searches) <= 1 + (2 * 2)


def test_neighbor_search_uses_relation_ids_as_ann_filter() -> None:
    store = object.__new__(TaichuHNSWMilvusStore)
    store.client = Mock()
    store.relation_collection = "relations"
    store.ef_search = 150
    store.client.search.return_value = [[{"entity": {"id": "r-1"}}]]

    result = store.search_neighbor_relations(
        [1.0, 0.0],
        ["r-1", "r-2", "r-2"],
        top_k=20,
    )

    assert result == [{"entity": {"id": "r-1"}}]
    call = store.client.search.call_args.kwargs
    assert call["limit"] == 2
    assert call["filter"] == 'id in ["r-1", "r-2"]'
    assert call["search_params"] == {
        "metric_type": "IP",
        "params": {"ef": 150},
    }


def _hub_store() -> _Store:
    store = _Store()
    hub_relations = [f"hub-{index}" for index in range(841)]
    store.entity_records["entity-qin"] = {
        "id": "entity-qin",
        "text": "秦浩轩",
        "relation_ids": hub_relations,
    }

    for index in range(30):
        relation_id = f"global-{index}"
        endpoint_id = f"global-entity-{index}"
        store.relation_records[relation_id] = _relation(
            relation_id,
            ["entity-qin", endpoint_id],
            score=0.70 - (index / 1000),
        )
        store.entity_records[endpoint_id] = _entity_with_relations(endpoint_id, 6, store)

    for index, relation_id in enumerate(hub_relations):
        endpoint_id = f"hub-entity-{index}"
        store.relation_records[relation_id] = _relation(
            relation_id,
            ["entity-qin", endpoint_id],
            score=0.99 - (index / 10000),
        )
        store.entity_records[endpoint_id] = _entity_with_relations(endpoint_id, 6, store)

    return store


def _entity_with_relations(entity_id: str, count: int, store: _Store) -> dict[str, Any]:
    relation_ids = [f"{entity_id}-next-{index}" for index in range(count)]
    for index, relation_id in enumerate(relation_ids):
        store.relation_records[relation_id] = _relation(
            relation_id,
            [entity_id, f"{entity_id}-leaf-{index}"],
            score=0.80 - (index / 100),
        )
    return {"id": entity_id, "text": entity_id, "relation_ids": relation_ids}


def _relation(
    relation_id: str,
    entity_ids: list[str],
    *,
    score: float,
) -> dict[str, Any]:
    return {
        "id": relation_id,
        "text": relation_id,
        "entity_ids": entity_ids,
        "passage_ids": [f"passage-{relation_id}"],
        "score": score,
    }


def _search_result(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "distance": record["score"],
        "entity": record,
    }
