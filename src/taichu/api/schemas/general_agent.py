"""通用写作助手 Runtime 的 HTTP 契约。"""

from pydantic import BaseModel, Field, model_validator

from taichu.application.agent_memory.models import AgentMemoryEntry
from taichu.application.general_agent.models import (
    GeneralAgentConversation,
    GeneralAgentRun,
    GeneralAgentRunLimits,
    GeneralAgentScope,
)
from taichu.application.general_agent.recovery import GeneralAgentRecoverySnapshot
from taichu.application.invocations.models import InvocationTraceRecord


class GeneralAgentRunRequest(BaseModel):
    user_goal: str = Field(min_length=1, max_length=100_000)
    conversation_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    start_new_conversation: bool | None = None
    scope: GeneralAgentScope = Field(default_factory=GeneralAgentScope)
    author_constraints: list[str] = Field(default_factory=list, max_length=100)
    external_access_allowed: bool = False
    limits: GeneralAgentRunLimits = Field(default_factory=GeneralAgentRunLimits)

    @model_validator(mode="after")
    def validate_conversation_intent(self) -> "GeneralAgentRunRequest":
        if self.start_new_conversation is True and self.conversation_id is not None:
            raise ValueError("开启新对话时不能同时传入已有会话标识。")
        if self.start_new_conversation is False and self.conversation_id is None:
            raise ValueError("继续当前对话时必须传入会话标识。")
        return self


class GeneralAgentResumeRequest(BaseModel):
    answer: str = Field(default="", max_length=100_000)
    approve: bool | None = None
    second_confirmation: bool = False


class GeneralAgentRunSummary(BaseModel):
    run_id: str
    conversation_id: str
    request_index: int = Field(ge=1)
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
    memory_count: int = Field(default=0, ge=0)
    context_snapshot_id: str | None = None
    context_compressed: bool = False
    estimated_context_tokens: int = Field(default=0, ge=0)
    created_at: str
    updated_at: str
    finished_at: str | None = None


class GeneralAgentRunResponse(BaseModel):
    run: GeneralAgentRun


class GeneralAgentRecoveryResponse(BaseModel):
    recovery: GeneralAgentRecoverySnapshot


class GeneralAgentRunListResponse(BaseModel):
    runs: list[GeneralAgentRunSummary] = Field(default_factory=list)
    page: int
    page_size: int
    total: int


class GeneralAgentDeleteResponse(BaseModel):
    run_id: str
    deleted: bool


class GeneralAgentConversationListResponse(BaseModel):
    conversations: list[GeneralAgentConversation] = Field(default_factory=list)
    page: int
    page_size: int
    total: int


class GeneralAgentConversationResponse(BaseModel):
    conversation_id: str
    runs: list[GeneralAgentRun] = Field(default_factory=list)


class GeneralAgentConversationDeleteResponse(BaseModel):
    conversation_id: str
    deleted_count: int = Field(ge=0)


class GeneralAgentTraceListResponse(BaseModel):
    traces: list[InvocationTraceRecord] = Field(default_factory=list)
    total: int = Field(ge=0)


class AgentMemoryListResponse(BaseModel):
    conversation_id: str
    memories: list[AgentMemoryEntry] = Field(default_factory=list)
    total: int = Field(ge=0)


class AgentMemoryResponse(BaseModel):
    memory: AgentMemoryEntry


class AgentMemoryDeleteResponse(BaseModel):
    memory_id: str
    deleted: bool
