"""确定性 RAG 回归与 Graph ON/OFF 成对消融。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from taichu.application.evaluations.rag.metrics import evaluate_case_retrieval
from taichu.application.evaluations.rag.models import (
    RAGAblationScore,
    RAGCaseScore,
    RAGEvaluationReport,
    RAGEvaluationSummary,
    RAGGoldenCase,
    RAGGoldenSuite,
)
from taichu.application.vector_graph.models import VectorGraphRetrievalResult


class RAGRetrievalService(Protocol):
    async def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        graph_enabled: bool,
    ) -> VectorGraphRetrievalResult: ...


async def run_deterministic_evaluation(
    suite: RAGGoldenSuite,
    service: RAGRetrievalService,
    *,
    top_k: int = 10,
    smoke_only: bool = False,
    include_ablation: bool = True,
) -> RAGEvaluationReport:
    selected = [case for case in suite.cases if case.smoke] if smoke_only else suite.cases
    scores: list[RAGCaseScore] = []
    ablations: list[RAGAblationScore] = []
    for case in selected:
        try:
            graph_on = await service.retrieve(
                case.query,
                top_k=top_k,
                graph_enabled=True,
            )
        except Exception as error:
            raise RAGEvaluationExecutionError(
                case.case_id,
                "Graph ON 生产检索",
                error,
            ) from error
        on_score = evaluate_case_retrieval(case, graph_on, top_k=top_k)
        scores.append(on_score)
        if include_ablation and case.graph_required:
            try:
                graph_off = await service.retrieve(
                    case.query,
                    top_k=top_k,
                    graph_enabled=False,
                )
            except Exception as error:
                raise RAGEvaluationExecutionError(
                    case.case_id,
                    "Graph OFF 生产检索",
                    error,
                ) from error
            off_score = evaluate_case_retrieval(case, graph_off, top_k=top_k)
            ablations.append(_ablation(case, on_score, off_score))

    return RAGEvaluationReport(
        suite_id=suite.suite_id,
        mode="smoke" if smoke_only else "deterministic",
        created_at=datetime.now(UTC).isoformat(),
        top_k=top_k,
        case_scores=scores,
        ablation_scores=ablations,
        summary=_summarize(scores, ablations),
    )


class RAGEvaluationExecutionError(RuntimeError):
    def __init__(self, case_id: str, phase: str, cause: Exception) -> None:
        detail = str(cause).strip() or type(cause).__name__
        super().__init__(f"用例 {case_id} 在{phase}阶段失败：{detail}")
        self.case_id = case_id
        self.phase = phase


def _ablation(
    case: RAGGoldenCase,
    graph_on: RAGCaseScore,
    graph_off: RAGCaseScore,
) -> RAGAblationScore:
    return RAGAblationScore(
        case_id=case.case_id,
        graph_on=graph_on,
        graph_off=graph_off,
        recall_delta=(
            graph_on.recall_at_k - graph_off.recall_at_k
            if graph_on.recall_at_k is not None
            and graph_off.recall_at_k is not None
            else None
        ),
        mrr_delta=(
            graph_on.mrr_at_k - graph_off.mrr_at_k
            if graph_on.mrr_at_k is not None and graph_off.mrr_at_k is not None
            else None
        ),
        relation_recall_delta=(graph_on.relation_recall_at_k or 0.0)
        - (graph_off.relation_recall_at_k or 0.0),
        complete_path_delta=(graph_on.complete_path_recall or 0.0)
        - (graph_off.complete_path_recall or 0.0),
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _summarize(
    scores: list[RAGCaseScore],
    ablations: list[RAGAblationScore],
) -> RAGEvaluationSummary:
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
        mean_ablation_recall_delta=(
            _mean(
                [item.recall_delta for item in ablations if item.recall_delta is not None]
            )
            if ablations
            else None
        ),
        mean_ablation_complete_path_delta=(
            _mean([item.complete_path_delta for item in ablations])
            if ablations
            else None
        ),
    )
