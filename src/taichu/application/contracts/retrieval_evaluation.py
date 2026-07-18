"""独立知识召回评测集与结果仓储契约。"""

from typing import Protocol

from taichu.application.evaluations.retrieval.models import (
    RetrievalEvaluationDataset,
    RetrievalEvaluationRecord,
)


class RetrievalEvaluationDatasetRepository(Protocol):
    async def get_dataset(
        self,
        dataset_id: str,
    ) -> RetrievalEvaluationDataset | None: ...


class RetrievalEvaluationResultRepository(Protocol):
    async def save(
        self,
        record: RetrievalEvaluationRecord,
    ) -> RetrievalEvaluationRecord: ...

    async def get(
        self,
        evaluation_id: str,
    ) -> RetrievalEvaluationRecord | None: ...

    async def list_records(
        self,
        *,
        limit: int = 20,
    ) -> list[RetrievalEvaluationRecord]: ...
