"""运行独立知识召回评测的命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
from pathlib import Path
import sys

from taichu.application.evaluations.retrieval.service import (
    RetrievalEvaluationService,
)
from taichu.application.evaluations.retrieval.models import (
    RetrievalEvaluationSummary,
)
from taichu.application.retrieval.policy import RetrievalPolicyResolver
from taichu.application.services.retrieval_service import RetrievalService
from taichu.config import Settings
from taichu.infrastructure.evaluations.retrieval import (
    JsonRetrievalEvaluationDatasetRepository,
    JsonRetrievalEvaluationResultRepository,
)
from taichu.infrastructure.knowledge import MongoKnowledgeRepository
from taichu.infrastructure.embedding import (
    JsonlEmbeddingUsageRepository,
    LlamaCppEmbeddingGateway,
)
from taichu.infrastructure.retrieval import (
    JsonlRetrievalTraceRepository,
    KnowledgeVectorRetrievalBackend,
    MongoLexicalRetrievalBackend,
)
from taichu.infrastructure.retrieval.vector_index import (
    JsonVectorIndexManifestRepository,
    QdrantVectorIndexBackend,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="运行统一知识召回离线评测。")
    parser.add_argument(
        "--dataset",
        default="retrieval_knowledge_core",
        help="召回评测集标识。",
    )
    parser.add_argument(
        "--strategy",
        default="mongo_lexical",
        choices=("mongo_lexical", "knowledge_vector", "both"),
        help="请求词法、独立向量或两种策略。",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        choices=range(1, 11),
        metavar="1-10",
        help="每种策略重复执行次数，用于检查排名稳定性。",
    )
    args = parser.parse_args()
    asyncio.run(
        _run(
            dataset_id=args.dataset,
            strategy=args.strategy,
            repeat=args.repeat,
        )
    )


async def _run(*, dataset_id: str, strategy: str, repeat: int) -> None:
    settings = Settings()
    knowledge_repository = MongoKnowledgeRepository(
        settings.mongodb_uri,
        settings.mongodb_database,
    )
    embedding_gateway: LlamaCppEmbeddingGateway | None = None
    vector_index_backend: QdrantVectorIndexBackend | None = None
    try:
        await knowledge_repository.initialize()
        resolver = RetrievalPolicyResolver.from_json(
            settings.retrieval_policies_json,
            default_relevance_strategy=(
                settings.retrieval_default_relevance_strategy
            ),
        )
        additional_backends = {}
        manifests = JsonVectorIndexManifestRepository(settings.project_assets_dir)
        if strategy in {"knowledge_vector", "both"}:
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
            vector_index_backend = QdrantVectorIndexBackend(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key.get_secret_value(),
            )
            vector_backend = KnowledgeVectorRetrievalBackend(
                knowledge_repository=knowledge_repository,
                embedding_gateway=embedding_gateway,
                vector_index=vector_index_backend,
                manifests=manifests,
                query_char_budget=settings.vector_query_char_budget,
                candidate_multiplier=settings.vector_candidate_multiplier,
                score_threshold=settings.vector_score_threshold,
                coverage_bonus=settings.vector_coverage_bonus,
            )
            additional_backends[vector_backend.strategy_name] = vector_backend
        retrieval = RetrievalService(
            MongoLexicalRetrievalBackend(knowledge_repository),
            JsonlRetrievalTraceRepository(settings.project_assets_dir),
            policy_resolver=resolver,
            additional_backends=additional_backends,
        )
        service = RetrievalEvaluationService(
            datasets=JsonRetrievalEvaluationDatasetRepository(
                settings.evaluation_datasets_dir
            ),
            results=JsonRetrievalEvaluationResultRepository(
                settings.project_assets_dir
            ),
            retrieval=retrieval,
        )
        environment = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "executable": Path(sys.executable).name,
        }
        manifest = await manifests.load_active()
        if manifest is not None:
            environment.update(
                {
                    "vector_index_id": manifest.index_id,
                    "vector_build_duration_ms": str(manifest.build_duration_ms),
                    "vector_estimated_bytes": str(manifest.estimated_vector_bytes),
                    "embedding_model_id": manifest.embedding_model_id,
                    "embedding_dimensions": str(manifest.vector_dimensions),
                }
            )
        strategies = (
            ["mongo_lexical", "knowledge_vector"]
            if strategy == "both"
            else [strategy]
        )
        outputs = []
        for selected_strategy in strategies:
            for repetition in range(1, repeat + 1):
                record = await service.evaluate(
                    dataset_id=dataset_id,
                    strategy=selected_strategy,
                    environment={
                        **environment,
                        "repetition": str(repetition),
                    },
                )
                outputs.append(_output(record, repetition=repetition))
        print(json.dumps(outputs, ensure_ascii=False, indent=2))
    finally:
        if embedding_gateway is not None:
            await embedding_gateway.close()
        if vector_index_backend is not None:
            await vector_index_backend.close()
        await knowledge_repository.close()


def _recall_at_k(summary: RetrievalEvaluationSummary, k: int) -> float:
    return next(item.recall for item in summary.at_k if item.k == k)


def _ndcg_at_k(summary: RetrievalEvaluationSummary, k: int) -> float:
    return next(item.ndcg for item in summary.at_k if item.k == k)


def _output(record: object, *, repetition: int) -> dict[str, object]:
    from taichu.application.evaluations.retrieval.models import (
        RetrievalEvaluationRecord,
    )

    assert isinstance(record, RetrievalEvaluationRecord)
    summary = record.summary
    return {
        "结果": "召回评测完成",
        "重复序号": repetition,
        "评测标识": record.evaluation_id,
        "数据集": record.dataset_id,
        "数据集校验和": record.dataset_checksum,
        "索引快照": record.index_snapshot_id,
        "已确认知识卡": record.confirmed_card_count,
        "请求策略": record.requested_strategy,
        "实际策略": record.effective_strategies,
        "样例数": summary.case_count,
        "Recall@5": _recall_at_k(summary, 5),
        "Recall@10": _recall_at_k(summary, 10),
        "nDCG@5": _ndcg_at_k(summary, 5),
        "MRR": summary.mrr,
        "空结果准确率": summary.empty_result_accuracy,
        "禁止卡命中率": summary.forbidden_hit_rate,
        "平均耗时毫秒": summary.average_latency_ms,
        "P95耗时毫秒": summary.p95_latency_ms,
        "Embedding调用数": summary.embedding_call_count,
        "Embedding失败率": summary.embedding_failure_rate,
        "Embedding_P50毫秒": summary.embedding_p50_latency_ms,
        "Embedding_P95毫秒": summary.embedding_p95_latency_ms,
        "索引检索_P50毫秒": summary.index_search_p50_latency_ms,
        "索引检索_P95毫秒": summary.index_search_p95_latency_ms,
        "Embedding费用": summary.embedding_cost_amount,
        "排名指纹": record.ranking_fingerprint_sha256,
        "失败样例数": len(record.failures),
    }


if __name__ == "__main__":
    main()
