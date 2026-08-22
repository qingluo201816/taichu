"""Graph RAG 评测结果摘要仓储测试。"""

from __future__ import annotations

import json

from taichu.infrastructure.evaluations.rag.result_repository import (
    RAGEvaluationResultRepository,
)


def test_lists_completed_and_infrastructure_failure_summaries(tmp_path) -> None:
    repository = RAGEvaluationResultRepository(tmp_path)
    (tmp_path / "20260821-120000-completed.json").write_text(
        json.dumps(
            {
                "deterministic": {
                    "mode": "full",
                    "created_at": "2026-08-21T12:00:00Z",
                    "summary": {"case_count": 30, "graph_case_count": 14},
                },
                "gate": {"passed": True},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "20260821-130000-failed.json").write_text(
        json.dumps(
            {
                "status": "infrastructure_failed",
                "mode": "smoke",
                "created_at": "2026-08-21T13:00:00Z",
                "error_message": "向量服务不可用",
            }
        ),
        encoding="utf-8",
    )

    summaries = repository.list_summaries()

    assert [summary.run_id for summary in summaries] == [
        "20260821-130000-failed",
        "20260821-120000-completed",
    ]
    assert summaries[0].status == "infrastructure_failed"
    assert summaries[0].error_message == "向量服务不可用"
    assert summaries[1].passed is True
    assert summaries[1].case_count == 30
    assert summaries[1].graph_case_count == 14


def test_skips_corrupted_results_and_honors_limit(tmp_path) -> None:
    repository = RAGEvaluationResultRepository(tmp_path)
    (tmp_path / "20260821-140000-corrupted.json").write_text(
        "不是 JSON",
        encoding="utf-8",
    )
    for index in range(2):
        (tmp_path / f"20260821-13{index}000-valid.json").write_text(
            json.dumps(
                {
                    "status": "infrastructure_failed",
                    "mode": "smoke",
                    "created_at": f"2026-08-21T13:0{index}:00Z",
                    "error_message": "测试失败",
                }
            ),
            encoding="utf-8",
        )

    summaries = repository.list_summaries(limit=1)

    assert len(summaries) == 1
    assert summaries[0].run_id == "20260821-131000-valid"


def test_loads_full_result_and_rejects_unsafe_run_id(tmp_path) -> None:
    repository = RAGEvaluationResultRepository(tmp_path)
    report = {
        "deterministic": {
            "suite_id": "suite",
            "mode": "smoke",
            "created_at": "2026-08-21T12:00:00Z",
            "top_k": 10,
            "case_scores": [],
            "ablation_scores": [],
            "summary": {
                "case_count": 0,
                "graph_case_count": 0,
                "mean_recall_at_k": 0,
                "mean_mrr_at_k": 0,
                "authority_pass_rate": 0,
            },
        },
        "semantic_scores": [],
        "runtime_identity": {},
        "gate": {"passed": True, "failures": []},
    }
    (tmp_path / "safe-run.json").write_text(json.dumps(report), encoding="utf-8")

    loaded = repository.get("safe-run")

    assert loaded is not None
    assert loaded.deterministic.top_k == 10  # type: ignore[union-attr]
    assert repository.get("../safe-run") is None
