"""通用写作助手 Runtime 独立的业务运行模型。"""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
import json
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


class GeneralAgentPlanSelectionNode(GeneralAgentModel):
    """第一阶段只选择能力和依赖，不提前猜测精确参数。"""

    node_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    kind: GeneralAgentNodeKind
    capability_name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    objective: str = Field(min_length=1, max_length=10_000)
    dependencies: list[str] = Field(default_factory=list, max_length=20)
    continue_on_failure: bool = False


class GeneralAgentPlanSelection(GeneralAgentModel):
    """全量轻量能力目录上的计划骨架。"""

    rationale: str = Field(min_length=1, max_length=20_000)
    requires_clarification: bool = False
    clarification_question: str = Field(default="", max_length=20_000)
    direct_response: str = Field(default="", max_length=100_000)
    nodes: list[GeneralAgentPlanSelectionNode] = Field(
        default_factory=list, max_length=40
    )
    final_response_guidance: str = Field(default="", max_length=20_000)

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        if self.requires_clarification:
            if not self.clarification_question.strip():
                raise ValueError("需要澄清的计划必须提供澄清问题。")
            if self.nodes:
                raise ValueError("等待澄清时不得提前安排执行节点。")
            return self
        if not self.nodes and not self.direct_response.strip():
            raise ValueError("能力选择必须包含节点或可直接回答的内容。")
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
        _ensure_acyclic(self.nodes)
        return self


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
    attempt_id: str | None = Field(
        default=None,
        pattern=r"^attempt_[a-f0-9]{32}$",
    )
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
    effect_id: str | None = Field(
        default=None,
        pattern=r"^effect_[a-f0-9]{32}$",
    )
    effect_status: str | None = Field(default=None, max_length=64)
    reconciliation_reason: str = Field(default="", max_length=2_000)
    duplicate_execution_protected: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int = Field(default=0, ge=0)
    error_type: str | None = None
    error_message: str | None = None


class GeneralAgentHumanRequest(GeneralAgentModel):
    request_id: str = Field(min_length=1, max_length=128)
    kind: Literal[
        "clarification",
        "write_authorization",
        "effect_reconciliation",
    ]
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


class GeneralAgentContextCategoryStat(GeneralAgentModel):
    category: str = Field(min_length=1, max_length=64)
    selected_count: int = Field(default=0, ge=0)
    selected_char_count: int = Field(default=0, ge=0)
    omitted_count: int = Field(default=0, ge=0)
    compressed: bool = False
    reason: str = Field(default="", max_length=500)


class GeneralAgentContextMemory(GeneralAgentModel):
    memory_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=20_000)
    source_refs: list[str] = Field(default_factory=list, max_length=100)
    artifact_refs: list[str] = Field(default_factory=list, max_length=100)
    content_sha256: str = Field(min_length=64, max_length=64)


class ContextDigest(GeneralAgentModel):
    """过程历史压缩后的结构化摘要，不承担小说事实职责。"""

    current_request: str = Field(min_length=1, max_length=100_000)
    user_instructions: list[str] = Field(default_factory=list, max_length=100)
    task_summaries: list[str] = Field(default_factory=list, max_length=100)
    completed_nodes: list[str] = Field(default_factory=list, max_length=100)
    fact_source_refs: list[str] = Field(default_factory=list, max_length=200)
    unresolved_issues: list[str] = Field(default_factory=list, max_length=100)
    next_conditions: list[str] = Field(default_factory=list, max_length=100)
    omitted_counts: dict[str, int] = Field(default_factory=dict)
    original_source_ids: list[str] = Field(default_factory=list, max_length=500)


class GeneralAgentCurrentRequest(GeneralAgentModel):
    """完整保留且最后才允许触及的当前请求层。"""

    content: str = Field(min_length=1, max_length=100_000)
    user_constraints: list[str] = Field(default_factory=list, max_length=100)
    scope: dict[str, Any] = Field(default_factory=dict)


class GeneralAgentWorkingMemory(GeneralAgentModel):
    """当前工作面：任务摘要、资源摘要、过程笔记与节点状态。"""

    memories: list[GeneralAgentContextMemory] = Field(default_factory=list)
    plan_summary: dict[str, Any] | None = None
    node_summaries: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_issues: list[str] = Field(default_factory=list, max_length=100)


class GeneralAgentContextEnvelope(GeneralAgentModel):
    """按稳定背景、工作、相关、过程和当前请求五层组装的上下文。"""

    phase: Literal["plan", "replan", "verify"]
    stable_background: list[str] = Field(default_factory=list, max_length=100)
    working_memory: GeneralAgentWorkingMemory = Field(
        default_factory=GeneralAgentWorkingMemory
    )
    related_memories: list[GeneralAgentContextMemory] = Field(default_factory=list)
    process_history: list[GeneralAgentMessage] = Field(default_factory=list)
    current_request: GeneralAgentCurrentRequest
    replan_guidance: str = Field(default="", max_length=20_000)
    digest: ContextDigest | None = None
    category_stats: list[GeneralAgentContextCategoryStat] = Field(default_factory=list)
    total_char_count: int = Field(default=0, ge=0)
    estimated_token_count: int = Field(default=0, ge=0)
    compressed: bool = False
    fallback_used: bool = False

    @property
    def current_goal(self) -> str:
        return self.current_request.content

    @property
    def author_constraints(self) -> list[str]:
        return self.current_request.user_constraints

    @property
    def scope(self) -> dict[str, Any]:
        return self.current_request.scope

    @property
    def recent_messages(self) -> list[GeneralAgentMessage]:
        return self.process_history

    @property
    def runtime_memories(self) -> list[GeneralAgentContextMemory]:
        return [*self.working_memory.memories, *self.related_memories]

    @property
    def plan_summary(self) -> dict[str, Any] | None:
        return self.working_memory.plan_summary

    @property
    def node_summaries(self) -> list[dict[str, Any]]:
        return self.working_memory.node_summaries

    @property
    def unresolved_issues(self) -> list[str]:
        return self.working_memory.unresolved_issues


