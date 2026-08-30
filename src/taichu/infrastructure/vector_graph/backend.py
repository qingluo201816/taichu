"""封装 Milvus 团队 vector-graph-rag 库，保持应用层契约稳定。"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from collections.abc import Iterable
from typing import Any, cast

from langchain_core.documents import Document
from langchain_core.language_models.chat_models import BaseChatModel
from pymilvus import MilvusClient  # type: ignore[import-untyped]
from vector_graph_rag.config import Settings as VectorGraphSettings  # type: ignore[import-untyped]

from taichu.application.vector_graph.corpus import (
    build_source_index_state,
    compact_knowledge_card_context,
    group_source_documents,
)
from taichu.application.vector_graph.models import (
    VectorGraphBuildPlan,
    VectorGraphBuildProgress,
    VectorGraphBuildResult,
    VectorGraphBuildStage,
    VectorGraphCollectionStatus,
    VectorGraphEvidence,
    VectorGraphExtractedTriplets,
    VectorGraphIndexState,
    VectorGraphIndexStatus,
    VectorGraphRetrievalResult,
    VectorGraphSourceDocument,
    VectorGraphSourceIndexManifest,
    VectorGraphSourceIndexState,
    VectorGraphSourceType,
)
from taichu.infrastructure.vector_graph.llm_adapter import (
    TaichuVectorGraphLLM,
)
from taichu.infrastructure.vector_graph.controlled_retriever import (
    ControlledExpansionSettings,
    PassageGraphSeed,
    PassageSeededExpansionResult,
    PassageSeededGraphExpander,
)
from taichu.infrastructure.vector_graph.embedding import BoundedEmbeddingModel
from taichu.infrastructure.vector_graph.rag import TaichuVectorGraphRAG
from taichu.infrastructure.vector_graph.milvus_store import TaichuHNSWMilvusStore

_SOURCE_HEADER = re.compile(r"^\[太初来源\](\{.*?\})\[/太初来源\]\n", re.S)


class MilvusVectorGraphBackend:
    """延迟连接 Milvus，避免基础设施暂不可用时阻断普通应用启动。"""

    def __init__(
        self,
        *,
        milvus_uri: str,
        milvus_token: str,
        collection_prefix: str,
        llm: BaseChatModel,
        llm_model: str,
        embedding_base_url: str,
        embedding_model: str,
        embedding_dimensions: int,
        manifest_path: Path,
        embedding_batch_size: int = 4,
        hnsw_m: int = 24,
        hnsw_ef_construction: int = 300,
        hnsw_ef_search: int = 150,
        rrf_k: int = 60,
        expansion_max_seed_entities: int = 5,
        expansion_max_seed_relations: int = 32,
        expansion_max_hop: int = 1,
        expansion_max_entities_per_hop: int = 20,
        expansion_relations_per_entity: int = 10,
        expansion_candidate_pool_multiplier: int = 4,
        expansion_hub_relations_per_entity: int = 5,
        expansion_hub_degree_threshold: int = 100,
        expansion_beam_width: int = 24,
        expansion_max_total_relations: int = 56,
        expansion_max_graph_passages: int = 20,
        final_top_k: int = 30,
    ) -> None:
        self._settings = VectorGraphSettings(
            milvus_uri=milvus_uri,
            milvus_token=milvus_token or None,
            collection_prefix=collection_prefix,
            # 官方库会创建 OpenAI 客户端，但太初会替换所有模型调用点；
            # 这个占位值只满足上游配置校验，不会作为鉴权信息发送。
            openai_api_key="taichu-managed-llm",
            llm_model=llm_model,
            embedding_provider="openai",
            embedding_model=embedding_model,
            embedding_api_key="local-embedding-service",
            embedding_base_url=embedding_base_url,
            embedding_dimension=embedding_dimensions,
            # 本地 OpenAI 兼容服务按整批累计 Token 校验上下文窗口。
            # 正文章节通常含多个 1000 字符子块，使用小批次避免把整章
            # 一次发送后超过模型的 8192 Token 上限。
            batch_size=embedding_batch_size,
            milvus_index_type="HNSW",
            milvus_index_params={
                "M": hnsw_m,
                "efConstruction": hnsw_ef_construction,
            },
            final_top_k=final_top_k,
        )
        self._llm = TaichuVectorGraphLLM(llm, llm_model)
        self._controlled_expansion = ControlledExpansionSettings(
            max_seed_entities=expansion_max_seed_entities,
            max_seed_relations=expansion_max_seed_relations,
            max_hop=expansion_max_hop,
            max_entities_per_hop=expansion_max_entities_per_hop,
            relations_per_entity=expansion_relations_per_entity,
            candidate_pool_multiplier=expansion_candidate_pool_multiplier,
            hub_relations_per_entity=expansion_hub_relations_per_entity,
            hub_degree_threshold=expansion_hub_degree_threshold,
            beam_width=expansion_beam_width,
            max_total_relations=expansion_max_total_relations,
            max_graph_passages=expansion_max_graph_passages,
        )
        self._milvus_uri = milvus_uri
        self._milvus_token = milvus_token
        self._collection_names = {
            "passages": f"{collection_prefix}_vgrag_passages",
            "entities": f"{collection_prefix}_vgrag_entities",
            "relations": f"{collection_prefix}_vgrag_relations",
        }
        self._hnsw_ef_search = hnsw_ef_search
        self._rrf_k = rrf_k
        self._index_configuration_sha256 = _sha256_json(
            {
                "document_projection": "taichu-source-replacement",
                "graph_phrase_normalization": "taichu-unicode-alnum-v1",
                "vector_graph_rag": importlib.metadata.version("vector-graph-rag"),
                "llm_model": llm_model,
                "triplet_extraction": self._llm.extraction_configuration_sha256,
                "embedding_model": embedding_model,
                "embedding_dimensions": embedding_dimensions,
            }
        )
        self._manifest_path = manifest_path
        self._source_manifest_path = manifest_path.with_name("source_manifest.json")
        self._progress_path = manifest_path.with_name("build_status.json")
        self._rag: TaichuVectorGraphRAG | None = None
        self._lock = Lock()

    async def update(
        self,
        documents: list[VectorGraphSourceDocument],
        *,
        plan: VectorGraphBuildPlan,
        extracted_triplets: VectorGraphExtractedTriplets | None = None,
    ) -> VectorGraphBuildResult:
        if extracted_triplets is not None:
            expected_identities = {
                _document_identity(document) for document in documents
            }
            supplied_identities = set(extracted_triplets)
            if supplied_identities != expected_identities:
                missing = len(expected_identities - supplied_identities)
                extra = len(supplied_identities - expected_identities)
                raise ValueError(
                    "离线三元组与当前语料不完全一致："
                    f"缺少 {missing} 条，多出 {extra} 条。"
                )
        started_at = _utc_now()
        grouped = group_source_documents(documents)
        desired_states = {
            source: build_source_index_state(
                items,
                indexed_at=started_at,
                index_configuration_sha256=self._index_configuration_sha256,
            )
            for source, items in grouped.items()
        }
        source_manifest = _read_model_json(
            self._source_manifest_path,
            VectorGraphSourceIndexManifest,
        )
        active_build = _read_model_json(self._manifest_path, VectorGraphBuildResult)
        previous_progress = _read_model_json(
            self._progress_path,
            VectorGraphBuildProgress,
        )
        desired_source_counts = {
            source: state.document_count for source, state in desired_states.items()
        }

        if (
            source_manifest is None
            and active_build is not None
            and active_build.status == "completed"
            and active_build.plan.snapshot_sha256 == plan.snapshot_sha256
            and active_build.index_configuration_sha256
            == self._index_configuration_sha256
            and active_build.passage_count == plan.document_count
            and await asyncio.to_thread(
                self._can_adopt_existing_index_sync,
                active_build,
                desired_source_counts,
            )
        ):
            self._write_source_manifest(desired_states.values())
            adopted = active_build.model_copy(
                update={
                    "status": "completed",
                    "plan": plan,
                    "index_configuration_sha256": self._index_configuration_sha256,
                    "updated_source_count": 0,
                    "deleted_source_count": 0,
                    "unchanged_source_count": len(desired_states),
                }
            )
            self._write_manifest(adopted)
            self._write_progress(
                VectorGraphBuildProgress(
                    stage=VectorGraphBuildStage.COMPLETED,
                    snapshot_sha256=plan.snapshot_sha256,
                    processed_documents=0,
                    total_documents=0,
                    processed_sources=0,
                    total_sources=0,
                    started_at=started_at,
                    updated_at=_utc_now(),
                )
            )
            return adopted

        stored_states = {
            item.source_key: item
            for item in (source_manifest.sources if source_manifest is not None else [])
        }
        indexed_source_counts = await asyncio.to_thread(
            self._passage_source_counts_sync
        )
        indexed_sources = set(indexed_source_counts)
        baseline_counts = await asyncio.to_thread(self._collection_counts_sync)
        existing_sources = indexed_sources | set(stored_states)
        upsert_sources = [
            source
            for source, desired in desired_states.items()
            if source not in indexed_sources
            or source not in stored_states
            or stored_states[source].index_configuration_sha256
            != self._index_configuration_sha256
            or stored_states[source].source_sha256 != desired.source_sha256
            or indexed_source_counts[source] != stored_states[source].document_count
        ]
        delete_sources = sorted(existing_sources - set(desired_states))
        unsafe_zero_passage_deletes = [
            source
            for source in delete_sources
            if source in stored_states and indexed_source_counts.get(source, 0) == 0
        ]
        if unsafe_zero_passage_deletes:
            raise RuntimeError(
                "待删除来源仍存在于来源清单，但 Milvus 段落记录（passage）"
                "已为 0，无法确认实体与关系是否已完整级联删除。已在任何"
                "来源清单或完成基线改写前停止更新，请先恢复索引一致性。"
            )
        if (
            active_build is not None
            and baseline_counts[:2]
            != (active_build.entity_count, active_build.relation_count)
            and not _is_failed_source_resume(previous_progress)
        ):
            raise RuntimeError(
                "Milvus 实体或关系集合行数与最近一次完成清单不一致，"
                "已在任何来源删除或写入前停止索引同步。请先完成索引"
                "一致性恢复，系统不会把当前异常行数写成新的完成基线。"
            )
        unchanged_sources = sorted(set(desired_states) - set(upsert_sources))
        total_documents = sum(len(grouped[source]) for source in upsert_sources)
        total_sources = len(upsert_sources) + len(delete_sources)
        progress = VectorGraphBuildProgress(
            stage=(
                VectorGraphBuildStage.INDEXING
                if extracted_triplets is not None
                else VectorGraphBuildStage.EXTRACTING
            ),
            snapshot_sha256=plan.snapshot_sha256,
            total_documents=total_documents,
            total_sources=total_sources,
            started_at=started_at,
            updated_at=started_at,
        )
        self._write_progress(progress)
        working_states = dict(stored_states)
        try:
            for source in delete_sources:
                progress = progress.model_copy(
                    update={
                        "stage": VectorGraphBuildStage.INDEXING,
                        "current_source_key": source,
                        "updated_at": _utc_now(),
                    }
                )
                self._write_progress(progress)
                if indexed_source_counts.get(source, 0) > 0:
                    try:
                        deleted = await asyncio.to_thread(
                            self._delete_source_sync,
                            source,
                        )
                    except Exception as error:
                        raise RuntimeError(
                            f"Milvus 删除来源“{source}”失败，来源清单保持不变："
                            f"{str(error)[:500]}"
                        ) from error
                    if deleted is not True:
                        raise RuntimeError(
                            f"Milvus 未确认来源“{source}”删除成功，来源清单"
                            "保持不变，可从该失败来源重试。"
                        )
                working_states.pop(source, None)
                self._write_source_manifest(working_states.values())
                progress = progress.model_copy(
                    update={
                        "processed_sources": progress.processed_sources + 1,
                        "updated_at": _utc_now(),
                    }
                )

            for source in upsert_sources:
                source_documents = grouped[source]
                langchain_documents = [
                    self._to_document(document) for document in source_documents
                ]
                progress = progress.model_copy(
                    update={
                        "stage": (
                            VectorGraphBuildStage.INDEXING
                            if extracted_triplets is not None
                            else VectorGraphBuildStage.EXTRACTING
                        ),
                        "current_source_key": source,
                        "updated_at": _utc_now(),
                    }
                )
                self._write_progress(progress)
                for source_document, document in zip(
                    source_documents,
                    langchain_documents,
                    strict=True,
                ):
                    if extracted_triplets is None:
                        triplets = await self._llm.extract_triplets(
                            source_document.content
                        )
                    else:
                        triplets = [
                            list(item)
                            for item in extracted_triplets[
                                _document_identity(source_document)
                            ]
                        ]
                    document.metadata["triplets"] = triplets
                    progress = progress.model_copy(
                        update={
                            "processed_documents": progress.processed_documents + 1,
                            "updated_at": _utc_now(),
                        }
                    )
                    self._write_progress(progress)
                progress = progress.model_copy(
                    update={
                        "stage": VectorGraphBuildStage.INDEXING,
                        "updated_at": _utc_now(),
                    }
                )
                self._write_progress(progress)
                await asyncio.to_thread(
                    self._upsert_source_sync,
                    source,
                    langchain_documents,
                )
                working_states[source] = desired_states[source].model_copy(
                    update={"indexed_at": _utc_now()}
                )
                self._write_source_manifest(working_states.values())
                progress = progress.model_copy(
                    update={
                        "processed_sources": progress.processed_sources + 1,
                        "updated_at": _utc_now(),
                    }
                )

            final_source_counts = await asyncio.to_thread(
                self._passage_source_counts_sync
            )
            entity_count, relation_count, passage_count = await asyncio.to_thread(
                self._collection_counts_sync
            )
            if (
                final_source_counts != desired_source_counts
                or passage_count != plan.document_count
            ):
                raise RuntimeError(
                    "Milvus passage 来源数量与本次来源清单不一致，已保留逐来源"
                    "成功状态但不会写入完成清单；再次运行时将只重试数量不一致"
                    "的来源。"
                )
            result = VectorGraphBuildResult(
                status="completed",
                plan=plan,
                index_configuration_sha256=self._index_configuration_sha256,
                entity_count=entity_count,
                relation_count=relation_count,
                passage_count=passage_count,
                updated_source_count=len(upsert_sources),
                deleted_source_count=len(delete_sources),
                unchanged_source_count=len(unchanged_sources),
            )
            self._write_manifest(result)
        except Exception as error:
            self._write_progress(
                progress.model_copy(
                    update={
                        "stage": VectorGraphBuildStage.FAILED,
                        "updated_at": _utc_now(),
                        "error_message": str(error)[:2_000],
                    }
                )
            )
            raise
        self._write_progress(
            progress.model_copy(
                update={
                    "stage": VectorGraphBuildStage.COMPLETED,
                    "current_source_key": None,
                    "updated_at": _utc_now(),
                }
            )
        )
        return result

    async def inspect(self, plan: VectorGraphBuildPlan) -> VectorGraphIndexStatus:
        return await asyncio.to_thread(self._inspect_sync, plan)

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int,
    ) -> VectorGraphRetrievalResult:
        return await asyncio.to_thread(
            self._retrieve_passage_first_sync,
            query,
            top_k,
        )

    async def expand_context(
        self,
        evidences: list[VectorGraphEvidence],
    ) -> list[VectorGraphEvidence]:
        return await asyncio.to_thread(self._expand_context_sync, evidences)

    async def close(self) -> None:
        if self._rag is None:
            return
        await asyncio.to_thread(self._rag._store.client.close)

    def _upsert_source_sync(
        self,
        source: str,
        documents: list[Document],
    ) -> None:
        rag = self._get_rag()
        rag.upsert_documents_by_source(
            documents,
            source=source,
            extract_triplets=False,
            show_progress=False,
        )

    def _delete_source_sync(self, source: str) -> bool:
        return cast(bool, self._get_rag().delete_documents_by_source(source))

    def _passage_source_counts_sync(self) -> dict[str, int]:
        store = cast(TaichuHNSWMilvusStore, self._get_rag()._store)
        store.client.flush(collection_name=store.passage_collection)
        return store.passage_source_counts()

    def _can_adopt_existing_index_sync(
        self,
        active_build: VectorGraphBuildResult,
        desired_source_counts: dict[str, int],
    ) -> bool:
        client: MilvusClient | None = None
        try:
            client = MilvusClient(
                uri=self._milvus_uri,
                token=self._milvus_token or None,
            )
            if not all(
                client.has_collection(name) for name in self._collection_names.values()
            ):
                return False
            actual_counts: dict[str, int] = {}
            for role, name in self._collection_names.items():
                actual_counts[role] = _count_collection_records(client, name)
            if actual_counts != {
                "entities": active_build.entity_count,
                "relations": active_build.relation_count,
                "passages": active_build.passage_count,
            }:
                return False
        finally:
            if client is not None:
                client.close()

        prepared_store = TaichuHNSWMilvusStore(
            settings=self._settings,
            ef_search=self._hnsw_ef_search,
            rrf_k=self._rrf_k,
        )
        try:
            prepared_store.ensure_incremental_collections()
            if prepared_store.passage_source_counts() != desired_source_counts:
                return False
        finally:
            prepared_store.client.close()
        return True

    def _collection_counts_sync(self) -> tuple[int, int, int]:
        client = self._get_rag()._store.client
        for name in self._collection_names.values():
            client.flush(collection_name=name)
        counts = {
            role: _count_collection_records(client, name)
            for role, name in self._collection_names.items()
        }
        return counts["entities"], counts["relations"], counts["passages"]

    def _retrieve_passage_first_sync(
        self,
        query: str,
        top_k: int,
    ) -> VectorGraphRetrievalResult:
        rag = self._get_rag()
        query_embedding = rag._embedding_model.embed(query)
        store = cast(TaichuHNSWMilvusStore, rag._store)
        rrf_results = store.hybrid_search_passages(
            lexical_query=query,
            query_embedding=query_embedding,
            top_k=top_k,
        )
        seeds = _passage_graph_seeds(rrf_results)
        expansion = PassageSeededGraphExpander(
            store=store,
            settings=self._controlled_expansion,
        ).expand(
            query=query,
            query_embedding=query_embedding,
            seed_passages=seeds,
        )
        novel_graph_passage_ids = list(expansion.graph_passage_ids)
        graph_records = store.get_passages_by_ids(novel_graph_passage_ids)
        passages = _merge_passage_candidates(rrf_results, graph_records)
        relation_ids = _unique_strings(
            relation_id
            for passage in passages
            for relation_id in passage["relation_ids"]
        )
        relation_text_by_id = {
            str(item["id"]): str(item.get("text", ""))
            for item in store._get_relations_by_ids(relation_ids)
        }
        return self._build_retrieval_result(
            query=query,
            expansion=expansion,
            passages=passages,
            relation_text_by_id=relation_text_by_id,
            graph_passage_ids=novel_graph_passage_ids,
        )

    def _expand_context_sync(
        self,
        evidences: list[VectorGraphEvidence],
    ) -> list[VectorGraphEvidence]:
        store = cast(TaichuHNSWMilvusStore, self._get_rag()._store)
        expanded: list[VectorGraphEvidence] = []
        for evidence in evidences:
            if evidence.source_type is not VectorGraphSourceType.MANUSCRIPT_CHUNK:
                expanded.append(evidence)
                continue
            records = store.get_passage_chunks(
                source_id=evidence.source_id,
                chunk_indexes=_parent_indexes(evidence),
            )
            sources: list[dict[str, object]] = []
            for record in records:
                parsed = _parse_passage(str(record.get("text", "")))
                if parsed is None:
                    continue
                _metadata, content = parsed
                sources.append(
                    {
                        "source_id": record["source_id"],
                        "chunk_index": record["chunk_index"],
                        "start_char": record["start_char"],
                        "end_char": record["end_char"],
                        "content": content,
                    }
                )
            context = _merge_context_sources(sources)
            expanded.append(
                evidence if context is None else evidence.model_copy(update=context)
            )
        return expanded

    @staticmethod
    def _build_retrieval_result(
        *,
        query: str,
        expansion: PassageSeededExpansionResult,
        passages: list[dict[str, Any]],
        relation_text_by_id: dict[str, str],
        graph_passage_ids: list[str],
    ) -> VectorGraphRetrievalResult:
        evidences: list[VectorGraphEvidence] = []
        for passage in passages:
            parsed = _parse_passage(str(passage.get("text", "")))
            if parsed is None:
                continue
            metadata, content = parsed
            try:
                source_type = VectorGraphSourceType(str(metadata["source_type"]))
                source_id = str(metadata["source_id"])
                source_ref = str(metadata["source_ref"])
                title = str(metadata["title"])
            except (KeyError, ValueError, TypeError):
                continue
            if source_type is VectorGraphSourceType.KNOWLEDGE_CARD:
                content = compact_knowledge_card_context(content)
            evidences.append(
                VectorGraphEvidence(
                    passage_id=str(passage.get("id", "")),
                    source_type=source_type,
                    source_id=source_id,
                    source_ref=source_ref,
                    title=title,
                    content=content,
                    content_sha256=str(metadata["content_sha256"]),
                    rank=len(evidences) + 1,
                    chunk_index=int(metadata.get("chunk_index", 0)),
                    start_char=_optional_int(metadata.get("start_char")),
                    end_char=_optional_int(metadata.get("end_char")),
                    parent_start_char=_optional_int(metadata.get("parent_start_char")),
                    parent_end_char=_optional_int(metadata.get("parent_end_char")),
                    parent_chunk_indexes=[
                        int(str(item))
                        for item in metadata.get("parent_chunk_indexes", [])
                    ],
                    relation_ids=list(passage.get("relation_ids", [])),
                    relation_texts=[
                        relation_text_by_id[relation_id]
                        for relation_id in passage.get("relation_ids", [])
                        if relation_id in relation_text_by_id
                    ],
                    retrieval_channels=list(passage.get("retrieval_channels", [])),
                )
            )
        expanded_by_id = {
            item.relation_id: item.text for item in expansion.relations
        }
        return VectorGraphRetrievalResult(
            query=query,
            evidences=evidences,
            retrieved_relations=[
                expanded_by_id[item]
                for item in expansion.seed_relation_ids
                if item in expanded_by_id
            ],
            expanded_relations=[item.text for item in expansion.relations],
            seed_passage_ids=list(expansion.seed_passage_ids),
            seed_entity_ids=list(expansion.seed_entity_ids),
            seed_relation_ids=list(expansion.seed_relation_ids),
            graph_passage_ids=graph_passage_ids,
            source_refs=list(dict.fromkeys(item.source_ref for item in evidences)),
        )

    def _get_rag(self) -> TaichuVectorGraphRAG:
        with self._lock:
            if self._rag is None:
                prepared_store = TaichuHNSWMilvusStore(
                    settings=self._settings,
                    ef_search=self._hnsw_ef_search,
                    rrf_k=self._rrf_k,
                )
                try:
                    # 上游构造器会自行创建默认集合。先由太初 Store 建好并校验
                    # BM25＋Dense Schema，避免首次增量运行落成缺少稀疏字段的表。
                    prepared_store.ensure_incremental_collections()
                    rag = TaichuVectorGraphRAG(settings=self._settings)
                except Exception:
                    prepared_store.client.close()
                    raise
                default_store = rag._store
                bounded_embedding = BoundedEmbeddingModel(rag._embedding_model)
                rag._embedding_model = bounded_embedding
                prepared_store.embedding_model = bounded_embedding
                rag._store = prepared_store
                # pymilvus 以 URI 作为连接别名；两个 MilvusClient 在同一 URI
                # 下共享别名。关闭上游默认 Store 会同时断开刚准备好的 Store。
                # 默认 Store 随 rag 初始化结束失去引用，统一由 close() 关闭
                # 当前 prepared_store 的共享连接。
                del default_store
                self._rag = rag
            return self._rag

    @staticmethod
    def _to_document(document: VectorGraphSourceDocument) -> Document:
        metadata: dict[str, Any] = document.model_dump(mode="json", exclude={"content"})
        metadata["source"] = f"{document.source_type.value}:{document.source_id}"
        header = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
        return Document(
            page_content=f"[太初来源]{header}[/太初来源]\n{document.content}",
            metadata=metadata,
        )

    def _write_manifest(self, result: VectorGraphBuildResult) -> None:
        _write_model_json(self._manifest_path, result)

    def _write_progress(self, progress: VectorGraphBuildProgress) -> None:
        _write_model_json(self._progress_path, progress)

    def _write_source_manifest(
        self,
        states: Iterable[VectorGraphSourceIndexState],
    ) -> None:
        ordered = sorted(states, key=lambda item: item.source_key)
        _write_model_json(
            self._source_manifest_path,
            VectorGraphSourceIndexManifest(
                sources=ordered,
                updated_at=_utc_now(),
            ),
        )

    def _inspect_sync(self, plan: VectorGraphBuildPlan) -> VectorGraphIndexStatus:
        progress = _read_model_json(self._progress_path, VectorGraphBuildProgress)
        active_build = _read_model_json(self._manifest_path, VectorGraphBuildResult)
        source_manifest = _read_model_json(
            self._source_manifest_path,
            VectorGraphSourceIndexManifest,
        )
        client: MilvusClient | None = None
        try:
            client = MilvusClient(
                uri=self._milvus_uri,
                token=self._milvus_token or None,
            )
            collections = [
                _inspect_collection(client, role, name)
                for role, name in self._collection_names.items()
            ]
        except Exception as error:
            return VectorGraphIndexStatus(
                state=VectorGraphIndexState.UNAVAILABLE,
                current_plan=plan,
                progress=progress,
                active_build=active_build,
                message=f"Milvus 状态读取失败：{str(error)[:500]}",
            )
        finally:
            if client is not None:
                client.close()

        all_exist = all(item.exists for item in collections)
        any_exist = any(item.exists for item in collections)
        collection_counts_match = (
            active_build is not None
            and all_exist
            and {item.role: item.row_count for item in collections}
            == {
                "entities": active_build.entity_count,
                "relations": active_build.relation_count,
                "passages": active_build.passage_count,
            }
        )
        active_configuration_is_current = (
            active_build is not None
            and active_build.index_configuration_sha256
            == self._index_configuration_sha256
        )
        source_configuration_is_current = source_manifest is not None and all(
            item.index_configuration_sha256 == self._index_configuration_sha256
            for item in source_manifest.sources
        )
        is_current = (
            active_build is not None
            and active_build.status == "completed"
            and active_build.plan.snapshot_sha256 == plan.snapshot_sha256
            and all_exist
            and collection_counts_match
            and active_configuration_is_current
            and source_configuration_is_current
        )
        if progress is not None and progress.stage in {
            VectorGraphBuildStage.EXTRACTING,
            VectorGraphBuildStage.INDEXING,
        }:
            state = VectorGraphIndexState.BUILDING
            if progress.snapshot_sha256 != plan.snapshot_sha256:
                message = "正在基于较早快照同步；源数据已变化，完成后仍需再次同步索引。"
            else:
                message = (
                    "正在抽取实体与关系。"
                    if progress.stage is VectorGraphBuildStage.EXTRACTING
                    else "正在写入 Milvus 三类集合。"
                )
        elif progress is not None and progress.stage is VectorGraphBuildStage.FAILED:
            state = VectorGraphIndexState.FAILED
            message = "最近一次索引同步失败，可查看失败来源和原因后重试。"
        elif active_build is None:
            if any_exist:
                state = VectorGraphIndexState.INCOMPLETE
                message = "存在未完成的 Milvus 集合，需要继续同步索引。"
            else:
                state = VectorGraphIndexState.NOT_BUILT
                message = "尚未建立 Milvus 向量图谱索引。"
        elif not all_exist:
            state = VectorGraphIndexState.INCOMPLETE
            message = "Milvus 三类集合不完整，需要继续同步索引。"
        elif not collection_counts_match:
            state = VectorGraphIndexState.INCOMPLETE
            message = (
                "Milvus 集合实际行数与最近一次完成清单不一致，需要先恢复索引一致性。"
            )
        elif is_current:
            state = VectorGraphIndexState.READY
            message = "当前索引与正文、知识卡快照一致。"
        elif active_build.plan.snapshot_sha256 == plan.snapshot_sha256 and (
            not source_configuration_is_current or not active_configuration_is_current
        ):
            state = VectorGraphIndexState.STALE
            message = (
                "索引来源状态尚未接管，或抽取与嵌入配置已变化，需要执行一次索引同步。"
            )
        else:
            state = VectorGraphIndexState.STALE
            message = "正文或知识卡已变化，当前索引需要更新。"
        return VectorGraphIndexStatus(
            state=state,
            current_plan=plan,
            progress=progress,
            active_build=active_build,
            is_current=is_current,
            collections=collections,
            message=message,
        )


def _parse_passage(passage: str) -> tuple[dict[str, Any], str] | None:
    match = _SOURCE_HEADER.match(passage)
    if match is None:
        return None
    try:
        metadata = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(metadata, dict):
        return None
    return metadata, passage[match.end() :]


def _passage_graph_seeds(
    results: list[dict[str, Any]],
) -> list[PassageGraphSeed]:
    seeds: list[PassageGraphSeed] = []
    seen: set[str] = set()
    for rank, result in enumerate(results, start=1):
        record = result.get("entity", {})
        passage_id = str(record.get("id", ""))
        if not passage_id or passage_id in seen:
            continue
        seen.add(passage_id)
        seeds.append(
            PassageGraphSeed(
                passage_id=passage_id,
                rank=rank,
                score=float(result.get("distance", 0.0)),
                entity_ids=tuple(
                    str(item) for item in record.get("entity_ids", [])
                ),
                relation_ids=tuple(
                    str(item) for item in record.get("relation_ids", [])
                ),
            )
        )
    return seeds


def _merge_passage_candidates(
    rrf_results: list[dict[str, Any]],
    graph_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for result in rrf_results:
        record = dict(result.get("entity", {}))
        passage_id = str(record.get("id", ""))
        if not passage_id:
            continue
        record["entity_ids"] = list(record.get("entity_ids", []))
        record["relation_ids"] = list(record.get("relation_ids", []))
        record["retrieval_channels"] = ["bm25_dense_rrf"]
        merged.setdefault(passage_id, record)
    for source in graph_records:
        record = dict(source)
        passage_id = str(record.get("id", ""))
        if not passage_id:
            continue
        current = merged.get(passage_id)
        if current is None:
            record["entity_ids"] = list(record.get("entity_ids", []))
            record["relation_ids"] = list(record.get("relation_ids", []))
            record["retrieval_channels"] = ["graph_expansion"]
            merged[passage_id] = record
            continue
        current["retrieval_channels"] = list(
            dict.fromkeys([*current["retrieval_channels"], "graph_expansion"])
        )
    return list(merged.values())


def _document_identity(
    document: VectorGraphSourceDocument,
) -> tuple[str, int, str]:
    return (
        document.source_ref,
        document.chunk_index,
        document.content_sha256,
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _parent_indexes(evidence: VectorGraphEvidence) -> list[int]:
    if evidence.parent_chunk_indexes:
        return evidence.parent_chunk_indexes
    return list(range(max(0, evidence.chunk_index - 1), evidence.chunk_index + 2))


def _merge_context_sources(
    sources: list[dict[str, object]],
) -> dict[str, object] | None:
    ordered = sorted(sources, key=lambda item: _as_int(item["chunk_index"]))
    if not ordered:
        return None
    first = ordered[0]
    source_id = str(first["source_id"])
    start_char = _as_int(first["start_char"])
    end_char = _as_int(first["end_char"])
    content = str(first["content"])
    indexes = [_as_int(first["chunk_index"])]
    for source in ordered[1:]:
        next_start = _as_int(source["start_char"])
        next_end = _as_int(source["end_char"])
        next_content = str(source["content"])
        overlap = end_char - next_start
        if overlap >= 0:
            content += next_content[min(overlap, len(next_content)) :]
        else:
            content += "\n\n" + next_content
        end_char = max(end_char, next_end)
        indexes.append(_as_int(source["chunk_index"]))
    return {
        "context_content": content,
        "context_source_ref": f"manuscript:{source_id}:{start_char}-{end_char}",
        "context_start_char": start_char,
        "context_end_char": end_char,
        "context_chunk_indexes": indexes,
    }


def _as_int(value: object) -> int:
    return int(str(value))


def _unique_strings(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _is_failed_source_resume(
    progress: VectorGraphBuildProgress | None,
) -> bool:
    return (
        progress is not None
        and progress.stage is VectorGraphBuildStage.FAILED
        and progress.current_source_key is not None
    )


def _sha256_json(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_model_json(path: Path, model: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary_path.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")
    try:
        for attempt in range(6):
            try:
                temporary_path.replace(path)
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        temporary_path.unlink(missing_ok=True)


def _read_model_json(path: Path, model_type: type[Any]) -> Any | None:
    try:
        return model_type.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _inspect_collection(
    client: MilvusClient,
    role: str,
    name: str,
) -> VectorGraphCollectionStatus:
    exists = bool(client.has_collection(name))
    row_count: int | None = None
    if exists:
        row_count = _count_collection_records(client, name)
    return VectorGraphCollectionStatus(
        role=role,
        name=name,
        exists=exists,
        row_count=row_count,
    )


def _count_collection_records(client: MilvusClient, name: str) -> int:
    iterator = client.query_iterator(
        collection_name=name,
        batch_size=1_000,
        filter='id != ""',
        output_fields=["id"],
    )
    count = 0
    try:
        while records := iterator.next():
            count += len(records)
    finally:
        iterator.close()
    return count
