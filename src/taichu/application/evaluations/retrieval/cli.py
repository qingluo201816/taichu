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
from taichu.infrastructure.retrieval import (
    JsonlRetrievalTraceRepository,
    MongoLexicalRetrievalBackend,
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
        help="请求的召回策略名称。",
    )
    args = parser.parse_args()
    asyncio.run(_run(dataset_id=args.dataset, strategy=args.strategy))


async def _run(*, dataset_id: str, strategy: str) -> None:
    settings = Settings()
    knowledge_repository = MongoKnowledgeRepository(
        settings.mongodb_uri,
        settings.mongodb_database,
    )
    try:
        await knowledge_repository.initialize()
        resolver = RetrievalPolicyResolver.from_json(
            settings.retrieval_policies_json,
            default_relevance_strategy=(
                settings.retrieval_default_relevance_strategy
            ),
        )
        retrieval = RetrievalService(
            MongoLexicalRetrievalBackend(knowledge_repository),
            JsonlRetrievalTraceRepository(settings.project_assets_dir),
            policy_resolver=resolver,
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
        record = await service.evaluate(
            dataset_id=dataset_id,
            strategy=strategy,
            environment={
                "python": platform.python_version(),
                "platform": platform.platform(),
                "executable": Path(sys.executable).name,
            },
        )
        summary = record.summary
        print(
            json.dumps(
                {
                    "结果": "召回评测完成",
                    "评测标识": record.evaluation_id,
                    "数据集": record.dataset_id,
                    "数据集校验和": record.dataset_checksum,
                    "知识快照": record.index_snapshot_id,
                    "已确认知识卡": record.confirmed_card_count,
                    "请求策略": record.requested_strategy,
                    "实际策略": record.effective_strategies,
                    "样例数": summary.case_count,
                    "Recall@10": _recall_at_k(summary, 10),
                    "MRR": summary.mrr,
                    "空结果准确率": summary.empty_result_accuracy,
                    "禁止卡命中率": summary.forbidden_hit_rate,
                    "平均耗时毫秒": summary.average_latency_ms,
                    "P95耗时毫秒": summary.p95_latency_ms,
                    "失败样例数": len(record.failures),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        await knowledge_repository.close()


def _recall_at_k(summary: RetrievalEvaluationSummary, k: int) -> float:
    return next(item.recall for item in summary.at_k if item.k == k)


if __name__ == "__main__":
    main()
