"""把评测报告转换为可解释的 CI 门禁结果。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping

from taichu.application.evaluations.rag.models import (
    RAGEvaluationReport,
    RAGGateResult,
    RAGGoldenCase,
)


def evaluate_regression_gate(
    report: RAGEvaluationReport,
    semantic_scores: Iterable[Mapping[str, object]] = (),
    *,
    recall_threshold: float = 0.8,
    mrr_threshold: float = 0.5,
    relation_recall_threshold: float = 0.7,
    complete_path_threshold: float = 0.6,
    ablation_path_delta_threshold: float = 0.05,
    semantic_threshold: float = 0.7,
) -> RAGGateResult:
    summary = report.summary
    failures: list[str] = []
    checks = (
        (summary.mean_recall_at_k, recall_threshold, "Recall@10"),
        (summary.mean_mrr_at_k, mrr_threshold, "MRR@10"),
        (summary.authority_pass_rate, 1.0, "权威来源完整率"),
    )
    for actual, threshold, label in checks:
        if actual < threshold:
            failures.append(f"{label}={actual:.3f}，低于门槛 {threshold:.3f}。")

    for case_score in report.case_scores:
        if not case_score.authority_verified:
            failures.append(f"{case_score.case_id} 存在未通过权威回源的证据。")
        if case_score.recall_at_k == 0:
            failures.append(f"{case_score.case_id} 未召回任何预期来源。")
        if case_score.complete_path_recall == 0:
            failures.append(f"{case_score.case_id} 未召回完整 Graph 路径。")

    if summary.graph_case_count:
        graph_checks = (
            (
                summary.mean_relation_recall_at_k,
                relation_recall_threshold,
                "Relation Recall@10",
            ),
            (
                summary.complete_path_pass_rate,
                complete_path_threshold,
                "完整路径召回率",
            ),
        )
        for graph_actual, threshold, label in graph_checks:
            if graph_actual is None or graph_actual < threshold:
                shown = "无" if graph_actual is None else f"{graph_actual:.3f}"
                failures.append(f"{label}={shown}，低于门槛 {threshold:.3f}。")
        if report.ablation_scores:
            for ablation in report.ablation_scores:
                if ablation.complete_path_delta < 0:
                    failures.append(
                        f"{ablation.case_id} 开启 Graph 后完整路径召回反而下降。"
                    )
            delta = summary.mean_ablation_complete_path_delta
            if delta is None or delta < ablation_path_delta_threshold:
                shown = "无" if delta is None else f"{delta:.3f}"
                failures.append(
                    f"Graph ON/OFF 完整路径增益={shown}，低于门槛 "
                    f"{ablation_path_delta_threshold:.3f}。"
                )

    semantic_by_metric: dict[str, list[float]] = defaultdict(list)
    for case in semantic_scores:
        metrics = case.get("metrics", [])
        if not isinstance(metrics, list):
            continue
        for metric in metrics:
            if not isinstance(metric, Mapping):
                continue
            name = metric.get("metric")
            score = metric.get("score")
            if isinstance(name, str) and isinstance(score, (float, int)):
                semantic_by_metric[name].append(float(score))
    for metric, values in semantic_by_metric.items():
        mean_score = sum(values) / len(values)
        if mean_score < semantic_threshold:
            failures.append(
                f"{metric} 均分={mean_score:.3f}，低于门槛 {semantic_threshold:.3f}。"
            )
    return RAGGateResult(passed=not failures, failures=failures)


def select_pr_semantic_cases(
    suite_cases: Iterable[RAGGoldenCase],
) -> list[RAGGoldenCase]:
    """按固定分层选 2 单事实、2 跨来源、4 Graph、2 困难负例。"""

    quotas = {
        "single_fact": 2,
        "cross_source": 2,
        "graph_multi_hop": 4,
        "hard_negative": 2,
    }
    selected: list[RAGGoldenCase] = []
    counts: dict[str, int] = defaultdict(int)
    for case in suite_cases:
        category = str(case.category)
        if counts[category] < quotas.get(category, 0):
            selected.append(case)
            counts[category] += 1
    return selected
