"""可供下游专业子 Agent 复用的有类型草稿产物。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IntermediateArtifactRecord(BaseModel):
    """JSON 中间态，不是正文或结构化知识事实。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lifecycle: Literal["draft"] = "draft"
    artifact_id: str = Field(pattern=r"^artifact_[a-f0-9]{32}$")
    artifact_type: str = Field(min_length=1, max_length=128)
    producer: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    call_id: str = Field(min_length=1, max_length=128)
    input_sha256: str = Field(min_length=64, max_length=64)
    content_sha256: str = Field(min_length=64, max_length=64)
    payload: dict[str, object]
    source_refs: list[str] = Field(default_factory=list)
    created_at: str = Field(min_length=1)
