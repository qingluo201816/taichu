"""Golden 数据集加载入口。"""

from __future__ import annotations

from pathlib import Path

from taichu.application.evaluations.rag.models import (
    RAGGoldenCategory,
    RAGGoldenSuite,
)


def load_golden_suite(path: Path) -> RAGGoldenSuite:
    return RAGGoldenSuite.model_validate_json(path.read_text(encoding="utf-8"))


def validate_core_golden_suite(suite: RAGGoldenSuite) -> None:
    expected_counts = {
        RAGGoldenCategory.SINGLE_FACT: 6,
        RAGGoldenCategory.CROSS_SOURCE: 6,
        RAGGoldenCategory.GRAPH_MULTI_HOP: 14,
        RAGGoldenCategory.HARD_NEGATIVE: 4,
    }
    actual_counts = {
        category: sum(case.category is category for case in suite.cases)
        for category in expected_counts
    }
    if actual_counts != expected_counts:
        raise ValueError(
            f"核心 Golden 集分层数量错误：期望 {expected_counts}，实际 {actual_counts}。"
        )
    smoke_count = sum(case.smoke for case in suite.cases)
    if smoke_count != 5:
        raise ValueError(f"核心 Golden 集必须恰好包含 5 条 Smoke，实际 {smoke_count} 条。")
