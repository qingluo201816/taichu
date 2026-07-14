"""通用写作助手 Runtime 的 HTTP 契约。"""

from pydantic import BaseModel, Field

from taichu.application.general_agent.models import (
    GeneralAgentRun,
    GeneralAgentRunLimits,
    GeneralAgentScope,
)
from taichu.application.invocations.models import InvocationTraceRecord


class GeneralAgentRunRequest(BaseModel):
    user_goal: str = Field(min_length=1, max_length=100_000)
    scope: GeneralAgentScope = Field(default_factory=GeneralAgentScope)
    author_constraints: list[str] = Field(default_factory=list, max_length=100)
    external_access_allowed: bool = False
    limits: GeneralAgentRunLimits = Field(default_factory=GeneralAgentRunLimits)


class GeneralAgentResumeRequest(BaseModel):
    answer: str = Field(default="", max_length=100_000)
    approve: bool | None = None
    second_confirmation: bool = False


class GeneralAgentRunSummary(BaseModel):
    run_id: str
    agent_name: str
    user_goal: str
    status: str
    scope_type: str
    plan_revision: int
    replan_count: int
    completed_node_count: int
    failed_node_count: int
    total_node_count: int
    waiting_human_kind: str | None = None
    final_answer_preview: str = ""
    created_at: str
    updated_at: str
    finished_at: str | None = None


class GeneralAgentRunResponse(BaseModel):
    run: GeneralAgentRun


class GeneralAgentRunListResponse(BaseModel):
    runs: list[GeneralAgentRunSummary] = Field(default_factory=list)
    page: int
    page_size: int
    total: int


class GeneralAgentDeleteResponse(BaseModel):
    run_id: str
    deleted: bool


class GeneralAgentTraceListResponse(BaseModel):
    traces: list[InvocationTraceRecord] = Field(default_factory=list)
    total: int = Field(ge=0)
