"""显式全量重建或校验知识卡 Qdrant 派生索引。"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from taichu.application.services.knowledge_vector_index_service import (
    KnowledgeVectorIndexService,
)
from taichu.config import Settings
from taichu.infrastructure.embedding import (
    JsonlEmbeddingUsageRepository,
    LlamaCppEmbeddingGateway,
)
from taichu.infrastructure.knowledge import MongoKnowledgeRepository
from taichu.infrastructure.retrieval.vector_index import (
    JsonVectorIndexManifestRepository,
    QdrantVectorIndexBackend,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从 MongoDB 已确认知识卡全量重建或校验 Qdrant 向量索引。"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="只输出卡片数、片段数和快照，不调用 Embedding 或写入 Qdrant。",
    )
    mode.add_argument(
        "--verify-only",
        action="store_true",
        help="只校验 active 清单、Mongo 快照、Qdrant alias、条目数和维度。",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    settings = Settings()
    knowledge_repository = MongoKnowledgeRepository(
        settings.mongodb_uri,
        settings.mongodb_database,
    )
    embedding_gateway = LlamaCppEmbeddingGateway(
        base_url=settings.embedding_base_url,
        model_id=settings.embedding_model_id,
        dimensions=settings.embedding_dimensions,
        timeout_seconds=settings.embedding_request_timeout_seconds,
        usage_repository=JsonlEmbeddingUsageRepository(
            settings.project_assets_dir
        ),
        max_input_tokens=settings.embedding_max_input_tokens,
    )
    vector_index = QdrantVectorIndexBackend(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value(),
    )
    service = KnowledgeVectorIndexService(
        knowledge_repository=knowledge_repository,
        embedding_gateway=embedding_gateway,
        vector_index=vector_index,
        manifests=JsonVectorIndexManifestRepository(settings.project_assets_dir),
        active_alias=settings.qdrant_collection,
        document_batch_size=settings.vector_document_batch_size,
        embedding_input_char_budget=(
            settings.vector_embedding_input_char_budget
        ),
    )
    await knowledge_repository.initialize()
    try:
        if args.verify_only:
            result: Any = await service.verify()
            _print_json(result.model_dump(mode="json"))
            return 0 if result.valid else 2
        result = await service.rebuild(dry_run=args.dry_run)
        _print_json(result.model_dump(mode="json"))
        return 0
    finally:
        await embedding_gateway.close()
        await vector_index.close()
        await knowledge_repository.close()


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    args = _parser().parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
