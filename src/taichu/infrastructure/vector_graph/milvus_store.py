"""为 Vector Graph RAG 提供 HNSW、BM25 与原生 RRF 混合检索。"""

import json
from typing import Any

from pymilvus import (  # type: ignore[import-untyped]
    AnnSearchRequest,
    DataType,
    Function,
    FunctionType,
    RRFRanker,
)
from vector_graph_rag.storage.milvus import MilvusStore  # type: ignore[import-untyped]


class TaichuHNSWMilvusStore(MilvusStore):
    MAX_ENTITY_RELATION_IDS = 1_200
    MAX_ENTITY_PASSAGE_IDS = 256

    def __init__(
        self,
        *args: Any,
        ef_search: int,
        rrf_k: int = 60,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.ef_search = ef_search
        self.rrf_k = rrf_k

    @property
    def _search_params(self) -> dict[str, Any]:
        return {"metric_type": "IP", "params": {"ef": self.ef_search}}

    def _search_entities(
        self,
        query_embeddings: list[list[float]],
        top_k: int | None = None,
    ) -> list[list[dict[str, Any]]]:
        return self.client.search(
            collection_name=self.entity_collection,
            data=query_embeddings,
            limit=top_k or self.settings.entity_top_k,
            search_params=self._search_params,
            output_fields=["id", "text", "relation_ids", "passage_ids"],
        )

    def _search_relations(
        self,
        query_embedding: list[float],
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        results = self.client.search(
            collection_name=self.relation_collection,
            data=[query_embedding],
            limit=top_k or self.settings.relation_top_k,
            search_params=self._search_params,
            output_fields=[
                "id",
                "text",
                "entity_ids",
                "passage_ids",
                "subject",
                "predicate",
                "object",
            ],
        )
        return results[0] if results else []

    def search_neighbor_relations(
        self,
        query_embedding: list[float],
        relation_ids: list[str],
        *,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """只在一个实体的邻接关系中执行 Query-aware ANN。"""

        unique_ids = list(dict.fromkeys(relation_ids))
        if not unique_ids or top_k < 1:
            return []
        limit = min(top_k, len(unique_ids))
        results = self.client.search(
            collection_name=self.relation_collection,
            data=[query_embedding],
            limit=limit,
            filter=f"id in {json.dumps(unique_ids, ensure_ascii=False)}",
            search_params=self._search_params,
            output_fields=[
                "id",
                "text",
                "entity_ids",
                "passage_ids",
                "subject",
                "predicate",
                "object",
            ],
        )
        return results[0] if results else []

    def _create_collection(
        self,
        collection_name: str,
        dimension: int | None = None,
        drop_existing: bool = False,
    ) -> None:
        if collection_name != self.passage_collection:
            super()._create_collection(
                collection_name,
                dimension=dimension,
                drop_existing=drop_existing,
            )
            return
        if self.client.has_collection(collection_name):
            if drop_existing:
                self.client.drop_collection(collection_name)
            else:
                return

        schema = self.client.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field(
            field_name="id",
            datatype=DataType.VARCHAR,
            max_length=64,
            is_primary=True,
        )
        schema.add_field(
            field_name="vector",
            datatype=DataType.FLOAT_VECTOR,
            dim=dimension or self.embedding_model.dimension,
        )
        schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(
            field_name="lexical_text",
            datatype=DataType.VARCHAR,
            max_length=65535,
            enable_analyzer=True,
            analyzer_params={"type": "chinese"},
        )
        schema.add_field(
            field_name="sparse",
            datatype=DataType.SPARSE_FLOAT_VECTOR,
        )
        schema.add_function(
            Function(
                name="passage_bm25",
                function_type=FunctionType.BM25,
                input_field_names=["lexical_text"],
                output_field_names=["sparse"],
            )
        )

        index_params = self.client.prepare_index_params()
        dense_index: dict[str, Any] = {
            "field_name": "vector",
            "index_type": self.settings.milvus_index_type,
            "metric_type": "IP",
        }
        if self.settings.milvus_index_params:
            dense_index["params"] = self.settings.milvus_index_params
        index_params.add_index(**dense_index)
        index_params.add_index(
            field_name="sparse",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="BM25",
        )
        self.client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,
            consistency_level=self.settings.milvus_consistency_level,
        )

    def ensure_incremental_collections(self) -> None:
        """确保增量写入使用兼容 Schema，且绝不自动删除已有集合。"""
        collection_names = {
            self.entity_collection,
            self.relation_collection,
            self.passage_collection,
        }
        existing = {
            collection_name
            for collection_name in collection_names
            if self.client.has_collection(collection_name)
        }
        if existing and existing != collection_names:
            missing = sorted(collection_names - existing)
            raise RuntimeError(
                "Milvus 向量图谱三类集合只存在一部分，已停止索引同步以避免"
                "把损坏状态误当成空集合补建。系统不会自动创建缺失集合，"
                f"请先完成一致性恢复。缺失集合：{', '.join(missing)}"
            )

        if existing:
            existing_issues = self._collection_schema_issues(existing)
            if not existing_issues:
                return
            raise RuntimeError(
                "Milvus 向量图谱集合结构与当前配置不兼容，已停止索引同步以避免"
                "破坏现有索引。系统不会自动删除或重建集合，请先执行一次性 "
                f"Schema 迁移。详情：{'；'.join(existing_issues)}"
            )

        # 只有三类集合全缺时才允许首次创建，部分缺失必须在上方阻断。
        self.create_collections(drop_existing=False)
        remaining = self._collection_schema_issues(collection_names)
        if remaining:
            raise RuntimeError(
                "Milvus 向量图谱集合创建后仍不符合当前配置，已停止索引同步："
                + "；".join(remaining)
            )

    def _collection_schema_issues(
        self,
        collection_names: set[str],
    ) -> list[str]:
        required_fields: dict[str, dict[str, DataType]] = {
            self.entity_collection: {
                "id": DataType.VARCHAR,
                "vector": DataType.FLOAT_VECTOR,
                "text": DataType.VARCHAR,
            },
            self.relation_collection: {
                "id": DataType.VARCHAR,
                "vector": DataType.FLOAT_VECTOR,
                "text": DataType.VARCHAR,
            },
            self.passage_collection: {
                "id": DataType.VARCHAR,
                "vector": DataType.FLOAT_VECTOR,
                "text": DataType.VARCHAR,
                "lexical_text": DataType.VARCHAR,
                "sparse": DataType.SPARSE_FLOAT_VECTOR,
            },
        }
        issues: list[str] = []
        expected_dimension = int(self.embedding_model.dimension)
        for collection_name, required in required_fields.items():
            if collection_name not in collection_names:
                continue
            if not self.client.has_collection(collection_name):
                issues.append(f"{collection_name} 不存在")
                continue
            description = self.client.describe_collection(collection_name)
            raw_fields = description.get("fields", []) if description else []
            fields = {
                str(field.get("name") or field.get("field_name")): field
                for field in raw_fields
                if isinstance(field, dict)
            }
            missing = sorted(set(required) - set(fields))
            if missing:
                issues.append(f"{collection_name} 缺少字段 {', '.join(missing)}")
                continue
            for field_name, expected_type in required.items():
                actual_type = fields[field_name].get("type") or fields[field_name].get(
                    "datatype"
                )
                if not _enum_matches(actual_type, expected_type):
                    issues.append(
                        f"{collection_name}.{field_name} 字段类型为 "
                        f"{actual_type or '未知'}，应为 {expected_type.name}"
                    )
            dimension = _field_dimension(fields["vector"])
            if dimension != expected_dimension:
                issues.append(
                    f"{collection_name} 向量维度为 {dimension or '未知'}，"
                    f"当前配置为 {expected_dimension}"
                )
            issues.extend(self._dense_index_issues(collection_name))

            if collection_name == self.passage_collection:
                issues.extend(
                    self._passage_bm25_issues(
                        description=description,
                        fields=fields,
                    )
                )
        return issues

    def _dense_index_issues(self, collection_name: str) -> list[str]:
        index_names = set(self.client.list_indexes(collection_name))
        if "vector" not in index_names:
            return [f"{collection_name}.vector 缺少稠密向量索引"]
        description = self.client.describe_index(collection_name, "vector")
        actual_type = str(description.get("index_type", "")).upper()
        actual_metric = str(description.get("metric_type", "")).upper()
        expected_type = str(self.settings.milvus_index_type).upper()
        issues: list[str] = []
        if actual_type != expected_type:
            issues.append(
                f"{collection_name}.vector 索引类型为 {actual_type or '未知'}，"
                f"当前配置为 {expected_type}"
            )
        if actual_metric != "IP":
            issues.append(
                f"{collection_name}.vector 距离度量为 {actual_metric or '未知'}，"
                "应为 IP"
            )
        return issues

    def _passage_bm25_issues(
        self,
        *,
        description: dict[str, Any],
        fields: dict[str, dict[str, Any]],
    ) -> list[str]:
        issues: list[str] = []
        lexical_params = fields["lexical_text"].get("params", {})
        if not isinstance(lexical_params, dict):
            lexical_params = {}
        analyzer_enabled = lexical_params.get("enable_analyzer")
        analyzer_params = _json_mapping(lexical_params.get("analyzer_params"))
        if not _is_truthy(analyzer_enabled):
            issues.append(f"{self.passage_collection}.lexical_text 未启用中文分词器")
        if str(analyzer_params.get("type", "")).lower() != "chinese":
            issues.append(f"{self.passage_collection}.lexical_text 分词器不是 chinese")
        if not _is_truthy(fields["sparse"].get("is_function_output")):
            issues.append(f"{self.passage_collection}.sparse 不是 BM25 函数输出字段")

        raw_functions = description.get("functions", [])
        functions = [item for item in raw_functions if isinstance(item, dict)]
        has_bm25 = any(
            _enum_matches(item.get("type"), FunctionType.BM25)
            and item.get("input_field_names") == ["lexical_text"]
            and item.get("output_field_names") == ["sparse"]
            for item in functions
        )
        if not has_bm25:
            issues.append(
                f"{self.passage_collection} 缺少 lexical_text 到 sparse 的 BM25 函数"
            )

        index_names = set(self.client.list_indexes(self.passage_collection))
        if "sparse" not in index_names:
            issues.append(f"{self.passage_collection}.sparse 缺少 BM25 索引")
        else:
            sparse_index = self.client.describe_index(
                self.passage_collection,
                "sparse",
            )
            sparse_type = str(sparse_index.get("index_type", "")).upper()
            sparse_metric = str(sparse_index.get("metric_type", "")).upper()
            if sparse_type != "SPARSE_INVERTED_INDEX":
                issues.append(
                    f"{self.passage_collection}.sparse 索引类型为 "
                    f"{sparse_type or '未知'}，应为 SPARSE_INVERTED_INDEX"
                )
            if sparse_metric != "BM25":
                issues.append(
                    f"{self.passage_collection}.sparse 距离度量为 "
                    f"{sparse_metric or '未知'}，应为 BM25"
                )
        return issues

    def insert_passages(
        self,
        passage_texts: list[str],
        ids: list[str] | None = None,
        embeddings: list[list[float]] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
        show_progress: bool = False,
    ) -> list[str]:
        lexical_metadatas: list[dict[str, Any]] = []
        for index, passage_text in enumerate(passage_texts):
            metadata = dict(metadatas[index]) if metadatas else {}
            title = str(metadata.get("title", "")).strip()
            content = (
                passage_text.split("\n", 1)[1] if "\n" in passage_text else passage_text
            )
            metadata["lexical_text"] = "\n".join(
                part for part in (title, title, content) if part
            )
            lexical_metadatas.append(metadata)
        return super().insert_passages(
            passage_texts,
            ids=ids,
            embeddings=embeddings,
            metadatas=lexical_metadatas,
            show_progress=show_progress,
        )

    def passage_source_counts(self, *, batch_size: int = 1_000) -> dict[str, int]:
        """统计每个稳定来源的实际 passage 数量，用于识别残缺写入。"""
        counts: dict[str, int] = {}
        offset = 0
        while True:
            records = self.client.query(
                collection_name=self.passage_collection,
                filter='id != ""',
                output_fields=["source"],
                limit=batch_size,
                offset=offset,
            )
            for record in records:
                source = str(record.get("source", "")).strip()
                if source:
                    counts[source] = counts.get(source, 0) + 1
            if len(records) < batch_size:
                break
            offset += len(records)
        return dict(sorted(counts.items()))

    def _upsert_entity_records(self, records: list[dict[str, Any]]) -> None:
        """限制中心实体的反向邻接表，避免超过 Milvus 动态字段上限。"""
        bounded: list[dict[str, Any]] = []
        for record in records:
            item = dict(record)
            item["relation_ids"] = list(item.get("relation_ids", []))[
                -self.MAX_ENTITY_RELATION_IDS :
            ]
            item["passage_ids"] = list(item.get("passage_ids", []))[
                -self.MAX_ENTITY_PASSAGE_IDS :
            ]
            bounded.append(item)
        super()._upsert_entity_records(bounded)

    def hybrid_search_passages(
        self,
        *,
        lexical_query: str,
        query_embedding: list[float],
        top_k: int,
        filter: str | None = None,
    ) -> list[dict[str, Any]]:
        requests = [
            AnnSearchRequest(
                data=[lexical_query],
                anns_field="sparse",
                param={"metric_type": "BM25", "params": {}},
                limit=top_k,
                expr=filter,
            ),
            AnnSearchRequest(
                data=[query_embedding],
                anns_field="vector",
                param=self._search_params,
                limit=top_k,
                expr=filter,
            ),
        ]
        results = self.client.hybrid_search(
            collection_name=self.passage_collection,
            reqs=requests,
            ranker=RRFRanker(self.rrf_k),
            limit=top_k,
            output_fields=["id", "text", "entity_ids", "relation_ids"],
        )
        return results[0] if results else []

    def get_passage_chunks(
        self,
        *,
        source_id: str,
        chunk_indexes: list[int],
    ) -> list[dict[str, Any]]:
        if not chunk_indexes:
            return []
        quoted_source_id = self._quote_string(source_id)
        indexes = ", ".join(str(index) for index in chunk_indexes)
        return self.client.query(
            collection_name=self.passage_collection,
            filter=(
                f'source_type == "manuscript_chunk" and '
                f"source_id == {quoted_source_id} and chunk_index in [{indexes}]"
            ),
            output_fields=[
                "text",
                "source_id",
                "chunk_index",
                "start_char",
                "end_char",
            ],
        )

    def get_passages_by_ids(self, passage_ids: list[str]) -> list[dict[str, Any]]:
        """按图关系的 ``passage_ids`` 直接回取 Passage。"""

        unique_ids = list(dict.fromkeys(passage_ids))
        if not unique_ids:
            return []
        return self.client.query(
            collection_name=self.passage_collection,
            filter=f"id in {json.dumps(unique_ids, ensure_ascii=False)}",
            output_fields=["id", "text", "entity_ids", "relation_ids"],
        )

    def search_passages(
        self,
        query_embedding: list[float],
        top_k: int | None = None,
        filter: str | None = None,
    ) -> list[dict[str, Any]]:
        results = self.client.search(
            collection_name=self.passage_collection,
            data=[query_embedding],
            limit=top_k or self.settings.final_top_k,
            filter=filter,
            search_params=self._search_params,
            output_fields=["id", "text", "entity_ids", "relation_ids"],
        )
        return results[0] if results else []


def _field_dimension(field: dict[str, Any]) -> int | None:
    raw_dimension = field.get("dim")
    if raw_dimension is None:
        params = field.get("params")
        if isinstance(params, dict):
            raw_dimension = params.get("dim")
    if raw_dimension is None:
        return None
    try:
        return int(raw_dimension)
    except (TypeError, ValueError):
        return None


def _enum_matches(value: object, expected: object) -> bool:
    if value == expected:
        return True
    actual_name = getattr(value, "name", None)
    expected_name = getattr(expected, "name", None)
    if actual_name is not None and expected_name is not None:
        return str(actual_name).upper() == str(expected_name).upper()
    return str(value).split(".")[-1].upper() == str(expected).split(".")[-1].upper()


def _json_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
