from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from pymilvus import DataType, FunctionType

from taichu.infrastructure.vector_graph.milvus_store import TaichuHNSWMilvusStore


DIMENSION = 4
ENTITY_COLLECTION = "entities"
RELATION_COLLECTION = "relations"
PASSAGE_COLLECTION = "passages"


class _SchemaFake:
    def __init__(self) -> None:
        self.fields: list[dict[str, Any]] = []
        self.functions: list[dict[str, Any]] = []

    def add_field(self, **kwargs: Any) -> None:
        self.fields.append(kwargs)

    def add_function(self, function: Any) -> None:
        self.functions.append(function.to_dict())


class _IndexParamsFake:
    def __init__(self) -> None:
        self.indexes: list[dict[str, Any]] = []

    def add_index(self, **kwargs: Any) -> None:
        self.indexes.append(kwargs)


class _MilvusClientFake:
    def __init__(self, collections: dict[str, dict[str, Any]] | None = None) -> None:
        self.collections = deepcopy(collections or {})
        self.created_collections: list[str] = []
        self.described_collections: list[str] = []
        self.create_schema_calls = 0
        self.query_responses: list[list[dict[str, Any]]] = []
        self.query_calls: list[dict[str, Any]] = []
        self.drop_collection = Mock()
        self.insert = Mock()
        self.upsert = Mock()
        self.delete = Mock()

    def has_collection(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def describe_collection(self, collection_name: str) -> dict[str, Any]:
        self.described_collections.append(collection_name)
        return deepcopy(self.collections[collection_name]["description"])

    def list_indexes(self, collection_name: str) -> list[str]:
        return list(self.collections[collection_name]["indexes"])

    def describe_index(
        self,
        collection_name: str,
        index_name: str,
    ) -> dict[str, Any]:
        return deepcopy(self.collections[collection_name]["indexes"][index_name])

    def create_schema(self, **_kwargs: Any) -> _SchemaFake:
        self.create_schema_calls += 1
        return _SchemaFake()

    def prepare_index_params(self) -> _IndexParamsFake:
        return _IndexParamsFake()

    def create_collection(
        self,
        *,
        collection_name: str,
        schema: _SchemaFake,
        index_params: _IndexParamsFake,
        **_kwargs: Any,
    ) -> None:
        self.created_collections.append(collection_name)
        function_outputs = {
            output_name
            for function in schema.functions
            for output_name in function.get("output_field_names", [])
        }
        fields = []
        for raw_field in schema.fields:
            field_name = str(raw_field["field_name"])
            params = {
                key: raw_field[key]
                for key in (
                    "dim",
                    "max_length",
                    "enable_analyzer",
                    "analyzer_params",
                )
                if key in raw_field
            }
            fields.append(
                {
                    "name": field_name,
                    "type": raw_field["datatype"],
                    "params": params,
                    "is_function_output": field_name in function_outputs,
                }
            )
        indexes = {
            str(index["field_name"]): {
                "index_type": index["index_type"],
                "metric_type": index["metric_type"],
            }
            for index in index_params.indexes
        }
        self.collections[collection_name] = {
            "description": {
                "fields": fields,
                "functions": deepcopy(schema.functions),
            },
            "indexes": indexes,
        }

    def query(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.query_calls.append(kwargs)
        return self.query_responses.pop(0)


def _valid_collection(*, passage: bool) -> dict[str, Any]:
    fields: list[dict[str, Any]] = [
        {
            "name": "id",
            "type": DataType.VARCHAR,
            "params": {"max_length": 64},
        },
        {
            "name": "vector",
            "type": DataType.FLOAT_VECTOR,
            "params": {"dim": DIMENSION},
        },
        {
            "name": "text",
            "type": DataType.VARCHAR,
            "params": {"max_length": 65535},
        },
    ]
    functions: list[dict[str, Any]] = []
    indexes: dict[str, dict[str, str]] = {
        "vector": {"index_type": "HNSW", "metric_type": "IP"}
    }
    if passage:
        fields.extend(
            [
                {
                    "name": "lexical_text",
                    "type": DataType.VARCHAR,
                    "params": {
                        "max_length": 65535,
                        "enable_analyzer": True,
                        "analyzer_params": {"type": "chinese"},
                    },
                },
                {
                    "name": "sparse",
                    "type": DataType.SPARSE_FLOAT_VECTOR,
                    "params": {},
                    "is_function_output": True,
                },
            ]
        )
        functions.append(
            {
                "name": "passage_bm25",
                "type": FunctionType.BM25,
                "input_field_names": ["lexical_text"],
                "output_field_names": ["sparse"],
            }
        )
        indexes["sparse"] = {
            "index_type": "SPARSE_INVERTED_INDEX",
            "metric_type": "BM25",
        }
    return {
        "description": {"fields": fields, "functions": functions},
        "indexes": indexes,
    }


def _store(client: _MilvusClientFake) -> TaichuHNSWMilvusStore:
    store = object.__new__(TaichuHNSWMilvusStore)
    store.client = client
    store.entity_collection = ENTITY_COLLECTION
    store.relation_collection = RELATION_COLLECTION
    store.passage_collection = PASSAGE_COLLECTION
    store.embedding_model = SimpleNamespace(dimension=DIMENSION)
    store.settings = SimpleNamespace(
        milvus_index_type="HNSW",
        milvus_index_params={"M": 24, "efConstruction": 200},
        milvus_consistency_level="Bounded",
    )
    return store


def _assert_no_destructive_or_data_writes(client: _MilvusClientFake) -> None:
    client.drop_collection.assert_not_called()
    client.insert.assert_not_called()
    client.upsert.assert_not_called()
    client.delete.assert_not_called()


@pytest.mark.parametrize("top_k", [10, 150, 151, 300])
@pytest.mark.parametrize("search", ["entity", "relation", "neighbor", "passage", "hybrid"])
def test_hnsw_search_breadth_covers_actual_candidate_limit(top_k, search) -> None:
    client = _MilvusClientFake()
    client.search = Mock(return_value=[[]])
    client.hybrid_search = Mock(return_value=[[]])
    store = _store(client)
    store.ef_search = 150
    store.rrf_k = 60
    if search == "entity":
        store._search_entities([[0.0] * DIMENSION], top_k=top_k)
    elif search == "relation":
        store._search_relations([0.0] * DIMENSION, top_k=top_k)
    elif search == "neighbor":
        store.search_neighbor_relations([0.0] * DIMENSION, [str(i) for i in range(400)], top_k=top_k)
    elif search == "passage":
        store.search_passages([0.0] * DIMENSION, top_k=top_k)
    else:
        store.hybrid_search_passages(lexical_query="测试", query_embedding=[0.0] * DIMENSION, top_k=top_k)
    if search == "hybrid":
        request = client.hybrid_search.call_args.kwargs["reqs"][1]
        parameters, limit = request.param, request.limit
    else:
        call = client.search.call_args.kwargs
        parameters, limit = call["search_params"], call["limit"]
    assert parameters["params"]["ef"] == max(150, limit)
    assert limit == top_k
    _assert_no_destructive_or_data_writes(client)


def test_existing_incompatible_passage_stops_before_create_or_write() -> None:
    incompatible_passage = _valid_collection(passage=True)
    incompatible_passage["description"]["fields"] = [
        field
        for field in incompatible_passage["description"]["fields"]
        if field["name"] not in {"lexical_text", "sparse"}
    ]
    client = _MilvusClientFake(
        {
            ENTITY_COLLECTION: _valid_collection(passage=False),
            RELATION_COLLECTION: _valid_collection(passage=False),
            PASSAGE_COLLECTION: incompatible_passage,
        }
    )

    with pytest.raises(RuntimeError) as error:
        _store(client).ensure_incremental_collections()

    message = str(error.value)
    assert "Milvus 向量图谱集合结构与当前配置不兼容" in message
    assert "系统不会自动删除或重建集合" in message
    assert "passages 缺少字段 lexical_text, sparse" in message
    assert client.create_schema_calls == 0
    assert client.created_collections == []
    _assert_no_destructive_or_data_writes(client)


def test_existing_compatible_schema_passes_read_only_validation() -> None:
    client = _MilvusClientFake(
        {
            ENTITY_COLLECTION: _valid_collection(passage=False),
            RELATION_COLLECTION: _valid_collection(passage=False),
            PASSAGE_COLLECTION: _valid_collection(passage=True),
        }
    )

    _store(client).ensure_incremental_collections()

    assert set(client.described_collections) == {
        ENTITY_COLLECTION,
        RELATION_COLLECTION,
        PASSAGE_COLLECTION,
    }
    assert client.create_schema_calls == 0
    assert client.created_collections == []
    _assert_no_destructive_or_data_writes(client)


def test_partial_collections_are_blocked_without_supplementing_missing_ones() -> None:
    client = _MilvusClientFake({PASSAGE_COLLECTION: _valid_collection(passage=True)})

    with pytest.raises(RuntimeError) as error:
        _store(client).ensure_incremental_collections()

    assert "三类集合只存在一部分" in str(error.value)
    assert "系统不会自动创建缺失集合" in str(error.value)
    assert client.created_collections == []
    assert client.described_collections == []
    _assert_no_destructive_or_data_writes(client)


def test_empty_milvus_creates_all_collections_and_validates_them() -> None:
    client = _MilvusClientFake()

    _store(client).ensure_incremental_collections()

    assert set(client.created_collections) == {
        ENTITY_COLLECTION,
        RELATION_COLLECTION,
        PASSAGE_COLLECTION,
    }
    assert set(client.described_collections) == {
        ENTITY_COLLECTION,
        RELATION_COLLECTION,
        PASSAGE_COLLECTION,
    }
    _assert_no_destructive_or_data_writes(client)


def test_passage_source_counts_paginates_and_counts_each_actual_row() -> None:
    client = _MilvusClientFake()
    client.query_responses = [
        [{"source": "chapter:1"}, {"source": "chapter:1"}],
        [{"source": "chapter:2"}, {"source": ""}],
        [],
    ]

    counts = _store(client).passage_source_counts(batch_size=2)

    assert counts == {"chapter:1": 2, "chapter:2": 1}
    assert [item["offset"] for item in client.query_calls] == [0, 2, 4]
    assert all(item["output_fields"] == ["source"] for item in client.query_calls)


def test_entity_backlinks_are_bounded_before_upsert() -> None:
    client = _MilvusClientFake()
    store = _store(client)
    store.settings.batch_size = 4
    relation_ids = [f"relation-{index}" for index in range(1_300)]
    passage_ids = [f"passage-{index}" for index in range(300)]

    store._upsert_entity_records(
        [
            {
                "id": "entity-1",
                "text": "秦浩轩",
                "vector": [0.1] * DIMENSION,
                "relation_ids": relation_ids,
                "passage_ids": passage_ids,
            }
        ]
    )

    written = client.upsert.call_args.kwargs["data"][0]
    assert written["relation_ids"] == relation_ids[-1_200:]
    assert written["passage_ids"] == passage_ids[-256:]
