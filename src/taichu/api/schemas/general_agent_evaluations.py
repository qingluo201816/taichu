"""通用写作助手专属评测 HTTP 契约。"""

from pydantic import BaseModel, Field

from taichu.application.evaluations.general_agent.models import (
    GeneralAgentEvaluationDataset,
    GeneralAgentEvaluationRecord,
)


class CreateGeneralAgentEvaluationRequest(BaseModel):
    dataset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    run_id: str = Field(pattern=r"^general_run_\d{8}_\d{6}_[a-z0-9]{6}$")


class GeneralAgentEvaluationDatasetListResponse(BaseModel):
    datasets: list[GeneralAgentEvaluationDataset] = Field(default_factory=list)


class GeneralAgentEvaluationDatasetResponse(BaseModel):
    dataset: GeneralAgentEvaluationDataset


class GeneralAgentEvaluationResponse(BaseModel):
    evaluation: GeneralAgentEvaluationRecord


class GeneralAgentEvaluationListResponse(BaseModel):
    evaluations: list[GeneralAgentEvaluationRecord] = Field(default_factory=list)
    page: int
    page_size: int
    total: int


class GeneralAgentEvaluationDeleteResponse(BaseModel):
    evaluation_id: str
    deleted: bool
