"""按来源增量更新正文 Markdown 与已确认知识卡的 Milvus Vector Graph RAG。"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from taichu.application.services.chapter_service import ChapterService
from taichu.application.vector_graph import VectorGraphRAGService
from taichu.config import Settings
from taichu.infrastructure.knowledge import MongoKnowledgeRepository
from taichu.infrastructure.llm.catalog import LLMModelCatalog
from taichu.infrastructure.llm.rightcode import RightCodeLLMGateway
from taichu.infrastructure.llm_replays import JsonLLMCallReplayRepository
from taichu.infrastructure.llm_usage import JsonlLLMUsageRepository
from taichu.infrastructure.storage.markdown_backend import ProjectAssetStorageBackend
from taichu.infrastructure.vector_graph import (
    BGEReranker,
    HybridVectorGraphBackend,
    MilvusVectorGraphBackend,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "按稳定来源键增量更新 Milvus 多跳图索引：新增或变化来源整源替换，"
            "消失来源删除，未变化来源跳过。"
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只输出章节、切片、知识卡数量和当前语料快照，不调用模型或写入 Milvus。",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    settings = Settings()
    repository = MongoKnowledgeRepository(
        settings.mongodb_uri,
        settings.mongodb_database,
    )
    storage = ProjectAssetStorageBackend(settings.project_assets_dir)
    model_catalog = LLMModelCatalog(settings)
    llm = RightCodeLLMGateway(
        settings,
        model_catalog,
        JsonlLLMUsageRepository(settings.project_assets_dir),
        replay_repository=JsonLLMCallReplayRepository(settings.project_assets_dir),
    )
    milvus_backend = MilvusVectorGraphBackend(
        milvus_uri=settings.milvus_uri,
        milvus_token=settings.milvus_token.get_secret_value(),
        collection_prefix=settings.milvus_collection_prefix,
        llm=llm,
        llm_model=(settings.vector_graph_llm_model or model_catalog.default_model_id),
        embedding_base_url=settings.embedding_base_url,
        embedding_model=settings.embedding_model_id,
        embedding_dimensions=settings.embedding_dimensions,
        manifest_path=(
            settings.project_assets_dir
            / "generated"
            / "milvus_vector_graph"
            / "active_manifest.json"
        ),
        hnsw_m=settings.milvus_hnsw_m,
        hnsw_ef_construction=settings.milvus_hnsw_ef_construction,
        hnsw_ef_search=settings.milvus_hnsw_ef_search,
        rrf_k=settings.milvus_rrf_k,
        entity_top_k=settings.vector_graph_entity_top_k,
        relation_top_k=settings.vector_graph_relation_top_k,
        expansion_degree=settings.vector_graph_expansion_degree,
        relation_number_threshold=settings.vector_graph_relation_number_threshold,
        final_top_k=settings.vector_graph_ann_top_k,
    )
    backend = HybridVectorGraphBackend(
        milvus=milvus_backend,
        reranker=BGEReranker(
            base_url=settings.reranker_base_url,
            model_id=settings.reranker_model_id,
            timeout_seconds=settings.reranker_request_timeout_seconds,
        ),
        candidate_top_k=settings.vector_graph_ann_top_k,
        final_top_k=settings.vector_graph_reranker_top_k,
    )
    service = VectorGraphRAGService(
        chapter_service=ChapterService(storage),
        knowledge_repository=repository,
        backend=backend,
        manuscript_chunk_size=settings.vector_graph_manuscript_chunk_size,
        manuscript_chunk_overlap=settings.vector_graph_manuscript_chunk_overlap,
    )
    await repository.initialize()
    try:
        result = await service.update(dry_run=args.dry_run)
        _print_json(result.model_dump(mode="json"))
        return 0
    finally:
        await backend.close()
        await repository.close()


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    return asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
