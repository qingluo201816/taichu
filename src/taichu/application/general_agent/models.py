"""通用写作助手 Runtime 独立的业务运行模型。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GeneralAgentModel(BaseModel):
    """拒绝额外字段的不可变 Runtime 模型。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class GeneralAgentRunStatus(StrEnum):
    """通用 Agent 长流程生命周期。"""

    INIT = "init"
    CLARIFYING = "clarifying"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING_HUMAN = "waiting_human"
    VERIFYING = "verifying"
    REPLANNING = "replanning"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class GeneralAgentNodeKind(StrEnum):
    TOOL = "tool"
    SUBAGENT = "subagent"


class GeneralAgentNodeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_HUMAN = "waiting_human"


class GeneralAgentMessage(GeneralAgentModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=100_000)
    created_at: str = Field(min_length=1)


class GeneralAgentScope(GeneralAgentModel):
    """由页面显式传入的当前写作范围，不通过 Tool 反查页面状态。"""

    scope_type: Literal["none", "selection", "chapter", "range", "novel"] = "none"
    current_chapter_id: str | None = Field(default=None, max_length=128)
    chapter_ids: list[str] = Field(default_factory=list, max_length=100)
    selection_text: str = Field(default="", max_length=100_000)
    direct_context: str = Field(default="", max_length=100_000)


class GeneralAgentRunLimits(GeneralAgentModel):
    max_plan_nodes: int = Field(default=12, ge=1, le=40)
    max_replans: int = Field(default=1, ge=0, le=3)
    max_concurrency: int = Field(default=3, ge=1, le=8)
    max_total_tool_calls: int = Field(default=40, ge=1, le=100)
    max_runtime_seconds: int = Field(default=900, ge=30, le=7_200)


class GeneralAgentInputBinding(GeneralAgentModel):
    """把一个上游节点输出字段绑定到当前节点输入字段。"""

    source_node_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    source_path: str = Field(min_length=1, max_length=256)
    target_path: str = Field(min_length=1, max_length=256)


class GeneralAgentPlanNode(GeneralAgentModel):
    """高层编排 Agent 针对单次请求生成的一个能力调用节点。"""

    node_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    kind: GeneralAgentNodeKind
    capability_name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    objective: str = Field(min_length=1, max_length=10_000)
    input_data: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list, max_length=20)
    input_bindings: list[GeneralAgentInputBinding] = Field(
        default_factory=list,
        max_length=30,
    )
    continue_on_failure: bool = False


class GeneralAgentExecutionPlan(GeneralAgentModel):
    """一次计划修订对应的动态 DAG 定义。"""

    rationale: str = Field(min_length=1, max_length=20_000)
    requires_clarification: bool = False
    clarification_question: str = Field(default="", max_length=20_000)
    direct_response: str = Field(default="", max_length=100_000)
    nodes: list[GeneralAgentPlanNode] = Field(default_factory=list, max_length=40)
    final_response_guidance: str = Field(default="", max_length=20_000)

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        if self.requires_clarification:
            if not self.clarification_question.strip():
                raise ValueError("需要澄清的计划必须提供澄清问题。")
            if self.nodes:
                raise ValueError("等待澄清时不得提前安排执行节点。")
            return self
        if not self.nodes and not self.direct_response.strip():
            raise ValueError("计划必须包含能力节点或可直接回答的内容。")
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("计划节点 ID 必须唯一。")
        known = set(node_ids)
        for node in self.nodes:
            if node.node_id in node.dependencies:
                raise ValueError(f"节点“{node.node_id}”不能依赖自身。")
            unknown = set(node.dependencies) - known
            if unknown:
                raise ValueError(
                    f"节点“{node.node_id}”依赖未知节点：{', '.join(sorted(unknown))}"
                )
            for binding in node.input_bindings:
                if binding.source_node_id not in node.dependencies:
                    raise ValueError(
                        f"节点“{node.node_id}”的输入绑定必须来自直接依赖节点。"
                    )
        _ensure_acyclic(self.nodes)
        return self


class GeneralAgentNodeRun(GeneralAgentModel):
    node_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    plan_revision: int = Field(ge=0)
    kind: GeneralAgentNodeKind
    capability_name: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)
    status: GeneralAgentNodeStatus = GeneralAgentNodeStatus.PENDING
    resolved_input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    authorization_grant_id: str | None = None
    authorization_approved: bool = False
    authorization_second_confirmation: bool = False
    authorization_resource_scopes: list[str] = Field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int = Field(default=0, ge=0)
    error_type: str | None = None
    error_message: str | None = None


class GeneralAgentHumanRequest(GeneralAgentModel):
    request_id: str = Field(min_length=1, max_length=128)
    kind: Literal["clarification", "write_authorization"]
    prompt: str = Field(min_length=1, max_length=20_000)
    node_id: str | None = None
    tool_name: str | None = None
    input_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    input_summary: dict[str, Any] = Field(default_factory=dict)
    resource_scopes: list[str] = Field(default_factory=list)
    second_confirmation_required: bool = False
    created_at: str = Field(min_length=1)


class GeneralAgentLifecycleEvent(GeneralAgentModel):
    status: GeneralAgentRunStatus
    reason: str = ""
    created_at: str = Field(min_length=1)


class GeneralAgentRun(GeneralAgentModel):
    """通用 Runtime 的完整可恢复检查点。"""

    run_id: str = Field(pattern=r"^general_run_\d{8}_\d{6}_[a-z0-9]{6}$")
    task_id: str = Field(min_length=1, max_length=128)
    agent_name: Literal["general_writing_assistant"] = "general_writing_assistant"
    user_goal: str = Field(min_length=1, max_length=100_000)
    scope: GeneralAgentScope = Field(default_factory=GeneralAgentScope)
    author_constraints: list[str] = Field(default_factory=list, max_length=100)
    external_access_allowed: bool = False
    limits: GeneralAgentRunLimits = Field(default_factory=GeneralAgentRunLimits)
    status: GeneralAgentRunStatus = GeneralAgentRunStatus.INIT
    messages: list[GeneralAgentMessage] = Field(default_factory=list)
    plan: GeneralAgentExecutionPlan | None = None
    plan_revision: int = 0
    replan_count: int = 0
    node_runs: list[GeneralAgentNodeRun] = Field(default_factory=list)
    pending_human_request: GeneralAgentHumanRequest | None = None
    final_answer: str = ""
    verification_issues: list[str] = Field(default_factory=list)
    lifecycle_events: list[GeneralAgentLifecycleEvent] = Field(default_factory=list)
    checkpoint_revision: int = Field(default=0, ge=0)
    resumable: bool = True
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    started_at: str = Field(min_length=1)
    finished_at: str | None = None
    errors: list[str] = Field(default_factory=list)


class GeneralAgentPlanDraft(GeneralAgentExecutionPlan):
    """编排模型输出 Schema；与持久化计划保持同一业务约束。"""


class GeneralAgentVerification(GeneralAgentModel):
    outcome: Literal["satisfied", "partial", "failed"]
    final_answer: str = Field(min_length=1, max_length=200_000)
    issues: list[str] = Field(default_factory=list, max_length=100)
    should_replan: bool = False
    replan_guidance: str = Field(default="", max_length=20_000)


def _ensure_acyclic(nodes: list[GeneralAgentPlanNode]) -> None:
    dependencies = {node.node_id: set(node.dependencies) for node in nodes}
    remaining = set(dependencies)
    while remaining:
        ready = {node_id for node_id in remaining if not dependencies[node_id] & remaining}
        if not ready:
            raise ValueError("计划节点依赖形成了循环。")
        remaining -= ready
