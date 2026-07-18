"""统一召回专项评测的只读 HTTP 契约。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from taichu.application.evaluations.retrieval.models import (
    RetrievalEvaluationDataset,
    RetrievalEvaluationRecord,
    RetrievalEvaluationSummary,
)


class RetrievalEvaluationDatasetResponse(BaseModel):
    dataset: RetrievalEvaluationDataset


class RetrievalEvaluationListItem(BaseModel):
    evaluation_id: str
    lifecycle: Literal["confirmed"]
    status: Literal["completed"]
    dataset_id: str
    dataset_checksum: str
    requested_strategy: str
    effective_strategies: list[str] = Field(default_factory=list)
    index_snapshot_id: str
    confirmed_card_count: int
    summary: RetrievalEvaluationSummary
    failure_count: int
    started_at: str
    finished_at: str

    @classmethod
    def from_record(
        cls,
        record: RetrievalEvaluationRecord,
    ) -> RetrievalEvaluationListItem:
        return cls(
            evaluation_id=record.evaluation_id,
            lifecycle=record.lifecycle,
            status=record.status,
            dataset_id=record.dataset_id,
            dataset_checksum=record.dataset_checksum,
            requested_strategy=record.requested_strategy,
            effective_strategies=record.effective_strategies,
            index_snapshot_id=record.index_snapshot_id,
            confirmed_card_count=record.confirmed_card_count,
            summary=record.summary,
            failure_count=len(record.failures),
            started_at=record.started_at,
            finished_at=record.finished_at,
        )


class RetrievalEvaluationListResponse(BaseModel):
    evaluations: list[RetrievalEvaluationListItem] = Field(default_factory=list)


class RetrievalEvaluationResponse(BaseModel):
    evaluation: RetrievalEvaluationRecord
