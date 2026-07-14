"""通用写作助手专属评测集与结果仓储契约。"""

from typing import Protocol

from taichu.application.evaluations.general_agent.models import (
    GeneralAgentEvaluationDataset,
    GeneralAgentEvaluationRecord,
)


class GeneralAgentEvaluationDatasetRepository(Protocol):
    async def list_datasets(self) -> list[GeneralAgentEvaluationDataset]: ...

    async def get_dataset(
        self,
        dataset_id: str,
    ) -> GeneralAgentEvaluationDataset | None: ...


class GeneralAgentEvaluationResultRepository(Protocol):
    async def save(
        self,
        record: GeneralAgentEvaluationRecord,
    ) -> GeneralAgentEvaluationRecord: ...

    async def get(self, evaluation_id: str) -> GeneralAgentEvaluationRecord | None: ...

    async def list_records(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str = "all",
    ) -> tuple[list[GeneralAgentEvaluationRecord], int]: ...

    async def delete(self, evaluation_id: str) -> bool: ...
