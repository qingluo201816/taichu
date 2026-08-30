"""Passage-first 受控 Graph Expansion 回归测试。"""

from __future__ import annotations

from typing import Any

from taichu.infrastructure.vector_graph.controlled_retriever import (
    ControlledExpansionSettings,
    ExpandedGraphRelation,
    PassageGraphSeed,
    PassageSeededGraphExpander,
    _select_balanced_beam,
)


class _Store:
    def __init__(self) -> None:
        self.entity_records: dict[str, dict[str, Any]] = {}
        self.relation_records: dict[str, dict[str, Any]] = {}
        self.neighbor_searches: list[tuple[int, int]] = []

    def _get_entities_by_ids(self, entity_ids: list[str]) -> list[dict[str, Any]]:
        return [
            self.entity_records[item]
            for item in entity_ids
            if item in self.entity_records
        ]

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
                for item in dict.fromkeys(relation_ids)
                if item in self.relation_records
            ),
            key=lambda item: float(item["score"]),
            reverse=True,
        )
        return [
            {"distance": record["score"], "entity": record}
            for record in records[:top_k]
        ]


def test_expansion_starts_from_rrf_passage_metadata_and_keeps_complete_path() -> None:
    store = _Store()
    store.relation_records.update(
        {
            "r-direct": _relation(
                "r-direct",
                "李靖 派人传话 严冬",
                ["li", "yan"],
                ["p-seed"],
                score=0.91,
            ),
            "r-next": _relation(
                "r-next",
                "严冬 同意 毒害小金",
                ["yan", "xiaojin"],
                ["p-graph"],
                score=0.95,
            ),
            "r-noise": _relation(
                "r-noise",
                "严冬 居住 灵田谷",
                ["yan", "valley"],
                ["p-noise"],
                score=0.20,
            ),
        }
    )
    store.entity_records.update(
        {
            "li": _entity("li", ["r-direct"]),
            "yan": _entity("yan", ["r-direct", "r-next", "r-noise"]),
            "xiaojin": _entity("xiaojin", ["r-next"]),
        }
    )
    expander = PassageSeededGraphExpander(
        store=store,  # type: ignore[arg-type]
        settings=_settings(max_seed_relations=2, max_total_relations=2),
    )

    result = expander.expand(
        query="小金食物中毒事件的幕后指使者是谁？",
        query_embedding=[1.0, 0.0],
        seed_passages=[
            PassageGraphSeed(
                passage_id="p-seed",
                rank=1,
                score=0.03,
                entity_ids=("li", "yan"),
                relation_ids=("r-direct",),
            )
        ],
    )

    assert result.seed_passage_ids == ("p-seed",)
    assert result.seed_relation_ids == ("r-direct",)
    assert [item.relation_id for item in result.relations] == [
        "r-direct",
        "r-next",
    ]
    assert result.relations[1].path_relation_ids == ("r-direct", "r-next")
    assert result.graph_passage_ids == ("p-graph",)


def test_hub_entity_expansion_is_query_ranked_and_strictly_bounded() -> None:
    store = _Store()
    hub_relations = [f"hub-{index}" for index in range(841)]
    store.entity_records["hub"] = _entity("hub", hub_relations)
    for index, relation_id in enumerate(hub_relations):
        store.relation_records[relation_id] = _relation(
            relation_id,
            f"主角 关系 {index}",
            ["hub", f"leaf-{index}"],
            [f"passage-{index}"],
            score=1 - (index / 1_000),
        )
    store.relation_records["seed"] = _relation(
        "seed",
        "主角 位于 山门",
        ["hub", "gate"],
        ["p-seed"],
        score=0.99,
    )

    expander = PassageSeededGraphExpander(
        store=store,  # type: ignore[arg-type]
        settings=_settings(
            max_seed_entities=1,
            max_seed_relations=2,
            max_entities_per_hop=1,
            relations_per_entity=4,
            hub_relations_per_entity=2,
            hub_degree_threshold=100,
            beam_width=2,
            max_total_relations=3,
        ),
    )

    result = expander.expand(
        query="主角后来去了哪里？",
        query_embedding=[1.0, 0.0],
        seed_passages=[
            PassageGraphSeed(
                passage_id="p-seed",
                rank=1,
                score=0.03,
                entity_ids=("hub",),
                relation_ids=("seed",),
            )
        ],
    )

    assert len(result.relations) <= 3
    assert any(size == 841 and limit == 8 for size, limit in store.neighbor_searches)
    assert len([item for item in result.relations if item.relation_id.startswith("hub-")]) <= 2


def test_no_global_entity_or_relation_search_is_required() -> None:
    store = _Store()
    store.relation_records["seed"] = _relation(
        "seed",
        "黄帝峰 属于 太初教",
        ["peak", "sect"],
        ["p-seed"],
        score=0.99,
    )
    store.entity_records["peak"] = _entity("peak", ["seed"])
    expander = PassageSeededGraphExpander(
        store=store,  # type: ignore[arg-type]
        settings=_settings(
            max_seed_relations=2,
            max_hop=1,
            max_total_relations=2,
        ),
    )

    result = expander.expand(
        query="黄帝峰属于哪个宗门？",
        query_embedding=[1.0, 0.0],
        seed_passages=[
            PassageGraphSeed(
                passage_id="p-seed",
                rank=1,
                score=0.03,
                entity_ids=("peak", "sect"),
                relation_ids=("seed",),
            )
        ],
    )

    assert [item.text for item in result.relations] == ["黄帝峰 属于 太初教"]