class GeneralAgentContextMemoryRef(GeneralAgentModel):
    memory_id: str = Field(min_length=1, max_length=128)
    content_sha256: str = Field(min_length=64, max_length=64)


class GeneralAgentContextSnapshot(GeneralAgentModel):
    snapshot_id: str = Field(pattern=r"^context_\d{8}_\d{6}_[a-z0-9]{8}$")
    phase: Literal["plan", "replan", "verify"]
    conversation_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    created_at: str = Field(min_length=1)
    policy_snapshot: dict[str, Any] = Field(default_factory=dict)
    memory_refs: list[GeneralAgentContextMemoryRef] = Field(default_factory=list)
    envelope: GeneralAgentContextEnvelope
    content_sha256: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_snapshot_hash(self) -> Self:
        if self.content_sha256 != context_snapshot_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        ):
            raise ValueError("上下文快照校验和不匹配。")
        return self


class GeneralAgentCompressionStats(GeneralAgentModel):
    compressed: bool = False
    fallback_used: bool = False
    input_char_count: int = Field(default=0, ge=0)
    output_char_count: int = Field(default=0, ge=0)
    estimated_token_count: int = Field(default=0, ge=0)
    omitted_message_count: int = Field(default=0, ge=0)
    omitted_node_count: int = Field(default=0, ge=0)
    selected_memory_count: int = Field(default=0, ge=0)


class GeneralAgentRun(GeneralAgentModel):
    """通用 Runtime 的完整可恢复检查点。"""

    run_id: str = Field(pattern=r"^general_run_\d{8}_\d{6}_[a-z0-9]{6}$")
    task_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=128)
    request_index: int = Field(ge=1)
    parent_run_id: str | None = Field(default=None, max_length=128)
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
    memory_refs: list[str] = Field(default_factory=list, max_length=500)
    context_snapshot_id: str | None = Field(default=None, max_length=128)
    context_snapshot: GeneralAgentContextSnapshot | None = None
    compression_stats: GeneralAgentCompressionStats = Field(
        default_factory=GeneralAgentCompressionStats
    )
    context_resume_differences: list[str] = Field(default_factory=list, max_length=100)
    lifecycle_events: list[GeneralAgentLifecycleEvent] = Field(default_factory=list)
    checkpoint_revision: int = Field(default=0, ge=0)
    resumable: bool = True
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    started_at: str = Field(min_length=1)
    finished_at: str | None = None
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_conversation_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        run_id = payload.get("run_id")
        task_id = payload.get("task_id")
        payload.setdefault("conversation_id", task_id or run_id)
        messages = payload.get("messages")
        legacy_request_count = (
            sum(
                1
                for message in messages
                if isinstance(message, dict) and message.get("role") == "user"
            )
            if isinstance(messages, list)
            else 1
        )
        payload.setdefault("request_index", max(1, legacy_request_count))
        payload.setdefault("parent_run_id", None)
        payload.setdefault("memory_refs", [])
        payload.setdefault("context_snapshot_id", None)
        payload.setdefault("context_snapshot", None)
        payload.setdefault("compression_stats", {})
        payload.setdefault("context_resume_differences", [])
        return payload

    @model_validator(mode="after")
    def validate_context_snapshot_reference(self) -> Self:
        if self.context_snapshot is None:
            if self.context_snapshot_id is not None:
                raise ValueError("上下文快照标识缺少对应快照。")
            return self
        if self.context_snapshot_id != self.context_snapshot.snapshot_id:
            raise ValueError("运行引用的上下文快照标识不一致。")
        if self.context_snapshot.run_id != self.run_id:
            raise ValueError("上下文快照不能跨运行复用。")
        if self.context_snapshot.conversation_id != self.conversation_id:
            raise ValueError("上下文快照不能跨会话复用。")
        return self


class GeneralAgentConversation(GeneralAgentModel):
    """由多次独立运行组成的持久化对话摘要。"""

    conversation_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=100_000)
    status: GeneralAgentRunStatus
    request_count: int = Field(ge=1)
    latest_run_id: str = Field(min_length=1, max_length=128)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class GeneralAgentPlanDraft(GeneralAgentExecutionPlan):
    """编排模型输出 Schema；与持久化计划保持同一业务约束。"""


class GeneralAgentVerification(GeneralAgentModel):
    outcome: Literal["satisfied", "partial", "failed"]
    final_answer: str = Field(min_length=1, max_length=200_000)
    issues: list[str] = Field(default_factory=list, max_length=100)
    should_replan: bool = False
    replan_guidance: str = Field(default="", max_length=20_000)


def _ensure_acyclic(
    nodes: list[GeneralAgentPlanNode] | list[GeneralAgentPlanSelectionNode],
) -> None:
    dependencies = {node.node_id: set(node.dependencies) for node in nodes}
    remaining = set(dependencies)
    while remaining:
        ready = {
            node_id for node_id in remaining if not dependencies[node_id] & remaining
        }
        if not ready:
            raise ValueError("计划节点依赖形成了循环。")
        remaining -= ready


def context_snapshot_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()
