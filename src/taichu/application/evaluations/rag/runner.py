"""基于唯一生产 RAG 链路执行确定性回归。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from taichu.application.evaluations.rag.metrics import evaluate_case_retrieval
from taichu.application.evaluations.rag.models import (
    RAGCaseExecutionFailure,
    RAGCaseScore,
    RAGEvaluationReport,
    RAGEvaluationSummary,
    RAGGoldenSuite,
)
from taichu.application.vector_graph.models import VectorGraphRetrievalResult


class RAGRetrievalService(Protocol):
    async def retrieve(
        self,
        query: str,
        *,
        top_k: int,
    ) -> VectorGraphRetrievalResult: ...


async def run_deterministic_evaluation(
    suite: RAGGoldenSuite,
    service: RAGRetrievalService,
    *,
    top_k: int = 10,
    smoke_only: bool = False,
    continue_on_error: bool = False,
) -> RAGEvaluationReport:
    selected = [case for case in suite.cases if case.smoke] if smoke_only else suite.cases
    scores: list[RAGCaseScore] = []
    execution_failures: list[RAGCaseExecutionFailure] = []
    for case in selected:
        try:
            retrieval = await service.retrieve(case.query, top_k=top_k)
        except Exception as error:
            failure = _execution_failure(case.case_id, "生产检索", error)
            if not continue_on_error:
                raise RAGEvaluationExecutionError(
                    case.case_id,
                    failure.phase,
                    error,
                ) from error
            execution_failures.append(failure)
            continue
        scores.append(evaluate_case_retrieval(case, retrieval, top_k=top_k))

    return RAGEvaluationReport(
        suite_id=suite.suite_id,
        mode="smoke" if smoke_only else "deterministic",
        created_at=datetime.now(UTC).isoformat(),
        top_k=top_k,
        case_scores=scores,
        execution_failures=execution_failures,
        summary=_summarize(scores),
    )


def _execution_failure(
    case_id: str, phase: str, error: Exception
) -> RAGCaseExecutionFailure:
    detail = str(error).strip() or type(error).__name__
    return RAGCaseExecutionFailure(
        case_id=case_id,
        phase=phase,
        error_type=type(error).__name__,
        error_message=detail[:2_000],
    )


class RAGEvaluationExecutionError(RuntimeError):
    def __init__(self, case_id: str, phase: str, cause: Exception) -> None:
        detail = str(cause).strip() or type(cause).__name__
        super().__init__(f"用例 {case_id} 在{phase}阶段失败：{detail}")
        self.case_id = case_id
        self.phase = phase


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _summarize(scores: list[RAGCaseScore]) -> RAGEvaluationSummary:
    graph_scores = [item for item in scores if item.relation_recall_at_k is not None]
    return RAGEvaluationSummary(
        case_count=len(scores),
        graph_case_count=len(graph_scores),
        mean_recall_at_k=_mean(
            [item.recall_at_k for item in scores if item.recall_at_k is not None]
        ),
        mean_mrr_at_k=_mean(
            [item.mrr_at_k for item in scores if item.mrr_at_k is not None]
        ),
        authority_pass_rate=_mean([float(item.authority_verified) for item in scores]),
        mean_relation_recall_at_k=(
            _mean([item.relation_recall_at_k or 0.0 for item in graph_scores])
            if graph_scores
            else None
        ),
        complete_path_pass_rate=(
            _mean([item.complete_path_recall or 0.0 for item in graph_scores])
            if graph_scores
            else None
        ),
    )