def test_seed_relation_budget_covers_later_rrf_passages_before_extra_relations() -> None:
    store = _Store()
    passages: list[PassageGraphSeed] = []
    for rank in range(1, 5):
        relation_ids = (f"p{rank}-best", f"p{rank}-extra")
        passages.append(
            PassageGraphSeed(
                passage_id=f"p{rank}",
                rank=rank,
                score=1 / rank,
                entity_ids=(),
                relation_ids=relation_ids,
            )
        )
        store.relation_records[relation_ids[0]] = _relation(
            relation_ids[0],
            f"第{rank}篇 关键 关系",
            [],
            [f"p{rank}"],
            score=1 - (rank / 100),
        )
        store.relation_records[relation_ids[1]] = _relation(
            relation_ids[1],
            f"第{rank}篇 次要 关系",
            [],
            [f"p{rank}"],
            score=0.5 - (rank / 100),
        )

    result = PassageSeededGraphExpander(
        store=store,  # type: ignore[arg-type]
        settings=_settings(
            max_seed_relations=4,
            max_total_relations=4,
        ),
    ).expand(
        query="关键关系",
        query_embedding=[1.0, 0.0],
        seed_passages=passages,
    )

    assert set(result.seed_relation_ids) == {
        "p1-best",
        "p2-best",
        "p3-best",
        "p4-best",
    }


def test_graph_passage_budget_is_diversified_across_path_relations() -> None:
    store = _Store()
    store.relation_records.update(
        {
            "r-seed": _relation(
                "r-seed",
                "秦浩轩 发现 一叶金莲",
                ["qin", "lotus"],
                ["p-seed", "p-noise-1", "p-noise-2"],
                score=0.95,
            ),
            "r-answer": _relation(
                "r-answer",
                "一叶金莲 有助突破 法相境",
                ["lotus", "realm"],
                ["p-answer"],
                score=0.99,
            ),
        }
    )
    store.entity_records.update(
        {
            "qin": _entity("qin", ["r-seed"]),
            "lotus": _entity("lotus", ["r-seed", "r-answer"]),
        }
    )

    result = PassageSeededGraphExpander(
        store=store,  # type: ignore[arg-type]
        settings=_settings(
            max_seed_relations=1,
            max_total_relations=2,
            max_graph_passages=2,
        ),
    ).expand(
        query="秦浩轩发现的灵药有助突破什么境界？",
        query_embedding=[1.0, 0.0],
        seed_passages=[
            PassageGraphSeed(
                passage_id="p-seed",
                rank=1,
                score=1.0,
                entity_ids=("qin", "lotus"),
                relation_ids=("r-seed",),
            )
        ],
    )

    assert result.graph_passage_ids == ("p-noise-1", "p-answer")


def test_next_hop_prefers_a_new_endpoint_over_parallel_edges() -> None:
    store = _Store()
    store.relation_records["r-seed"] = _relation(
        "r-seed",
        "秦浩轩 发现 一叶金莲",
        ["qin", "lotus"],
        ["p-seed"],
        score=0.99,
    )
    parallel_ids: list[str] = []
    for index in range(6):
        relation_id = f"parallel-{index}"
        parallel_ids.append(relation_id)
        store.relation_records[relation_id] = _relation(
            relation_id,
            f"秦浩轩 使用 一叶金莲{index}",
            ["qin", "lotus"],
            [f"p-parallel-{index}"],
            score=0.98 - (index / 100),
        )
    store.relation_records["r-answer"] = _relation(
        "r-answer",
        "一叶金莲 有助突破 法相境",
        ["lotus", "realm"],
        ["p-answer"],
        score=0.80,
    )
    neighbor_ids = ["r-seed", *parallel_ids, "r-answer"]
    store.entity_records.update(
        {
            "qin": _entity("qin", neighbor_ids),
            "lotus": _entity("lotus", neighbor_ids),
        }
    )

    result = PassageSeededGraphExpander(
        store=store,  # type: ignore[arg-type]
        settings=_settings(
            max_seed_relations=1,
            relations_per_entity=2,
            candidate_pool_multiplier=4,
            max_total_relations=2,
        ),
    ).expand(
        query="秦浩轩发现的灵药有助突破什么境界？",
        query_embedding=[1.0, 0.0],
        seed_passages=[
            PassageGraphSeed(
                passage_id="p-seed",
                rank=1,
                score=1.0,
                entity_ids=("qin", "lotus"),
                relation_ids=("r-seed",),
            )
        ],
    )

    assert [item.relation_id for item in result.relations] == [
        "r-seed",
        "r-answer",
    ]


