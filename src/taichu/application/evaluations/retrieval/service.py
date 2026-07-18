"""确定性执行召回数据集并计算离线排名指标。"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
import json
import math
from secrets import token_hex
from statistics import fmean

from taichu.application.contracts.retrieval_evaluation import (
    RetrievalEvaluationDatasetRepository,
    RetrievalEvaluationResultRepository,
)
from taichu.application.evaluations.retrieval.models import (
    RetrievalAtKMetric,
    RetrievalEvaluationCase,
    RetrievalEvaluationCaseResult,
    RetrievalEvaluationCategory,
    RetrievalEvaluationDataset,
    RetrievalEvaluationFailure,
    RetrievalEvaluationGroupResult,
    RetrievalEvaluationRecord,
    RetrievalEvaluationSummary,
)
from taichu.application.retrieval.models import (
    RetrievalConsumerContext,
    RetrievalMode,
    RetrievalRequest,
    RetrievalResult,
)
from taichu.application.services.retrieval_service import RetrievalService

_K_VALUES = (1, 3, 5, 10)


class RetrievalEvaluationService:
    """独立于业务 Agent 评测，直接评估统一召回契约。"""

    def __init__(
        self,
        *,
        datasets: RetrievalEvaluationDatasetRepository,
        results: RetrievalEvaluationResultRepository,
        retrieval: RetrievalService,
    ) -> None:
        self._datasets = datasets
        self._results = results
        self._retrieval = retrieval

    async def evaluate(
        self,
        *,
        dataset_id: str,
        strategy: str,
        environment: dict[str, str] | None = None,
    ) -> RetrievalEvaluationRecord:
        dataset = await self.get_dataset(dataset_id)

        started_at = _now_iso()
        snapshot = await self._retrieval.retrieve(
            RetrievalRequest(
                mode=RetrievalMode.CATALOG,
                top_k=200,
                max_content_chars=50_000,
                consumer=RetrievalConsumerContext(
                    consumer_type="retrieval_evaluation",
                    run_id=dataset.dataset_id,
                    stage="confirmed_snapshot",
                ),
            )
        )
        snapshot_id = snapshot.index_snapshot_id or _fallback_snapshot_id(snapshot)

        case_results: list[RetrievalEvaluationCaseResult] = []
        effective_strategies: set[str] = set()
        policy_snapshots: dict[str, dict[str, str | int | bool | None]] = {}
        for case in dataset.cases:
            retrieval_result = await self._retrieval.retrieve(
                RetrievalRequest(
                    query_text=case.query_text,
                    context_text=case.context_text,
                    knowledge_types=case.knowledge_types,
                    top_k=case.expected_top_k,
                    max_content_chars=50_000,
                    requested_strategy=strategy,
                    consumer=RetrievalConsumerContext(
                        consumer_type="retrieval_evaluation",
                        run_id=dataset.dataset_id,
                        stage=case.case_id,
                    ),
                )
            )
            effective_strategies.add(
                retrieval_result.effective_strategy or retrieval_result.strategy
            )
            snapshot_key = json.dumps(
                retrieval_result.strategy_snapshot,
                ensure_ascii=False,
                sort_keys=True,
            )
            policy_snapshots[snapshot_key] = retrieval_result.strategy_snapshot
            case_results.append(_evaluate_case(case, retrieval_result))

        failures = _failures(dataset, case_results)
        groups_by_category: dict[
            RetrievalEvaluationCategory,
            list[RetrievalEvaluationCaseResult],
        ] = defaultdict(list)
        for case_result in case_results:
            groups_by_category[case_result.category].append(case_result)
        groups = [
            RetrievalEvaluationGroupResult(
                category=category,
                summary=_summary(results),
            )
            for category, results in sorted(
                groups_by_category.items(),
                key=lambda item: item[0].value,
            )
        ]
        record = RetrievalEvaluationRecord(
            evaluation_id=_new_evaluation_id(),
            dataset_id=dataset.dataset_id,
            dataset_checksum=dataset.checksum,
            requested_strategy=strategy,
            effective_strategies=sorted(effective_strategies),
            index_snapshot_id=snapshot_id,
            confirmed_card_count=snapshot.candidate_count,
            policy_snapshots=[policy_snapshots[key] for key in sorted(policy_snapshots)],
            summary=_summary(case_results),
            groups=groups,
            cases=case_results,
            failures=failures,
            environment=environment or {},
            started_at=started_at,
            finished_at=_now_iso(),
        )
        return await self._results.save(record)

    async def get_dataset(self, dataset_id: str) -> RetrievalEvaluationDataset:
        """读取前端展示所需的确认态召回评测集。"""
        dataset = await self._datasets.get_dataset(dataset_id)
        if dataset is None:
            raise RetrievalEvaluationError(
                "未找到指定的召回评测集。",
                code="RETRIEVAL_EVALUATION_DATASET_NOT_FOUND",
            )
        return dataset

    async def list_evaluations(
        self,
        *,
        limit: int = 20,
    ) -> list[RetrievalEvaluationRecord]:
        """按时间倒序读取可重建的评测结果。"""
        return await self._results.list_records(limit=limit)

    async def get_evaluation(
        self,
        evaluation_id: str,
    ) -> RetrievalEvaluationRecord:
        """读取一条不含查询正文和知识卡正文的评测结果。"""
        record = await self._results.get(evaluation_id)
        if record is None:
            raise RetrievalEvaluationError(
                "未找到指定的召回评测结果。",
                code="RETRIEVAL_EVALUATION_NOT_FOUND",
            )
        return record


def _evaluate_case(
    case: RetrievalEvaluationCase,
    retrieval: RetrievalResult,
) -> RetrievalEvaluationCaseResult:
    returned_ids = [item.source_id for item in retrieval.items]
    relevant = set(case.relevant_card_ids)
    forbidden_hits = [
        card_id for card_id in returned_ids if card_id in case.must_not_return_card_ids
    ]
    at_k = [_at_k(returned_ids, relevant, k) for k in _K_VALUES]
    reciprocal_rank = 0.0
    for rank, card_id in enumerate(returned_ids, start=1):
        if card_id in relevant:
            reciprocal_rank = 1 / rank
            break
    return RetrievalEvaluationCaseResult(
        case_id=case.case_id,
        category=case.category,
        retrieval_id=retrieval.retrieval_id,
        returned_card_ids=returned_ids,
        forbidden_hit_ids=forbidden_hits,
        at_k=at_k,
        reciprocal_rank=round(reciprocal_rank, 6),
        empty_result_correct=(
            not returned_ids if case.should_be_empty else None
        ),
        latency_ms=retrieval.duration_ms,
        candidate_count=retrieval.candidate_count,
        hit_count=retrieval.hit_count,
        truncated=retrieval.truncated,
        budget_limited=retrieval.budget_limited,
        content_chars_used=retrieval.content_chars_used,
    )


def _at_k(
    returned_ids: list[str],
    relevant: set[str],
    k: int,
) -> RetrievalAtKMetric:
    selected = returned_ids[:k]
    hit_count = sum(card_id in relevant for card_id in selected)
    recall = hit_count / len(relevant) if relevant else 0.0
    precision = hit_count / k
    dcg = sum(
        1 / math.log2(rank + 1)
        for rank, card_id in enumerate(selected, start=1)
        if card_id in relevant
    )
    ideal_hits = min(len(relevant), k)
    ideal_dcg = sum(1 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    ndcg = dcg / ideal_dcg if ideal_dcg else 0.0
    return RetrievalAtKMetric(
        k=k,  # type: ignore[arg-type]
        recall=round(recall, 6),
        precision=round(precision, 6),
        ndcg=round(ndcg, 6),
    )


def _summary(
    case_results: list[RetrievalEvaluationCaseResult],
) -> RetrievalEvaluationSummary:
    relevance_results = [
        result
        for result in case_results
        if result.category is not RetrievalEvaluationCategory.NO_ANSWER_ADVERSARIAL
    ]
    empty_results = [
        result for result in case_results if result.empty_result_correct is not None
    ]
    at_k = [
        RetrievalAtKMetric(
            k=k,  # type: ignore[arg-type]
            recall=round(fmean(_metric(result, k).recall for result in relevance_results), 6)
            if relevance_results
            else 0,
            precision=round(
                fmean(_metric(result, k).precision for result in relevance_results),
                6,
            )
            if relevance_results
            else 0,
            ndcg=round(fmean(_metric(result, k).ndcg for result in relevance_results), 6)
            if relevance_results
            else 0,
        )
        for k in _K_VALUES
    ]
    latencies = sorted(result.latency_ms for result in case_results)
    p95_index = max(0, math.ceil(len(latencies) * 0.95) - 1)
    case_count = len(case_results)
    return RetrievalEvaluationSummary(
        case_count=case_count,
        relevance_case_count=len(relevance_results),
        at_k=at_k,
        mrr=round(fmean(result.reciprocal_rank for result in relevance_results), 6)
        if relevance_results
        else 0,
        empty_result_accuracy=round(
            sum(result.empty_result_correct is True for result in empty_results)
            / len(empty_results),
            6,
        )
        if empty_results
        else 1,
        forbidden_hit_rate=round(
            sum(bool(result.forbidden_hit_ids) for result in case_results)
            / case_count,
            6,
        ),
        average_latency_ms=round(fmean(latencies), 3),
        p95_latency_ms=float(latencies[p95_index]),
        average_candidate_count=round(
            fmean(result.candidate_count for result in case_results),
            3,
        ),
        truncation_rate=round(
            sum(result.truncated for result in case_results) / case_count,
            6,
        ),
        content_budget_hit_rate=round(
            sum(result.budget_limited for result in case_results) / case_count,
            6,
        ),
    )


def _metric(result: RetrievalEvaluationCaseResult, k: int) -> RetrievalAtKMetric:
    return next(item for item in result.at_k if item.k == k)


def _failures(
    dataset: RetrievalEvaluationDataset,
    results: list[RetrievalEvaluationCaseResult],
) -> list[RetrievalEvaluationFailure]:
    cases = {case.case_id: case for case in dataset.cases}
    failures: list[RetrievalEvaluationFailure] = []
    for result in results:
        case = cases[result.case_id]
        reasons: list[str] = []
        if case.should_be_empty:
            if result.empty_result_correct is not True:
                reasons.append("期望空结果，但召回返回了知识卡。")
        elif _metric(result, case.expected_top_k).recall < 1:
            reasons.append("期望相关知识卡未在指定 top-k 内全部召回。")
        if result.forbidden_hit_ids:
            reasons.append("召回结果命中了样例明确禁止的知识卡。")
        if reasons:
            failures.append(
                RetrievalEvaluationFailure(
                    case_id=result.case_id,
                    reasons=reasons,
                    returned_card_ids=result.returned_card_ids,
                )
            )
    return failures


def _fallback_snapshot_id(result: RetrievalResult) -> str:
    from hashlib import sha256

    payload = "\n".join(
        f"{item.source_id}:{item.knowledge_card.updated_at}"
        for item in result.items
    )
    return "confirmed_catalog_" + sha256(payload.encode("utf-8")).hexdigest()


def _new_evaluation_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"retrieval_eval_{stamp}_{token_hex(3)}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class RetrievalEvaluationError(RuntimeError):
    """召回评测输入、数据集或结果不可用。"""

    def __init__(
        self,
        message: str,
        *,
        code: str = "RETRIEVAL_EVALUATION_INVALID",
    ) -> None:
        super().__init__(message)
        self.code = code
