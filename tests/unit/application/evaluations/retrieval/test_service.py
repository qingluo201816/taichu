"""独立召回评测指标、脱敏结果和结果仓储测试。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from taichu.application.evaluations.retrieval.models import (
    RetrievalEvaluationCase,
    RetrievalEvaluationCategory,
    RetrievalEvaluationDataset,
    RetrievalEvaluationRecord,
    RetrievalAtKMetric,
)
from taichu.application.evaluations.retrieval.service import (
    RetrievalEvaluationService,
)
from taichu.application.retrieval.models import (
    RetrievalBackendCandidate,
    RetrievalBackendResult,
    RetrievalMode,
    RetrievalRequest,
    RetrievalTraceRecord,
)
from taichu.application.services.retrieval_service import RetrievalService
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeType,
)
from taichu.infrastructure.evaluations.retrieval import (
    JsonRetrievalEvaluationDatasetRepository,
    JsonRetrievalEvaluationResultRepository,
)


def _async_test(
    test: Callable[..., Coroutine[Any, Any, None]],
) -> Callable[..., None]:
    @wraps(test)
    def run(*args: Any, **kwargs: Any) -> None:
        asyncio.run(test(*args, **kwargs))

    return run


def test_production_fixture_has_stable_checksum_and_required_distribution() -> None:
    repository = JsonRetrievalEvaluationDatasetRepository(
        Path("tests/fixtures/evaluations")
    )

    dataset = asyncio.run(repository.get_dataset("retrieval_knowledge_core"))

    assert dataset is not None
    assert len(dataset.cases) == 60
    assert len(dataset.checksum) == 64
    counts = {
        category: sum(case.category is category for case in dataset.cases)
        for category in RetrievalEvaluationCategory
    }
    assert counts == {
        RetrievalEvaluationCategory.EXACT_NAME_ALIAS: 15,
        RetrievalEvaluationCategory.SEMANTIC_PARAPHRASE: 20,
        RetrievalEvaluationCategory.STATE_RELATION_EVENT_RULE: 15,
        RetrievalEvaluationCategory.MULTI_ENTITY_DISAMBIGUATION: 5,
        RetrievalEvaluationCategory.NO_ANSWER_ADVERSARIAL: 5,
    }


def test_case_rejects_top_k_without_a_defined_metric() -> None:
    with pytest.raises(ValidationError):
        RetrievalEvaluationCase.model_validate(
            {
                "case_id": "invalid_top_k",
                "label": "非法 top-k",
                "category": RetrievalEvaluationCategory.EXACT_NAME_ALIAS,
                "query_text": "秦浩轩",
                "relevant_card_ids": ["card-a"],
                "expected_top_k": 2,
            }
        )


@_async_test
async def test_evaluation_calculates_metrics_and_saves_query_free_record(
    tmp_path: Path,
) -> None:
    dataset = _dataset()
    results = JsonRetrievalEvaluationResultRepository(tmp_path)
    traces = _TraceRepository()
    retrieval = RetrievalService(_EvaluationBackend(), traces)
    service = RetrievalEvaluationService(
        datasets=_DatasetRepository(dataset),
        results=results,
        retrieval=retrieval,
    )

    record = await service.evaluate(
        dataset_id=dataset.dataset_id,
        strategy="mongo_lexical",
        environment={"python": "test"},
    )

    assert record.summary.case_count == 60
    assert record.summary.relevance_case_count == 55
    assert _metric(record, 10).recall == 1
    assert record.summary.mrr == 1
    assert record.summary.empty_result_accuracy == 1
    assert record.summary.forbidden_hit_rate == 0
    assert record.failures == []
    assert len(record.groups) == 5
    assert record.confirmed_card_count == 2
    assert record.index_snapshot_id == "test_confirmed_snapshot"
    stored = await results.get(record.evaluation_id)
    assert stored == record
    raw = (
        tmp_path
        / "derived"
        / "agent_evaluations"
        / "retrieval"
        / f"{record.evaluation_id}.json"
    ).read_text(encoding="utf-8")
    assert "exact_query_00" not in raw
    assert len(traces.records) == 61
    assert all("query_text" not in trace.model_dump() for trace in traces.records)


def _dataset() -> RetrievalEvaluationDataset:
    cases: list[RetrievalEvaluationCase] = []
    cases.extend(
        _cases(
            "exact",
            RetrievalEvaluationCategory.EXACT_NAME_ALIAS,
            15,
            ["card-a"],
        )
    )
    cases.extend(
        _cases(
            "semantic",
            RetrievalEvaluationCategory.SEMANTIC_PARAPHRASE,
            20,
            ["card-a"],
        )
    )
    cases.extend(
        _cases(
            "state",
            RetrievalEvaluationCategory.STATE_RELATION_EVENT_RULE,
            15,
            ["card-b"],
        )
    )
    cases.extend(
        _cases(
            "multi",
            RetrievalEvaluationCategory.MULTI_ENTITY_DISAMBIGUATION,
            5,
            ["card-a", "card-b"],
        )
    )
    cases.extend(
        [
            RetrievalEvaluationCase(
                case_id=f"empty_{index:02d}",
                label=f"空结果 {index}",
                category=RetrievalEvaluationCategory.NO_ANSWER_ADVERSARIAL,
                query_text=f"empty_query_{index:02d}",
                should_be_empty=True,
            )
            for index in range(5)
        ]
    )
    return RetrievalEvaluationDataset(
        dataset_id="retrieval_test_core",
        label="测试召回集",
        updated_at="2026-07-18T00:00:00Z",
        cases=cases,
        checksum="a" * 64,
    )


def _cases(
    prefix: str,
    category: RetrievalEvaluationCategory,
    count: int,
    relevant_ids: list[str],
) -> list[RetrievalEvaluationCase]:
    return [
        RetrievalEvaluationCase(
            case_id=f"{prefix}_{index:02d}",
            label=f"{prefix} {index}",
            category=category,
            query_text=f"{prefix}_query_{index:02d}",
            relevant_card_ids=relevant_ids,
        )
        for index in range(count)
    ]


def _metric(record: RetrievalEvaluationRecord, k: int) -> RetrievalAtKMetric:
    return next(item for item in record.summary.at_k if item.k == k)


class _DatasetRepository:
    def __init__(self, dataset: RetrievalEvaluationDataset) -> None:
        self._dataset = dataset

    async def get_dataset(
        self,
        dataset_id: str,
    ) -> RetrievalEvaluationDataset | None:
        return self._dataset if dataset_id == self._dataset.dataset_id else None


class _TraceRepository:
    def __init__(self) -> None:
        self.records: list[RetrievalTraceRecord] = []

    async def append(self, record: RetrievalTraceRecord) -> None:
        self.records.append(record)


class _EvaluationBackend:
    strategy_name = "mongo_lexical"

    def __init__(self) -> None:
        self._cards = {
            "card-a": _card("card-a", "甲知识"),
            "card-b": _card("card-b", "乙知识"),
        }

    async def retrieve(self, request: RetrievalRequest) -> RetrievalBackendResult:
        if request.mode is RetrievalMode.CATALOG:
            selected = [self._cards["card-a"], self._cards["card-b"]]
        elif request.query_text.startswith("empty"):
            selected = []
        elif request.query_text.startswith("multi"):
            selected = [self._cards["card-a"], self._cards["card-b"]]
        elif request.query_text.startswith("state"):
            selected = [self._cards["card-b"]]
        else:
            selected = [self._cards["card-a"]]
        return RetrievalBackendResult(
            strategy="mongo_lexical",
            candidate_count=len(self._cards),
            candidates=[
                RetrievalBackendCandidate(
                    card=card,
                    score=100 - index,
                    estimated_content_chars=10,
                )
                for index, card in enumerate(selected)
            ],
            index_snapshot_id="test_confirmed_snapshot",
        )


def _card(card_id: str, name: str) -> StructuredKnowledgeCard:
    return StructuredKnowledgeCard(
        id=card_id,
        type=StructuredKnowledgeType.CHARACTER,
        name=name,
        aliases=[],
        summary=f"{name}的已确认事实。",
        lifecycle=StructuredKnowledgeLifecycle.CONFIRMED,
        source_origin=StructuredKnowledgeSourceOrigin.MANUAL,
        source_note="测试确认。",
        created_at="2026-07-18T00:00:00Z",
        updated_at="2026-07-18T00:00:00Z",
    )
