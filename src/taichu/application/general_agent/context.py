"""通用 Runtime 的五层上下文组装、固定裁剪顺序与可追溯快照。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any, Literal
from uuid import uuid4

from taichu.application.agent_memory.models import (
    AgentMemoryDependencyRelation,
    AgentMemoryEntry,
    AgentMemoryKind,
    AgentMemoryQuery,
    AgentMemoryValidity,
    memory_state_sha256,
)
from taichu.application.agent_memory.projection import (
    CurrentFactProjectionPolicy,
    MemoryProjectionCandidate,
    RepairProjection,
)
from taichu.application.general_agent.models import (
    ContextDigest,
    GeneralAgentContextCategoryStat,
    GeneralAgentContextEnvelope,
    GeneralAgentContextLayerTrace,
    GeneralAgentContextMemory,
    GeneralAgentContextMemoryRef,
    GeneralAgentContextProjectionTrace,
    GeneralAgentContextSnapshot,
    GeneralAgentCurrentRequest,
    GeneralAgentHistoryMemory,
    GeneralAgentMessage,
    GeneralAgentNodeRun,
    GeneralAgentNodeStatus,
    GeneralAgentRun,
    GeneralAgentWorkingMemory,
    GeneralAgentAssemblyTrace,
    context_snapshot_sha256,
)
from taichu.application.invocations.models import now_iso
from taichu.application.services.agent_memory_service import AgentMemoryService

ContextPhase = Literal["plan", "replan", "verify"]

_STABLE_MEMORY = (
    "你是太初通用写作助手的高层编排 Agent，负责理解当前请求、选择最小充分路径并收敛结果。",
    "只能调用能力目录中真实存在且契约完整的 Tool 或子 Agent；不得临时创造能力。",
    "Markdown 正文是章节原文事实源；MongoDB 中已确认知识卡是结构事实源；所有索引均为可重建派生层。",
    "运行记忆只延续工作状态，不是小说事实；涉及事实时必须重新读取正文或通过统一召回取证。",
    "工作记忆中标为失效、被否决或被替代的记录只用于理解错误和修复，不得作为当前事实、正文或最终结论。",
    "写入正文或结构事实必须遵守授权、校验和作者确认门禁。",
)
_CURRENT_REQUEST_CONTENT_LIMIT = 100_000
_INVALID_MEMORY_REPAIR_CONTENT = (
    "该运行记忆已经失效；模型上下文只保留状态与内容哈希用于修复审计，"
    "必须重新取证或重新生成，不得把原内容作为当前事实使用。"
)
_INVALID_MEMORY_REPAIR_REASON = (
    "原始失效原因保存在运行审计中；模型上下文不投影可能复活旧结论的原文。"
)


@dataclass(frozen=True, slots=True)
class GeneralAgentContextPolicy:
    """可保存到快照中的五层上下文预算。"""

    total_char_budget: int = 180_000
    working_memory_retrieval_top_k: int = 12
    working_memory_char_budget: int = 24_000
    long_term_memory_char_budget: int = 12_000
    history_memory_limit: int = 10
    history_memory_char_budget: int = 24_000
    node_summary_char_budget: int = 20_000
    plan_summary_char_budget: int = 20_000
    message_compaction_threshold: int = 20
    node_output_compaction_threshold: int = 30_000
    estimated_chars_per_token: int = 4

    def snapshot(self) -> dict[str, Any]:
        return {
            "policy": "five_layer_runtime_context",
            "trim_order": [
                "long_term_memory",
                "history_memory",
                "working_memory",
                "stable_memory_protected",
                "current_request_protected",
            ],
            **asdict(self),
        }


@dataclass(frozen=True, slots=True)
class ContextAssemblyResult:
    snapshot: GeneralAgentContextSnapshot
    reused_snapshot: bool
    resume_differences: tuple[str, ...] = ()


class ContextCompactor:
    """把旧工作状态压成结构化摘要，同时保留来源标识。"""

    def compact(
        self,
        run: GeneralAgentRun,
        *,
        memories: list[GeneralAgentContextMemory],
        omitted_message_count: int,
        omitted_node_count: int,
        excluded_node_ids: set[str] | None = None,
    ) -> ContextDigest:
        memories = _active_context_memories(memories)
        current_nodes = [
            node
            for node in _current_nodes(run)
            if node.node_id not in (excluded_node_ids or set())
        ]
        return ContextDigest(
            user_instructions=_deduplicate(
                [
                    *run.author_constraints,
                    *[
                        memory.content
                        for memory in memories
                        if memory.kind == AgentMemoryKind.USER_INSTRUCTION.value
                    ],
                ]
            ),
            task_summaries=_deduplicate(
                [
                    memory.content
                    for memory in memories
                    if memory.kind == AgentMemoryKind.TASK_SUMMARY.value
                ]
            ),
            completed_nodes=[
                f"{node.capability_name}：{node.objective[:500]}"
                for node in current_nodes
                if node.status is GeneralAgentNodeStatus.SUCCESS
            ],
            fact_source_refs=_deduplicate(
                [
                    *[ref for memory in memories for ref in memory.source_refs],
                    *[ref for node in current_nodes for ref in node.source_refs],
                ]
            ),
            unresolved_issues=_deduplicate(
                [
                    *run.verification_issues,
                    *[
                        memory.content
                        for memory in memories
                        if memory.kind == AgentMemoryKind.UNRESOLVED_ISSUE.value
                    ],
                ]
            ),
            next_conditions=(
                [run.pending_human_request.prompt]
                if run.pending_human_request is not None
                else []
            ),
            omitted_counts={
                "messages": omitted_message_count,
                "nodes": omitted_node_count,
            },
            original_source_ids=_deduplicate(
                [
                    *[
                        f"message:{index}:{message.created_at}"
                        for index, message in enumerate(run.messages)
                    ],
                    *[
                        f"node:{node.plan_revision}:{node.node_id}"
                        for node in run.node_runs
                    ],
                    *[memory.memory_id for memory in memories],
                ]
            ),
        )


class ContextAssembler:
    """从第一次请求开始，在规划、重规划和校验前组装同一五层结构。"""

    def __init__(
        self,
        *,
        memory_service: AgentMemoryService,
        policy: GeneralAgentContextPolicy | None = None,
        compactor: ContextCompactor | None = None,
    ) -> None:
        self._memory_service = memory_service
        self._policy = policy or GeneralAgentContextPolicy()
        self._compactor = compactor or ContextCompactor()

    async def assemble(
        self,
        run: GeneralAgentRun,
        *,
        phase: ContextPhase,
        replan_guidance: str = "",
    ) -> ContextAssemblyResult:
        _ensure_protected_context_fits(
            run,
            phase=phase,
            policy=self._policy,
        )
        await self._memory_service.refresh_evidence_validity(run.conversation_id)
        reusable = run.context_snapshot
        if (
            reusable is not None
            and reusable.phase == phase
            and reusable.policy_snapshot == self._policy.snapshot()
            and reusable.envelope.working_memory.replan_guidance == replan_guidance
        ):
            differences = await self._snapshot_differences(reusable)
            if not differences:
                return ContextAssemblyResult(snapshot=reusable, reused_snapshot=True)
        else:
            differences = []

        as_of = now_iso()
        active_entries = await self._memory_service.list_active(
            run.conversation_id,
            current_request_index=run.request_index,
            as_of=as_of,
            refresh_evidence=False,
        )
        baseline_entries = _working_entries(
            active_entries,
            char_budget=self._policy.working_memory_char_budget,
        )
        selection = await self._memory_service.retrieve(
            AgentMemoryQuery(
                conversation_id=run.conversation_id,
                current_request_index=run.request_index,
                query_text=_memory_query_text(run, replan_guidance),
                top_k=self._policy.working_memory_retrieval_top_k,
                char_budget=self._policy.working_memory_char_budget,
                as_of=as_of,
            ),
            refresh_evidence=False,
        )
        working_entries = _working_entries(
            _deduplicate_entries([*baseline_entries, *selection.entries]),
            char_budget=self._policy.working_memory_char_budget,
        )
        invalidated_entries = await self._memory_service.list_invalidated(
            run.conversation_id,
            current_request_index=run.request_index,
            as_of=as_of,
            limit=6,
            char_budget=min(8_000, self._policy.working_memory_char_budget // 3),
            refresh_evidence=False,
        )
        producer_entries = [
            entry for entry in working_entries if entry.producer_ref is not None
        ]
        current_projection = CurrentFactProjectionPolicy().project(
            tuple(
                MemoryProjectionCandidate(
                    entry=entry,
                    role=AgentMemoryDependencyRelation.BASIS,
                )
                for entry in producer_entries
            ),
            allowed_producer_refs=frozenset(
                entry.producer_ref
                for entry in producer_entries
                if entry.producer_ref is not None
            ),
        )
        current_producer_ids = {item.memory_id for item in current_projection.items}
        working_entries = [
            entry
            for entry in working_entries
            if entry.producer_ref is None or entry.memory_id in current_producer_ids
        ]
        repair_projection = RepairProjection.from_candidates(
            tuple(
                MemoryProjectionCandidate(
                    entry=entry,
                    role=AgentMemoryDependencyRelation.REPAIR_SOURCE,
                )
                for entry in invalidated_entries
            ),
            allowed_producer_refs=frozenset(
                entry.producer_ref
                for entry in invalidated_entries
                if entry.producer_ref is not None
            ),
        )
        repair_memory_ids = {item.memory_id for item in repair_projection.items}
        invalidated_entries = [
            entry
            for entry in invalidated_entries
            if entry.memory_id in repair_memory_ids
        ]
        node_producer_refs = {
            _node_memory_producer_ref(run, node) for node in _current_nodes(run)
        }
        producer_validities = await self._memory_service.producer_validities(
            run.conversation_id,
            node_producer_refs,
        )
        excluded_node_ids = {
            node.node_id
            for node in _current_nodes(run)
            if producer_validities.get(_node_memory_producer_ref(run, node))
            not in {None, AgentMemoryValidity.ACTIVE}
        }
        envelope, assembly_trace = self._build_envelope(
            run,
            phase=phase,
            replan_guidance=replan_guidance,
            working_memories=[
                _context_memory(
                    entry,
                    projection_role=AgentMemoryDependencyRelation.BASIS,
                )
                for entry in working_entries
            ],
            invalidated_memories=[
                _context_memory(
                    entry,
                    projection_role=AgentMemoryDependencyRelation.REPAIR_SOURCE,
                    repair_only=True,
                )
                for entry in invalidated_entries
            ],
            excluded_node_ids=excluded_node_ids,
        )
        created_at = now_iso()
        snapshot_id = (
            f"context_{created_at[0:10].replace('-', '')}_"
            f"{created_at[11:19].replace(':', '')}_{uuid4().hex[:8]}"
        )
        all_memories = [
            *envelope.working_memory.memories,
            *envelope.working_memory.invalidated_memories,
        ]
        source_entries_by_id = {
            entry.memory_id: entry for entry in [*working_entries, *invalidated_entries]
        }
        snapshot_payload = {
            "snapshot_id": snapshot_id,
            "phase": phase,
            "conversation_id": run.conversation_id,
            "run_id": run.run_id,
            "created_at": created_at,
            "policy_snapshot": self._policy.snapshot(),
            "memory_refs": [
                GeneralAgentContextMemoryRef(
                    memory_id=memory.memory_id,
                    content_sha256=memory.content_sha256,
                    state_sha256=memory_state_sha256(
                        source_entries_by_id[memory.memory_id]
                    ),
                ).model_dump(mode="json")
                for memory in all_memories
            ],
            "envelope": envelope.model_dump(mode="json"),
            "assembly_trace": assembly_trace.model_dump(mode="json"),
        }
        snapshot = GeneralAgentContextSnapshot.model_validate(
            {
                **snapshot_payload,
                "content_sha256": context_snapshot_sha256(snapshot_payload),
            }
        )
        return ContextAssemblyResult(
            snapshot=snapshot,
            reused_snapshot=False,
            resume_differences=tuple(differences),
        )

    async def _snapshot_differences(
        self,
        snapshot: GeneralAgentContextSnapshot,
    ) -> list[str]:
        differences: list[str] = []
        for reference in snapshot.memory_refs:
            current = await self._memory_service.get(reference.memory_id)
            if current is None or current.deleted_at is not None:
                differences.append(f"运行记忆 {reference.memory_id} 已删除或过期。")
                continue
            if current.content_sha256 != reference.content_sha256:
                differences.append(f"运行记忆 {reference.memory_id} 的内容已经变化。")
                continue
            if memory_state_sha256(current) != reference.state_sha256:
                differences.append(
                    f"运行记忆 {reference.memory_id} 的使用状态已经变化。"
                )
        return differences

    def _build_envelope(
        self,
        run: GeneralAgentRun,
        *,
        phase: ContextPhase,
        replan_guidance: str,
        working_memories: list[GeneralAgentContextMemory],
        invalidated_memories: list[GeneralAgentContextMemory],
        excluded_node_ids: set[str],
    ) -> tuple[GeneralAgentContextEnvelope, GeneralAgentAssemblyTrace]:
        working_memories = _active_context_memories(working_memories)
        invalidated_memories = [
            memory
            for memory in invalidated_memories
            if memory.validity != AgentMemoryValidity.ACTIVE.value
            and memory.repair_only
        ]
        history_memory = _history_memory(
            run,
            limit=self._policy.history_memory_limit,
            char_budget=self._policy.history_memory_char_budget,
        )
        omitted_messages = history_memory.omitted_message_count
        node_summaries, omitted_nodes = _node_summaries(
            run,
            char_budget=self._policy.node_summary_char_budget,
            excluded_node_ids=excluded_node_ids,
        )
        plan_summary, omitted_plan_nodes = _plan_summary(
            run,
            char_budget=self._policy.plan_summary_char_budget,
        )
        unresolved = _deduplicate(
            [
                *run.verification_issues,
                *[
                    memory.content
                    for memory in working_memories
                    if memory.kind == AgentMemoryKind.UNRESOLVED_ISSUE.value
                ],
            ]
        )
        raw_node_chars = sum(
            len(json.dumps(node.output, ensure_ascii=False))
            for node in _current_nodes(run)
            if node.node_id not in excluded_node_ids
        )
        compression_needed = (
            len(run.messages) > self._policy.message_compaction_threshold
            or raw_node_chars > self._policy.node_output_compaction_threshold
            or omitted_messages > 0
            or omitted_nodes > 0
            or omitted_plan_nodes > 0
        )
        digest: ContextDigest | None = None
        fallback_used = False
        if compression_needed:
            try:
                digest = self._compactor.compact(
                    run,
                    memories=working_memories,
                    omitted_message_count=omitted_messages,
                    omitted_node_count=omitted_nodes,
                    excluded_node_ids=excluded_node_ids,
                )
            except Exception:  # noqa: BLE001
                fallback_used = True
                digest = _safe_digest(
                    run,
                    memories=working_memories,
                    omitted_message_count=omitted_messages,
                    omitted_node_count=omitted_nodes,
                )

        envelope = GeneralAgentContextEnvelope(
            phase=phase,
            stable_memory=list(_STABLE_MEMORY),
            working_memory=GeneralAgentWorkingMemory(
                memories=working_memories,
                invalidated_memories=invalidated_memories,
                plan_summary=plan_summary,
                node_summaries=node_summaries,
                unresolved_issues=unresolved,
                replan_guidance=replan_guidance,
                digest=digest,
            ),
            long_term_memory=[],
            history_memory=history_memory,
            current_request=GeneralAgentCurrentRequest(
                content=run.user_goal,
                user_constraints=_deduplicate(run.author_constraints),
                scope=run.scope.model_dump(mode="json"),
            ),
            compressed=compression_needed,
            fallback_used=fallback_used,
        )
        pre_trim_envelope = _with_context_counts(
            envelope,
            chars_per_token=self._policy.estimated_chars_per_token,
        )
        envelope, total_omissions = self._trim_to_total_budget(
            pre_trim_envelope,
            run=run,
            omitted_messages=omitted_messages,
            omitted_nodes=omitted_nodes,
            excluded_node_ids=excluded_node_ids,
        )
        stats = _category_stats(
            envelope,
            omissions={
                "long_term_memory": total_omissions["long_term_memory"],
                "history_memory": omitted_messages + total_omissions["history_memory"],
                "working_memory": total_omissions["working_memory"],
                "stable_memory": total_omissions["stable_memory"],
            },
        )
        envelope = envelope.model_copy(update={"category_stats": stats})
        envelope = _with_context_counts(
            envelope,
            chars_per_token=self._policy.estimated_chars_per_token,
        )
        if envelope.total_char_count > self._policy.total_char_budget:
            raise _unsafe_context_error(
                run,
                policy=self._policy,
                message=(
                    "受保护上下文超过上下文总预算，无法安全容纳；"
                    "系统不会截断这两层（稳定记忆与当前请求），"
                    "也不会静默删除当前有效指令、未决问题或直接依赖。"
                    "请缩小当前选区或拆分请求。"
                ),
            )
        assembly_trace = _build_assembly_trace(
            run=run,
            pre_trim_envelope=pre_trim_envelope,
            envelope=envelope,
            omitted_messages=omitted_messages,
            omitted_nodes=omitted_nodes,
            omitted_plan_nodes=omitted_plan_nodes,
            excluded_node_ids=excluded_node_ids,
            chars_per_token=self._policy.estimated_chars_per_token,
        )
        return envelope, assembly_trace

    def _trim_to_total_budget(
        self,
        envelope: GeneralAgentContextEnvelope,
        *,
        run: GeneralAgentRun,
        omitted_messages: int,
        omitted_nodes: int,
        excluded_node_ids: set[str],
    ) -> tuple[GeneralAgentContextEnvelope, dict[str, int]]:
        omissions = {
            "long_term_memory": 0,
            "history_memory": 0,
            "working_memory": 0,
            "stable_memory": 0,
        }
        trim_budget = max(0, self._policy.total_char_budget - 4_000)
        current = _with_context_counts(
            envelope,
            chars_per_token=self._policy.estimated_chars_per_token,
        )

        # 1. 长期记忆用于优化回答方式，预算紧张时最先退出。
        while current.total_char_count > trim_budget and current.long_term_memory:
            current = current.model_copy(
                update={"long_term_memory": current.long_term_memory[:-1]}
            )
            omissions["long_term_memory"] += 1
            current = _with_context_counts(
                current,
                chars_per_token=self._policy.estimated_chars_per_token,
            )

        # 2. 历史记忆从最旧对话开始裁剪；完整原文仍保存在运行记录中。
        if (
            current.total_char_count > trim_budget
            and current.history_memory.messages
            and current.working_memory.digest is None
        ):
            try:
                digest = self._compactor.compact(
                    run,
                    memories=current.working_memory.memories,
                    omitted_message_count=omitted_messages,
                    omitted_node_count=omitted_nodes,
                    excluded_node_ids=excluded_node_ids,
                )
            except Exception:  # noqa: BLE001
                digest = _safe_digest(
                    run,
                    memories=current.working_memory.memories,
                )
                current = current.model_copy(update={"fallback_used": True})
            current = current.model_copy(
                update={
                    "working_memory": current.working_memory.model_copy(
                        update={"digest": digest}
                    ),
                    "compressed": True,
                }
            )
        while (
            current.total_char_count > trim_budget and current.history_memory.messages
        ):
            history = current.history_memory.model_copy(
                update={
                    "messages": current.history_memory.messages[1:],
                    "omitted_message_count": (
                        current.history_memory.omitted_message_count + 1
                    ),
                }
            )
            current = current.model_copy(update={"history_memory": history})
            omissions["history_memory"] += 1
            current = _with_context_counts(
                current,
                chars_per_token=self._policy.estimated_chars_per_token,
            )

        # 3. 失效记录只供修复参考，预算紧张时先于当前有效工作记忆退出。
        while (
            current.total_char_count > trim_budget
            and current.working_memory.invalidated_memories
        ):
            working = current.working_memory.model_copy(
                update={
                    "invalidated_memories": (
                        current.working_memory.invalidated_memories[:-1]
                    )
                }
            )
            current = current.model_copy(update={"working_memory": working})
            omissions["working_memory"] += 1
            current = _with_context_counts(
                current,
                chars_per_token=self._policy.estimated_chars_per_token,
            )

        # 4. 当前有效工作记忆只裁剪可重建的低优先级过程载体。
        # 用户指令与未决问题是当前任务的保护输入；若它们与稳定层、当前请求
        # 合计仍无法容纳，交由末尾的 fail-closed 门禁拒绝，不能静默丢失。
        for kind in (
            AgentMemoryKind.WORK_NOTE.value,
            AgentMemoryKind.RESOURCE_SUMMARY.value,
            AgentMemoryKind.TASK_SUMMARY.value,
        ):
            while current.total_char_count > trim_budget:
                memories = current.working_memory.memories
                index = next(
                    (idx for idx, memory in enumerate(memories) if memory.kind == kind),
                    None,
                )
                if index is None:
                    break
                working = current.working_memory.model_copy(
                    update={"memories": [*memories[:index], *memories[index + 1 :]]}
                )
                current = current.model_copy(update={"working_memory": working})
                omissions["working_memory"] += 1
                current = _with_context_counts(
                    current,
                    chars_per_token=self._policy.estimated_chars_per_token,
                )
        required_node_ids = _required_node_ids(run)
        while current.total_char_count > trim_budget:
            node_summaries = current.working_memory.node_summaries
            removable_index = next(
                (
                    index
                    for index in range(len(node_summaries) - 1, -1, -1)
                    if str(node_summaries[index].get("node_id"))
                    not in required_node_ids
                ),
                None,
            )
            if removable_index is None:
                break
            working = current.working_memory.model_copy(
                update={
                    "node_summaries": [
                        *node_summaries[:removable_index],
                        *node_summaries[removable_index + 1 :],
                    ]
                }
            )
            current = current.model_copy(update={"working_memory": working})
            omissions["working_memory"] += 1
            current = _with_context_counts(
                current,
                chars_per_token=self._policy.estimated_chars_per_token,
            )
        if (
            current.total_char_count > trim_budget
            and current.working_memory.plan_summary is not None
        ):
            working = current.working_memory.model_copy(update={"plan_summary": None})
            current = current.model_copy(update={"working_memory": working})
            omissions["working_memory"] += 1
            current = _with_context_counts(
                current,
                chars_per_token=self._policy.estimated_chars_per_token,
            )

        # 5. 稳定记忆和当前请求都不截断；仍超预算就显式拒绝。
        return current.model_copy(
            update={
                "compressed": current.compressed or any(omissions.values()),
            }
        ), omissions


class ContextAssemblyError(ValueError):
    """在完整保留当前请求的前提下无法满足上下文预算。"""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str = "unsafe_context",
        total_char_budget: int | None = None,
        protected_char_count: int | None = None,
        current_request_sha256: str | None = None,
        stable_memory_sha256: str | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.total_char_budget = total_char_budget
        self.protected_char_count = protected_char_count
        self.current_request_sha256 = current_request_sha256
        self.stable_memory_sha256 = stable_memory_sha256


def _ensure_protected_context_fits(
    run: GeneralAgentRun,
    *,
    phase: ContextPhase,
    policy: GeneralAgentContextPolicy,
) -> None:
    protected_char_count = _protected_context_char_count(run, phase=phase)
    if (
        len(run.user_goal) <= _CURRENT_REQUEST_CONTENT_LIMIT
        and protected_char_count <= policy.total_char_budget
    ):
        return
    if len(run.user_goal) > _CURRENT_REQUEST_CONTENT_LIMIT:
        detail = "当前请求超过模型上下文单层可接受上限"
    else:
        detail = "稳定记忆与当前请求合计超过上下文总预算"
    raise _unsafe_context_error(
        run,
        policy=policy,
        protected_char_count=protected_char_count,
        message=(
            f"{detail}，无法安全容纳；系统不会截断这两层，"
            "不会把截断结果伪装成已完成。请缩小当前选区或拆分请求。"
        ),
    )


def _unsafe_context_error(
    run: GeneralAgentRun,
    *,
    policy: GeneralAgentContextPolicy,
    message: str,
    protected_char_count: int | None = None,
) -> ContextAssemblyError:
    return ContextAssemblyError(
        message,
        reason_code="unsafe_context",
        total_char_budget=policy.total_char_budget,
        protected_char_count=(
            protected_char_count
            if protected_char_count is not None
            else _protected_context_char_count(run, phase="verify")
        ),
        current_request_sha256=sha256(run.user_goal.encode("utf-8")).hexdigest(),
        stable_memory_sha256=context_snapshot_sha256(
            {"stable_memory": list(_STABLE_MEMORY)}
        ),
    )


def _protected_context_char_count(
    run: GeneralAgentRun,
    *,
    phase: ContextPhase,
) -> int:
    return _compact_json_char_count(
        {
            "phase": phase,
            "stable_memory": list(_STABLE_MEMORY),
            "current_request": {
                "content": run.user_goal,
                "user_constraints": _deduplicate(run.author_constraints),
                "scope": run.scope.model_dump(mode="json"),
            },
        }
    )


def _context_memory(
    entry: AgentMemoryEntry,
    *,
    projection_role: AgentMemoryDependencyRelation,
    repair_only: bool = False,
) -> GeneralAgentContextMemory:
    if not repair_only and entry.validity is not AgentMemoryValidity.ACTIVE:
        raise ContextAssemblyError("失效运行记忆不得进入当前事实投影。")
    if repair_only and entry.validity is AgentMemoryValidity.ACTIVE:
        raise ContextAssemblyError("有效运行记忆不得伪装成修复隔离投影。")
    content = entry.content
    if entry.kind is AgentMemoryKind.FACT_REFERENCE:
        content = f"事实引用标签：{content}。使用前必须通过正文或统一召回重新取证。"
    if repair_only:
        content = _INVALID_MEMORY_REPAIR_CONTENT
    return GeneralAgentContextMemory(
        memory_id=entry.memory_id,
        kind=entry.kind.value,
        content=content,
        source_refs=[] if repair_only else entry.source_refs,
        artifact_refs=[] if repair_only else entry.artifact_refs,
        content_sha256=entry.content_sha256,
        basis_sha256=entry.basis_sha256,
        validity=entry.validity.value,
        previous_validity=(
            entry.previous_validity.value
            if entry.previous_validity is not None
            else None
        ),
        invalidation_reason=(
            _INVALID_MEMORY_REPAIR_REASON if repair_only else entry.invalidation_reason
        ),
        invalidated_by_memory_id=entry.invalidated_by_memory_id,
        supersedes_memory_id=entry.supersedes_memory_id,
        result_type=None if repair_only else entry.result_type,
        producer_ref=None if repair_only else entry.producer_ref,
        projection_role=projection_role.value,
        repair_only=repair_only,
    )


def _working_entries(
    entries: list[AgentMemoryEntry],
    *,
    char_budget: int,
) -> list[AgentMemoryEntry]:
    limits = {
        AgentMemoryKind.USER_INSTRUCTION: 8,
        AgentMemoryKind.RESOURCE_SUMMARY: 5,
        AgentMemoryKind.WORK_NOTE: 3,
        AgentMemoryKind.UNRESOLVED_ISSUE: 5,
        AgentMemoryKind.FACT_REFERENCE: 3,
    }
    counts = {kind: 0 for kind in limits}
    selected: list[AgentMemoryEntry] = []
    selected_ids: set[str] = set()
    used = 0
    protected_kinds = {
        AgentMemoryKind.USER_INSTRUCTION,
        AgentMemoryKind.UNRESOLVED_ISSUE,
    }
    for entry in entries:
        if entry.kind not in protected_kinds:
            continue
        chars = _entry_char_count(entry)
        if used + chars > char_budget:
            raise ContextAssemblyError(
                "当前有效作者指令和未决问题超过工作记忆预算；"
                "系统不会静默删除这些保护输入。"
            )
        selected.append(entry)
        selected_ids.add(entry.memory_id)
        counts[entry.kind] += 1
        used += chars

    for entry in entries:
        if entry.kind is AgentMemoryKind.TASK_SUMMARY:
            continue
        if entry.memory_id in selected_ids:
            continue
        if counts[entry.kind] >= limits[entry.kind]:
            continue
        chars = _entry_char_count(entry)
        if used + chars > char_budget:
            continue
        selected.append(entry)
        counts[entry.kind] += 1
        used += chars
    return selected


def _memory_query_text(run: GeneralAgentRun, replan_guidance: str) -> str:
    plan_text = ""
    if run.plan is not None:
        plan_text = " ".join(
            [run.plan.rationale, *[node.objective for node in run.plan.nodes]]
        )
    return " ".join([run.user_goal, replan_guidance, plan_text]).strip()


def _history_memory(
    run: GeneralAgentRun,
    *,
    limit: int,
    char_budget: int,
) -> GeneralAgentHistoryMemory:
    messages = [
        message for message in run.messages if message.role in {"user", "assistant"}
    ]
    if (
        messages
        and messages[-1].role == "user"
        and messages[-1].content == run.user_goal
    ):
        messages = messages[:-1]
    total_message_count = len(messages)
    needs_summary = (
        len(messages) > limit
        or sum(len(message.content) for message in messages) > char_budget
    )
    recent_budget = char_budget * 3 // 4 if needs_summary else char_budget
    selected: list[GeneralAgentMessage] = []
    used = 0
    for message in reversed(messages):
        if len(selected) >= limit:
            break
        if used + len(message.content) > recent_budget:
            break
        selected.append(message)
        used += len(message.content)
    selected.reverse()
    omitted = messages[: len(messages) - len(selected)]
    summary_budget = max(0, char_budget - used)
    return GeneralAgentHistoryMemory(
        summary=_history_summary(omitted, char_budget=summary_budget),
        messages=selected,
        total_message_count=total_message_count,
        omitted_message_count=len(omitted),
    )


def _history_summary(
    messages: list[GeneralAgentMessage],
    *,
    char_budget: int,
) -> str:
    if not messages or char_budget < 40:
        return ""
    lines = [f"更早对话共 {len(messages)} 条，以下为受预算摘要："]
    for message in messages:
        role = "作者" if message.role == "user" else "太初"
        content = " ".join(message.content.split())
        line = f"{role}：{content[:600]}"
        candidate = "\n".join([*lines, line])
        if len(candidate) > char_budget:
            break
        lines.append(line)
    summary = "\n".join(lines)
    return summary[:char_budget]


def _required_output_paths_by_node(
    run: GeneralAgentRun,
) -> dict[str, tuple[str, ...]]:
    paths: dict[str, list[str]] = {}
    if run.plan is None:
        return {}
    for node in run.plan.nodes:
        for binding in node.input_bindings:
            paths.setdefault(binding.source_node_id, []).append(binding.source_path)
    return {
        node_id: tuple(_deduplicate(node_paths))
        for node_id, node_paths in paths.items()
    }


def _required_node_ids(run: GeneralAgentRun) -> set[str]:
    return set(_required_output_paths_by_node(run))


def _node_summaries(
    run: GeneralAgentRun,
    *,
    char_budget: int,
    excluded_node_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    selected: list[tuple[int, dict[str, Any]]] = []
    used = 0
    excluded = excluded_node_ids or set()
    nodes = [node for node in _current_nodes(run) if node.node_id not in excluded]
    required_paths = _required_output_paths_by_node(run)
    required_node_ids = set(required_paths)
    ordered_nodes = sorted(
        enumerate(nodes),
        key=lambda item: (
            item[1].node_id not in required_node_ids,
            item[0],
        ),
    )
    for position, (original_index, node) in enumerate(ordered_nodes):
        remaining_nodes = len(ordered_nodes) - position
        remaining_required = sum(
            item.node_id in required_node_ids for _, item in ordered_nodes[position:]
        )
        divisor = (
            remaining_required if node.node_id in required_node_ids else remaining_nodes
        )
        node_budget = max(0, (char_budget - used) // max(1, divisor))
        summary = {
            "node_id": node.node_id,
            "capability_name": node.capability_name,
            "objective": node.objective,
            "status": node.status.value,
            "source_refs": node.source_refs,
            "artifact_refs": node.artifact_refs,
            "error": node.error_message,
            "required_output_paths": list(required_paths.get(node.node_id, ())),
        }
        base_chars = _compact_json_char_count(summary)
        output_summary = _output_summary(
            node,
            char_budget=max(0, node_budget - base_chars),
            required_paths=required_paths.get(node.node_id, ()),
        )
        if node.node_id in required_node_ids and node.output and not output_summary:
            raise ContextAssemblyError(
                f"直接依赖节点 {node.node_id} 的 required output paths "
                "无法安全投影到节点摘要预算。"
            )
        summary["output_summary"] = output_summary
        chars = _compact_json_char_count(summary)
        if used + chars > char_budget:
            if node.node_id in required_node_ids:
                raise ContextAssemblyError(
                    f"直接依赖节点 {node.node_id} 无法安全容纳到节点摘要预算。"
                )
            continue
        selected.append((original_index, summary))
        used += chars
    selected.sort(key=lambda item: item[0])
    summaries = [summary for _, summary in selected]
    return summaries, len(nodes) - len(summaries)


def _output_summary(
    node: GeneralAgentNodeRun,
    *,
    char_budget: int,
    required_paths: tuple[str, ...] = (),
) -> Any:
    if not node.output:
        return ""
    encoded = json.dumps(node.output, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) <= char_budget:
        return node.output

    for item_limit in (24, 12, 6, 3):
        projection = {
            "_projection_status": "compressed",
            "_projection_notice": (
                "节点原始输出超过当前上下文预算；以下是结构概览，"
                "不得据此断言未展示的条目不存在。"
            ),
            "_original_char_count": len(encoded),
            "_required_output_paths": list(required_paths),
            "_required_fields": _required_field_overview(
                node.output,
                required_paths=required_paths,
            ),
            "fields": _structured_output_overview(
                node.output,
                depth=0,
                item_limit=item_limit,
            ),
        }
        if _compact_json_char_count(projection) <= char_budget:
            return projection

    minimal = {
        "_projection_status": "omitted",
        "_projection_notice": "节点原始输出超过当前上下文预算，未传递残缺内容。",
        "_original_char_count": len(encoded),
        "_top_level_keys": list(node.output),
        "_required_output_paths": list(required_paths),
        "_required_fields": _required_field_overview(
            node.output,
            required_paths=required_paths,
        ),
    }
    if _compact_json_char_count(minimal) <= char_budget:
        return minimal
    return ""


def _required_field_overview(
    output: dict[str, Any],
    *,
    required_paths: tuple[str, ...],
) -> dict[str, Any]:
    overview: dict[str, Any] = {}
    for path in required_paths:
        found, value = _resolve_output_path(output, path)
        if not found:
            overview[path] = {"available": False}
            continue
        if isinstance(value, list):
            overview[path] = {
                "available": True,
                "value_kind": "list",
                "item_count": len(value),
            }
        elif isinstance(value, dict):
            overview[path] = {
                "available": True,
                "value_kind": "object",
                "field_count": len(value),
                "fields": list(value),
            }
        else:
            overview[path] = {
                "available": True,
                "value_kind": "scalar",
                "value": value,
            }
    return overview


def _resolve_output_path(
    output: dict[str, Any],
    path: str,
) -> tuple[bool, Any]:
    current: Any = output
    for segment in path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
            continue
        if isinstance(current, list) and segment.isdigit():
            index = int(segment)
            if 0 <= index < len(current):
                current = current[index]
                continue
        return False, None
    return True, current


def _compact_json_char_count(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _structured_output_overview(
    value: Any,
    *,
    depth: int,
    item_limit: int,
) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= 500 else f"{value[:499]}…"
    if isinstance(value, list):
        overview: dict[str, Any] = {"item_count": len(value)}
        if not value:
            overview["items"] = []
            return overview
        if depth >= 2:
            return overview
        items = value[:item_limit]
        overview["items"] = [
            _structured_output_overview(
                item,
                depth=depth + 1,
                item_limit=item_limit,
            )
            for item in items
        ]
        if len(items) < len(value):
            overview["omitted_item_count"] = len(value) - len(items)
        return overview
    if isinstance(value, dict):
        return {
            str(key): _structured_output_overview(
                item,
                depth=depth + 1,
                item_limit=item_limit,
            )
            for key, item in value.items()
        }
    return str(value)


def _plan_summary(
    run: GeneralAgentRun,
    *,
    char_budget: int,
) -> tuple[dict[str, Any] | None, int]:
    if run.plan is None:
        return None, 0
    plan = run.plan
    summary: dict[str, Any] = {
        "rationale": plan.rationale[:4_000],
        "requires_clarification": plan.requires_clarification,
        "clarification_question": plan.clarification_question[:2_000],
        "direct_response": plan.direct_response[:8_000],
        "nodes": [],
        "final_response_guidance": plan.final_response_guidance[:4_000],
    }
    selected_nodes: list[dict[str, Any]] = []
    for node in plan.nodes:
        candidate = {
            "node_id": node.node_id,
            "capability_name": node.capability_name,
            "objective": node.objective[:1_000],
            "dependencies": node.dependencies,
        }
        attempted = {**summary, "nodes": [*selected_nodes, candidate]}
        if len(json.dumps(attempted, ensure_ascii=False)) > char_budget:
            continue
        selected_nodes.append(candidate)
    summary["nodes"] = selected_nodes
    for field in (
        "direct_response",
        "final_response_guidance",
        "clarification_question",
        "rationale",
    ):
        encoded = json.dumps(summary, ensure_ascii=False)
        if len(encoded) <= char_budget:
            break
        overflow = len(encoded) - char_budget
        value = str(summary[field])
        summary[field] = value[: max(0, len(value) - overflow - 16)]
    return summary, len(plan.nodes) - len(selected_nodes)


def _category_stats(
    envelope: GeneralAgentContextEnvelope,
    *,
    omissions: dict[str, int],
) -> list[GeneralAgentContextCategoryStat]:
    values: list[tuple[str, int, int]] = [
        (
            "stable_memory",
            len(envelope.stable_memory),
            sum(len(item) for item in envelope.stable_memory),
        ),
        (
            "working_memory",
            len(envelope.working_memory.memories)
            + len(envelope.working_memory.invalidated_memories),
            len(
                json.dumps(
                    envelope.working_memory.model_dump(mode="json"), ensure_ascii=False
                )
            ),
        ),
        (
            "long_term_memory",
            len(envelope.long_term_memory),
            sum(len(item.content) for item in envelope.long_term_memory),
        ),
        (
            "history_memory",
            len(envelope.history_memory.messages),
            len(envelope.history_memory.summary)
            + sum(len(item.content) for item in envelope.history_memory.messages),
        ),
        (
            "current_request",
            1,
            len(
                json.dumps(
                    envelope.current_request.model_dump(mode="json"), ensure_ascii=False
                )
            ),
        ),
    ]
    return [
        GeneralAgentContextCategoryStat(
            category=category,
            selected_count=count,
            selected_char_count=chars,
            omitted_count=omissions.get(category, 0),
            compressed=omissions.get(category, 0) > 0,
            reason=(
                "按固定顺序因总预算收缩。" if omissions.get(category, 0) > 0 else ""
            ),
        )
        for category, count, chars in values
    ]


def _build_assembly_trace(
    *,
    run: GeneralAgentRun,
    pre_trim_envelope: GeneralAgentContextEnvelope,
    envelope: GeneralAgentContextEnvelope,
    omitted_messages: int,
    omitted_nodes: int,
    omitted_plan_nodes: int,
    excluded_node_ids: set[str],
    chars_per_token: int,
) -> GeneralAgentAssemblyTrace:
    historical_messages = _raw_history_messages(run)
    raw_working_payload = {
        "memories": [
            item.model_dump(mode="json")
            for item in pre_trim_envelope.working_memory.memories
        ],
        "invalidated_memories": [
            item.model_dump(mode="json")
            for item in pre_trim_envelope.working_memory.invalidated_memories
        ],
        "plan": run.plan.model_dump(mode="json") if run.plan is not None else None,
        "nodes": [item.model_dump(mode="json") for item in _current_nodes(run)],
        "unresolved_issues": [
            *run.verification_issues,
            *pre_trim_envelope.working_memory.unresolved_issues,
        ],
        "replan_guidance": pre_trim_envelope.working_memory.replan_guidance,
    }
    pre_layer_metrics = {
        "stable_memory": (
            len(pre_trim_envelope.stable_memory),
            sum(len(item) for item in pre_trim_envelope.stable_memory),
        ),
        "working_memory": (
            _raw_working_carrier_count(run, pre_trim_envelope),
            _compact_json_char_count(raw_working_payload),
        ),
        "long_term_memory": (
            len(pre_trim_envelope.long_term_memory),
            sum(len(item.content) for item in pre_trim_envelope.long_term_memory),
        ),
        "history_memory": (
            len(historical_messages),
            sum(len(item.content) for item in historical_messages),
        ),
        "current_request": (
            1,
            _compact_json_char_count(
                pre_trim_envelope.current_request.model_dump(mode="json")
            ),
        ),
    }
    post_layer_metrics = {
        "stable_memory": (
            len(envelope.stable_memory),
            sum(len(item) for item in envelope.stable_memory),
        ),
        "working_memory": (
            _projected_working_carrier_count(envelope),
            _compact_json_char_count(envelope.working_memory.model_dump(mode="json")),
        ),
        "long_term_memory": (
            len(envelope.long_term_memory),
            sum(len(item.content) for item in envelope.long_term_memory),
        ),
        "history_memory": (
            len(envelope.history_memory.messages),
            len(envelope.history_memory.summary)
            + sum(len(item.content) for item in envelope.history_memory.messages),
        ),
        "current_request": (
            1,
            _compact_json_char_count(envelope.current_request.model_dump(mode="json")),
        ),
    }
    item_refs, source_refs = _omitted_context_refs(
        run=run,
        pre_trim_envelope=pre_trim_envelope,
        envelope=envelope,
        excluded_node_ids=excluded_node_ids,
    )
    protected_refs = _protected_context_refs(run, envelope)
    layer_item_refs: dict[str, tuple[str, ...]] = {
        "stable_memory": (),
        "working_memory": tuple(
            item for item in item_refs if item.startswith(("memory:", "node:", "plan:"))
        ),
        "long_term_memory": tuple(
            item for item in item_refs if item.startswith("long_term_memory:")
        ),
        "history_memory": tuple(
            item for item in item_refs if item.startswith("message:")
        ),
        "current_request": (),
    }
    layer_source_refs: dict[str, tuple[str, ...]] = {
        "stable_memory": (),
        "working_memory": source_refs,
        "long_term_memory": (),
        "history_memory": (),
        "current_request": (),
    }
    layer_protected_refs: dict[str, tuple[str, ...]] = {
        "stable_memory": tuple(
            item for item in protected_refs if item.startswith("stable_memory:")
        ),
        "working_memory": tuple(
            item for item in protected_refs if item.startswith(("memory:", "node:"))
        ),
        "long_term_memory": (),
        "history_memory": (),
        "current_request": tuple(
            item for item in protected_refs if item == "current_request"
        ),
    }
    layers: list[GeneralAgentContextLayerTrace] = []
    for layer in (
        "stable_memory",
        "working_memory",
        "long_term_memory",
        "history_memory",
        "current_request",
    ):
        pre_count, pre_chars = pre_layer_metrics[layer]
        post_count, post_chars = post_layer_metrics[layer]
        known_omissions = {
            "stable_memory": 0,
            "working_memory": omitted_nodes + omitted_plan_nodes,
            "long_term_memory": 0,
            "history_memory": omitted_messages,
            "current_request": 0,
        }[layer]
        omitted_count = max(
            pre_count - post_count,
            known_omissions,
            len(layer_item_refs[layer]),
        )
        layers.append(
            GeneralAgentContextLayerTrace(
                layer=layer,
                pre_count=pre_count,
                pre_char_count=pre_chars,
                pre_token_estimate=_estimated_tokens(pre_chars, chars_per_token),
                post_count=post_count,
                post_char_count=post_chars,
                post_token_estimate=_estimated_tokens(post_chars, chars_per_token),
                omitted_count=omitted_count,
                omitted_item_refs=layer_item_refs[layer],
                omitted_source_refs=layer_source_refs[layer],
                protected_refs=layer_protected_refs[layer],
            )
        )
    digest = envelope.working_memory.digest
    return GeneralAgentAssemblyTrace.create(
        layers=tuple(layers),
        omitted_item_refs=item_refs,
        omitted_source_refs=source_refs,
        protected_refs=protected_refs,
        digest_used=digest is not None,
        fallback_used=envelope.fallback_used,
        digest_source_ids=(
            tuple(digest.original_source_ids) if digest is not None else ()
        ),
        current_request_sha256=sha256(run.user_goal.encode("utf-8")).hexdigest(),
        stable_memory_sha256=context_snapshot_sha256(
            {"stable_memory": envelope.stable_memory}
        ),
        projections=_node_projection_traces(run, envelope),
    )


def _raw_history_messages(run: GeneralAgentRun) -> list[GeneralAgentMessage]:
    messages = [item for item in run.messages if item.role in {"user", "assistant"}]
    if (
        messages
        and messages[-1].role == "user"
        and messages[-1].content == run.user_goal
    ):
        return messages[:-1]
    return messages


def _raw_working_carrier_count(
    run: GeneralAgentRun,
    envelope: GeneralAgentContextEnvelope,
) -> int:
    return (
        len(envelope.working_memory.memories)
        + len(envelope.working_memory.invalidated_memories)
        + len(_current_nodes(run))
        + (1 if run.plan is not None else 0)
        + len(
            _deduplicate(
                [
                    *run.verification_issues,
                    *envelope.working_memory.unresolved_issues,
                ]
            )
        )
        + (1 if envelope.working_memory.digest is not None else 0)
    )


def _projected_working_carrier_count(
    envelope: GeneralAgentContextEnvelope,
) -> int:
    working = envelope.working_memory
    return (
        len(working.memories)
        + len(working.invalidated_memories)
        + len(working.node_summaries)
        + (1 if working.plan_summary is not None else 0)
        + len(working.unresolved_issues)
        + (1 if working.digest is not None else 0)
    )


def _protected_context_refs(
    run: GeneralAgentRun,
    envelope: GeneralAgentContextEnvelope,
) -> tuple[str, ...]:
    refs = [
        *[
            "stable_memory:" + sha256(item.encode("utf-8")).hexdigest()
            for item in envelope.stable_memory
        ],
        "current_request",
        *[
            f"memory:{memory.memory_id}"
            for memory in envelope.working_memory.memories
            if memory.kind
            in {
                AgentMemoryKind.USER_INSTRUCTION.value,
                AgentMemoryKind.UNRESOLVED_ISSUE.value,
            }
        ],
    ]
    refs.extend(f"node:{node_id}" for node_id in _required_node_ids(run))
    return tuple(_deduplicate(refs))


def _omitted_context_refs(
    *,
    run: GeneralAgentRun,
    pre_trim_envelope: GeneralAgentContextEnvelope,
    envelope: GeneralAgentContextEnvelope,
    excluded_node_ids: set[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    item_refs: list[str] = []
    source_refs: list[str] = []
    post_memory_ids = {
        item.memory_id
        for item in [
            *envelope.working_memory.memories,
            *envelope.working_memory.invalidated_memories,
        ]
    }
    for memory in [
        *pre_trim_envelope.working_memory.memories,
        *pre_trim_envelope.working_memory.invalidated_memories,
    ]:
        if memory.memory_id in post_memory_ids:
            continue
        item_refs.append(f"memory:{memory.memory_id}")
        source_refs.extend(memory.source_refs)

    projected_node_ids = {
        str(item.get("node_id"))
        for item in envelope.working_memory.node_summaries
        if isinstance(item, dict) and item.get("node_id")
    }
    for node in _current_nodes(run):
        if node.node_id in projected_node_ids and node.node_id not in excluded_node_ids:
            continue
        item_refs.append(f"node:{node.node_id}")
        source_refs.extend(node.source_refs)

    if run.plan is not None and envelope.working_memory.plan_summary is not None:
        projected_plan_ids = {
            str(item.get("node_id"))
            for item in envelope.working_memory.plan_summary.get("nodes", [])
            if isinstance(item, dict) and item.get("node_id")
        }
        for plan_node in run.plan.nodes:
            if plan_node.node_id not in projected_plan_ids:
                item_refs.append(f"plan:{plan_node.node_id}")

    selected_message_keys = {
        (item.role, item.content, item.created_at)
        for item in envelope.history_memory.messages
    }
    for index, message in enumerate(_raw_history_messages(run)):
        if (
            message.role,
            message.content,
            message.created_at,
        ) not in selected_message_keys:
            item_refs.append(f"message:{index}:{message.created_at}")

    return tuple(_deduplicate(item_refs)), tuple(_deduplicate(source_refs))


def _node_projection_traces(
    run: GeneralAgentRun,
    envelope: GeneralAgentContextEnvelope,
) -> tuple[GeneralAgentContextProjectionTrace, ...]:
    summaries = {
        str(item.get("node_id")): item
        for item in envelope.working_memory.node_summaries
        if isinstance(item, dict) and item.get("node_id")
    }
    required_paths = _required_output_paths_by_node(run)
    traces: list[GeneralAgentContextProjectionTrace] = []
    for node in _current_nodes(run):
        summary = summaries.get(node.node_id)
        projection = (
            summary.get("output_summary") if isinstance(summary, dict) else None
        )
        original_count = _structured_item_count(node.output)
        projected_count = min(
            original_count,
            _projected_item_count(projection),
        )
        traces.append(
            GeneralAgentContextProjectionTrace(
                node_id=node.node_id,
                original_content_sha256=context_snapshot_sha256(node.output),
                projected_content_sha256=(
                    context_snapshot_sha256({"projection": projection})
                    if projection is not None
                    else None
                ),
                original_item_count=original_count,
                projected_item_count=projected_count,
                omitted_item_count=original_count - projected_count,
                required_output_paths=required_paths.get(node.node_id, ()),
                source_refs=tuple(node.source_refs),
                artifact_refs=tuple(node.artifact_refs),
            )
        )
    return tuple(traces)


def _structured_item_count(value: Any) -> int:
    if isinstance(value, list):
        nested = sum(_structured_item_count(item) for item in value)
        return max(len(value), nested)
    if isinstance(value, dict):
        nested = sum(_structured_item_count(item) for item in value.values())
        return max(len(value), nested)
    return 0


def _projected_item_count(value: Any) -> int:
    if not isinstance(value, (dict, list)):
        return 0
    if isinstance(value, list):
        return max(
            len(value),
            sum(_projected_item_count(item) for item in value),
        )
    if value.get("_projection_status") == "omitted":
        return 0
    item_count = value.get("item_count")
    omitted_count = value.get("omitted_item_count", 0)
    if isinstance(item_count, int) and isinstance(omitted_count, int):
        return max(0, item_count - omitted_count)
    nested = sum(_projected_item_count(item) for item in value.values())
    if value.get("_projection_status") == "compressed":
        return nested
    return max(len(value), nested)


def _safe_digest(
    run: GeneralAgentRun,
    *,
    memories: list[GeneralAgentContextMemory],
    omitted_message_count: int = 0,
    omitted_node_count: int = 0,
) -> ContextDigest:
    memories = _active_context_memories(memories)
    return ContextDigest(
        user_instructions=_deduplicate(
            [
                *run.author_constraints,
                *[
                    memory.content
                    for memory in memories
                    if memory.kind == AgentMemoryKind.USER_INSTRUCTION.value
                ],
            ]
        ),
        task_summaries=[
            memory.content
            for memory in memories
            if memory.kind == AgentMemoryKind.TASK_SUMMARY.value
        ],
        completed_nodes=[],
        fact_source_refs=_deduplicate(
            [ref for memory in memories for ref in memory.source_refs]
        ),
        unresolved_issues=_deduplicate(run.verification_issues),
        next_conditions=(
            [run.pending_human_request.prompt]
            if run.pending_human_request is not None
            else []
        ),
        omitted_counts={
            "messages": omitted_message_count,
            "nodes": omitted_node_count,
        },
        original_source_ids=_deduplicate(
            [
                *[memory.memory_id for memory in memories],
                *[
                    f"node:{node.plan_revision}:{node.node_id}"
                    for node in run.node_runs
                ],
            ]
        ),
    )


def _active_context_memories(
    memories: list[GeneralAgentContextMemory],
) -> list[GeneralAgentContextMemory]:
    return [
        memory
        for memory in memories
        if (
            memory.validity == AgentMemoryValidity.ACTIVE.value
            and not memory.repair_only
            and memory.projection_role
            != AgentMemoryDependencyRelation.REPAIR_SOURCE.value
        )
    ]


def _current_nodes(run: GeneralAgentRun) -> list[GeneralAgentNodeRun]:
    return [node for node in run.node_runs if node.plan_revision == run.plan_revision]


def _node_memory_producer_ref(
    run: GeneralAgentRun,
    node: GeneralAgentNodeRun,
) -> str:
    return f"node:{run.run_id}:{node.plan_revision}:{node.node_id}"


def _entry_char_count(entry: AgentMemoryEntry) -> int:
    return (
        len(entry.content)
        + sum(len(item) for item in entry.source_refs)
        + sum(len(item) for item in entry.artifact_refs)
        + 24
    )


def _estimated_tokens(char_count: int, chars_per_token: int) -> int:
    return (char_count + max(1, chars_per_token) - 1) // max(1, chars_per_token)


def _with_context_counts(
    envelope: GeneralAgentContextEnvelope,
    *,
    chars_per_token: int,
) -> GeneralAgentContextEnvelope:
    counted = envelope
    for _ in range(4):
        char_count = len(
            json.dumps(counted.model_dump(mode="json"), ensure_ascii=False)
        )
        updated = counted.model_copy(
            update={
                "total_char_count": char_count,
                "estimated_token_count": _estimated_tokens(
                    char_count,
                    chars_per_token,
                ),
            }
        )
        if updated == counted:
            break
        counted = updated
    return counted


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _deduplicate_entries(entries: list[AgentMemoryEntry]) -> list[AgentMemoryEntry]:
    return list({entry.memory_id: entry for entry in entries}.values())
