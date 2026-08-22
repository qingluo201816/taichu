"""RAG 评测报告的原子 JSON 存储。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from taichu.application.evaluations.rag.models import (
    RAGEvaluationResultSummary,
    RAGInfrastructureFailureReport,
    RAGRunReport,
)


class RAGEvaluationResultRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, report: BaseModel, *, run_id: str) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        target = self._root / f"{run_id}.json"
        temporary = self._root / f".{run_id}.{uuid4().hex}.tmp"
        temporary.write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, target)
        return target

    def list_summaries(self, *, limit: int = 20) -> list[RAGEvaluationResultSummary]:
        if not self._root.exists():
            return []
        summaries: list[RAGEvaluationResultSummary] = []
        for path in sorted(self._root.glob("*.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    continue
                summaries.append(_result_summary(path.stem, payload))
            except (OSError, ValueError, TypeError):
                continue
            if len(summaries) >= limit:
                break
        return summaries

    def get(self, run_id: str) -> RAGRunReport | RAGInfrastructureFailureReport | None:
        if not run_id or any(character not in _SAFE_RUN_ID_CHARS for character in run_id):
            return None
        path = self._root / f"{run_id}.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("status") == "infrastructure_failed":
            return RAGInfrastructureFailureReport.model_validate(payload)
        return RAGRunReport.model_validate(payload)


_SAFE_RUN_ID_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
)


def _result_summary(
    run_id: str,
    payload: dict[str, object],
) -> RAGEvaluationResultSummary:
    if payload.get("status") == "infrastructure_failed":
        return RAGEvaluationResultSummary(
            run_id=run_id,
            mode=str(payload.get("mode", "unknown")),
            created_at=str(payload.get("created_at", "")),
            status="infrastructure_failed",
            error_message=str(payload.get("error_message", "")) or None,
        )
    deterministic = payload.get("deterministic")
    gate = payload.get("gate")
    if not isinstance(deterministic, dict) or not isinstance(gate, dict):
        raise ValueError("RAG 评测结果结构无效。")
    summary = deterministic.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("RAG 评测摘要结构无效。")
    passed = gate.get("passed")
    return RAGEvaluationResultSummary(
        run_id=run_id,
        mode=str(deterministic.get("mode", "unknown")),
        created_at=str(deterministic.get("created_at", "")),
        status="completed",
        passed=passed if isinstance(passed, bool) else None,
        case_count=_optional_int(summary.get("case_count")),
        graph_case_count=_optional_int(summary.get("graph_case_count")),
    )


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
