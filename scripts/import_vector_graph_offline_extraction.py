"""校验 ChatGPT 网页离线抽取结果并写入 Milvus。"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from taichu.application.services.chapter_service import ChapterService
from taichu.application.vector_graph import VectorGraphRAGService
from taichu.application.vector_graph.offline_extraction import (
    load_offline_extraction_package,
)
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
            "独立校验离线三元组与当前语料快照，校验通过后"
            "跳过 LLM 抽取，直接构建 Milvus Vector Graph RAG。"
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("taichu_vector_graph_offline_extraction_input.jsonl"),
        help="离线抽取输入 JSONL 路径。",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("taichu_vector_graph_offline_extraction_output"),
        help="包含 manifest.json、triplets.jsonl 和 validation_report.json 的目录。",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="只校验输入和输出，不写入 Milvus。",
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
        plan, documents = await service.plan()
        package = load_offline_extraction_package(
            input_path=args.input.resolve(),
            output_dir=args.output_dir.resolve(),
            plan=plan,
            documents=documents,
        )
        validation = {
            "status": "validated",
            "snapshot_sha256": package.snapshot_sha256,
            "document_count": package.document_count,
            "triplet_count": package.triplet_count,
            "warning_count": package.warning_count,
            "triplets_file_sha256": package.triplets_file_sha256,
            "producer": {
                "surface": package.producer_surface,
                "model": package.producer_model,
            },
        }
        if args.validate_only:
            _print_json(validation)
            return 0

        result = await service.update(extracted_triplets=package.triplets)
        receipt = {
            **validation,
            "status": "imported",
            "imported_at": datetime.now(UTC).isoformat(),
            "build_result": result.model_dump(mode="json"),
        }
        receipt_path = (
            settings.project_assets_dir
            / "generated"
            / "milvus_vector_graph"
            / "offline_import_receipt.json"
        )
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = receipt_path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(receipt_path)
        _print_json(receipt)
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