def test_dead_end_entities_do_not_consume_the_frontier_budget() -> None:
    store = _Store()
    store.relation_records.update(
        {
            "r-seed": _relation(
                "r-seed",
                "秦浩轩 发现 一叶金莲",
                ["a-dead", "z-bridge"],
                ["p-seed"],
                score=0.99,
            ),
            "r-answer": _relation(
                "r-answer",
                "一叶金莲 有助突破 法相境",
                ["z-bridge", "realm"],
                ["p-answer"],
                score=0.80,
            ),
        }
    )
    store.entity_records.update(
        {
            "a-dead": _entity("a-dead", ["r-seed"]),
            "z-bridge": _entity("z-bridge", ["r-seed", "r-answer"]),
        }
    )

    result = PassageSeededGraphExpander(
        store=store,  # type: ignore[arg-type]
        settings=_settings(
            max_seed_relations=1,
            max_entities_per_hop=1,
            max_total_relations=2,
        ),
    ).expand(
        query="秦浩轩发现的灵药有助突破什么境界？",
        query_embedding=[1.0, 0.0],
        seed_passages=[
            PassageGraphSeed(
                passage_id="p-seed",
                rank=1,
                score=1.0,
                entity_ids=("a-dead", "z-bridge"),
                relation_ids=("r-seed",),
            )
        ],
    )

    assert [item.relation_id for item in result.relations] == [
        "r-seed",
        "r-answer",
    ]


def test_explicit_query_predicate_outweighs_entity_name_dense_noise() -> None:
    store = _Store()
    store.relation_records.update(
        {
            "r-seed": _relation(
                "r-seed",
                "秦浩轩 师从 璇玑子",
                ["qin", "xuan"],
                ["p-seed"],
                score=0.99,
            ),
            "r-noise": _relation(
                "r-noise",
                "璇玑子 收徒 另一名弟子",
                ["xuan", "other"],
                ["p-noise"],
                score=0.99,
            ),
            "r-answer": _relation(
                "r-answer",
                "璇玑子 亲自迎接 蒲汉忠",
                ["xuan", "puhan"],
                ["p-answer"],
                score=0.30,
            ),
        }
    )
    store.entity_records.update(
        {
            "qin": _entity("qin", ["r-seed"]),
            "xuan": _entity("xuan", ["r-seed", "r-noise", "r-answer"]),
        }
    )

    result = PassageSeededGraphExpander(
        store=store,  # type: ignore[arg-type]
        settings=_settings(
            max_seed_relations=1,
            relations_per_entity=1,
            hub_relations_per_entity=1,
            max_total_relations=2,
        ),
    ).expand(
        query="秦浩轩的师父曾亲自迎接哪位弟子？",
        query_embedding=[1.0, 0.0],
        seed_passages=[
            PassageGraphSeed(
                passage_id="p-seed",
                rank=1,
                score=1.0,
                entity_ids=("qin", "xuan"),
                relation_ids=("r-seed",),
            )
        ],
    )

    assert [item.relation_id for item in result.relations] == [
        "r-seed",
        "r-answer",
    ]


def test_balanced_beam_keeps_one_candidate_from_each_frontier_entity() -> None:
    hub_best = _expanded_relation("hub-best", 0.99)
    hub_second = _expanded_relation("hub-second", 0.98)
    bridge = _expanded_relation("bridge", 0.20)

    selected = _select_balanced_beam(
        frontier_ids=["hub", "bridge"],
        local_candidates_by_entity={
            "hub": [hub_best, hub_second],
            "bridge": [bridge],
        },
        candidates={
            item.relation_id: item for item in (hub_best, hub_second, bridge)
        },
        width=2,
    )

    assert [item.relation_id for item in selected] == ["hub-best", "bridge"]


def _settings(**overrides: int) -> ControlledExpansionSettings:
    values = {
        "max_seed_entities": 4,
        "max_seed_relations": 8,
        "max_hop": 1,
        "max_entities_per_hop": 4,
        "relations_per_entity": 4,
        "hub_relations_per_entity": 2,
        "candidate_pool_multiplier": 4,
        "hub_degree_threshold": 100,
        "beam_width": 8,
        "max_total_relations": 12,
        "max_graph_passages": 8,
    }
    values.update(overrides)
    return ControlledExpansionSettings(**values)


def _entity(entity_id: str, relation_ids: list[str]) -> dict[str, Any]:
    return {"id": entity_id, "text": entity_id, "relation_ids": relation_ids}


def _relation(
    relation_id: str,
    text: str,
    entity_ids: list[str],
    passage_ids: list[str],
    *,
    score: float,
) -> dict[str, Any]:
    return {
        "id": relation_id,
        "text": text,
        "entity_ids": entity_ids,
        "passage_ids": passage_ids,
        "score": score,
    }


def _expanded_relation(
    relation_id: str,
    path_score: float,
) -> ExpandedGraphRelation:
    return ExpandedGraphRelation(
        relation_id=relation_id,
        text=relation_id,
        entity_ids=(relation_id,),
        passage_ids=(f"passage-{relation_id}",),
        query_score=path_score,
        path_score=path_score,
        hop=1,
        path_relation_ids=(relation_id,),
        adds_new_endpoint=True,
    )
