"""Evaluation dataset repository boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from taichu.application.evaluations.knowledge_extraction.dataset import (
    DatasetValidationResult,
    EvaluationDatasetSummary,
    LoadedEvaluationDataset,
)


@runtime_checkable
class EvaluationDatasetRepository(Protocol):
    """Discover and load immutable knowledge-extraction evaluation data."""

    async def list_datasets(
        self,
        *,
        include_non_confirmed: bool = False,
    ) -> list[EvaluationDatasetSummary]:
        """List datasets without exposing filesystem paths."""
        ...

    async def validate_dataset(self, dataset_id: str) -> DatasetValidationResult:
        """Validate one dataset and return all discoverable issues."""
        ...

    async def get_dataset(self, dataset_id: str) -> LoadedEvaluationDataset:
        """Return one confirmed and fully validated dataset."""
        ...
