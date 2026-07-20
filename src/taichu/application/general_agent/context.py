"""通用 Runtime 的五层上下文组装、固定裁剪顺序与可追溯快照。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any, Literal
from uuid import uuid4

from taichu.application.agent_memory.models import (
    AgentMemoryEntry,
    AgentMemoryKind,
    AgentMemoryQuery,
)
from taichu.application.general_agent.models import (
    ContextDigest,
    GeneralAgentContextCategoryStat,
    GeneralAgentContextEnvelope,
    GeneralAgentContextMemory,
    GeneralAgentContextMemoryRef,
    GeneralAgentContextSnapshot,
    GeneralAgentCurrentRequest,
    GeneralAgentMessage,
    GeneralAgentNodeRun,
    GeneralAgentNodeStatus,
    GeneralAgentRun,
    GeneralAgentWorkingMemory,
    context_snapshot_sha256,
)
from taichu.application.invocations.models import now_iso
from taichu.application.services.agent_memory_service import AgentMemoryService

ContextPhase = Literal["plan", "replan", "verify"]

_STABLE_BACKGROUND = (
    "你是太初通用写作助手的高层编排 Agent，负责理解当前请求、选择最小充分路径并收敛结果。",
    "只能调用能力目录中真实存在且契约完整的 Tool 或子 Agent；不得临时创造能力。",
    "Markdown 正文是章节原文事实源；MongoDB 中已确认知识卡是结构事实源；所有索引均为可重建派生层。",
    "运行记忆只延续工作状态，不是小说事实；涉及事实时必须重新读取正文或通过统一召回取证。",
    "写入正文或结构事实必须遵守授权、校验和作者确认门禁。",
)


@dataclass(frozen=True, slots=True)
class GeneralAgentContextPolicy:
    """可保存到快照中的五层上下文预算。"""

    total_char_budget: int = 180_000
    related_memory_top_k: int = 12
    related_memory_char_budget: int = 12_000
    working_memory_char_budget: int = 24_000
    process_history_limit: int = 10
    process_history_char_budget: int = 24_000
    node_summary_char_budget: int = 20_000
    plan_summary_char_budget: int = 20_000
    message_compaction_threshold: int = 20
    node_output_compaction_threshold: int = 30_000
    estimated_chars_per_token: int = 4

    def snapshot(self) -> dict[str, Any]:
        return {
            "policy": "five_layer_runtime_context",
            "trim_order": [
                "related_memories",
                "process_history",
                "working_memory",
                "stable_background",
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
    """把旧过程证据压成结构化摘要，同时保留来源标识。"""

    def compact(
        self,
        run: GeneralAgentRun,
        *,
        memories: list[GeneralAgentContextMemory],
        omitted_message_count: int,
        omitted_node_count: int,
    ) -> ContextDigest:
        return ContextDigest(
            current_request=run.user_goal,
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
                for node in _current_nodes(run)
                if node.status is GeneralAgentNodeStatus.SUCCESS
            ],
            fact_source_refs=_deduplicate(
                [
                    *[ref for memory in memories for ref in memory.source_refs],
                    *[ref for node in _current_nodes(run) for ref in node.source_refs],
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
        reusable = run.context_snapshot
        if (
            reusable is not None
            and reusable.phase == phase
            and reusable.policy_snapshot == self._policy.snapshot()
            and reusable.envelope.replan_guidance == replan_guidance
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
        )
        working_entries = _working_entries(
            active_entries,
            char_budget=self._policy.working_memory_char_budget,
        )
        working_ids = {entry.memory_id for entry in working_entries}
        selection = await self._memory_service.retrieve(
            AgentMemoryQuery(
                conversation_id=run.conversation_id,
                current_request_index=run.request_index,
                query_text=_memory_query_text(run, replan_guidance),
                top_k=self._policy.related_memory_top_k,
                char_budget=self._policy.related_memory_char_budget,
                as_of=as_of,
            )
        )
        related_entries = [
            entry for entry in selection.entries if entry.memory_id not in working_ids
        ]
        envelope = self._build_envelope(
            run,
            phase=phase,
            replan_guidance=replan_guidance,
            working_memories=[_context_memory(entry) for entry in working_entries],
            related_memories=[_context_memory(entry) for entry in related_entries],
        )
        created_at = now_iso()
        snapshot_id = (
            f"context_{created_at[0:10].replace('-', '')}_"
            f"{created_at[11:19].replace(':', '')}_{uuid4().hex[:8]}"
        )
        all_memories = [
            *envelope.working_memory.memories,
            *envelope.related_memories,
        ]
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
                ).model_dump(mode="json")
                for memory in all_memories
            ],
            "envelope": envelope.model_dump(mode="json"),
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
        return differences

    def _build_envelope(
        self,
        run: GeneralAgentRun,
        *,
        phase: ContextPhase,
        replan_guidance: str,
        working_memories: list[GeneralAgentContextMemory],
        related_memories: list[GeneralAgentContextMemory],
    ) -> GeneralAgentContextEnvelope:
        process_history, omitted_messages = _process_history(
            run,
            limit=self._policy.process_history_limit,
            char_budget=self._policy.process_history_char_budget,
        )
        node_summaries, omitted_nodes = _node_summaries(
            run,
            char_budget=self._policy.node_summary_char_budget,
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
                    memories=[*working_memories, *related_memories],
                    omitted_message_count=omitted_messages,
                    omitted_node_count=omitted_nodes,
                )
            except Exception:  # noqa: BLE001
                fallback_used = True
                digest = _safe_digest(
                    run,
                    memories=[*working_memories, *related_memories],
                    omitted_message_count=omitted_messages,
                    omitted_node_count=omitted_nodes,
                )

        envelope = GeneralAgentContextEnvelope(
            phase=phase,
            stable_background=list(_STABLE_BACKGROUND),
            working_memory=GeneralAgentWorkingMemory(
                memories=working_memories,
                plan_summary=plan_summary,
                node_summaries=node_summaries,
                unresolved_issues=unresolved,
            ),
            related_memories=related_memories,
            process_history=process_history,
            current_request=GeneralAgentCurrentRequest(
                content=run.user_goal,
                user_constraints=_deduplicate(run.author_constraints),
                scope=run.scope.model_dump(mode="json"),
            ),
            replan_guidance=replan_guidance,
            digest=digest,
            compressed=compression_needed,
            fallback_used=fallback_used,
        )
        envelope, total_omissions = self._trim_to_total_budget(
            envelope,
            run=run,
            omitted_messages=omitted_messages,
            omitted_nodes=omitted_nodes,
        )
        stats = _category_stats(
            envelope,
            omissions={
                "related_memories": total_omissions["related_memories"],
                "process_history": omitted_messages
                + total_omissions["process_history"],
                "working_memory": total_omissions["working_memory"],
                "stable_background": total_omissions["stable_background"],
            },
        )
        envelope = envelope.model_copy(update={"category_stats": stats})
        envelope = _with_context_counts(
            envelope,
            chars_per_token=self._policy.estimated_chars_per_token,
        )
        if envelope.total_char_count > self._policy.total_char_budget:
            raise ContextAssemblyError(
                "当前请求本身超过上下文总预算；系统不会截断当前请求，请缩小选区或拆分请求。"
            )
        return envelope

    def _trim_to_total_budget(
        self,
        envelope: GeneralAgentContextEnvelope,
        *,
        run: GeneralAgentRun,
        omitted_messages: int,
        omitted_nodes: int,
    ) -> tuple[GeneralAgentContextEnvelope, dict[str, int]]:
        omissions = {
            "related_memories": 0,
            "process_history": 0,
            "working_memory": 0,
            "stable_background": 0,
        }
        trim_budget = max(0, self._policy.total_char_budget - 4_000)
        current = _with_context_counts(
            envelope,
            chars_per_token=self._policy.estimated_chars_per_token,
        )

        # 1. 相关记忆是按需补充层，预算紧张时最先退出。
        while (
            current.total_char_count > trim_budget
            and current.related_memories
        ):
            current = current.model_copy(
                update={"related_memories": current.related_memories[:-1]}
            )
            omissions["related_memories"] += 1
            current = _with_context_counts(
                current,
                chars_per_token=self._policy.estimated_chars_per_token,
            )

        # 2. 过程历史先压缩成摘要，再从最旧证据开始裁剪。
        if (
            current.total_char_count > trim_budget
            and current.process_history
            and current.digest is None
        ):
            try:
                digest = self._compactor.compact(
                    run,
                    memories=[
                        *current.working_memory.memories,
                        *current.related_memories,
                    ],
                    omitted_message_count=omitted_messages,
                    omitted_node_count=omitted_nodes,
                )
            except Exception:  # noqa: BLE001
                digest = _safe_digest(
                    run,
                    memories=[
                        *current.working_memory.memories,
                        *current.related_memories,
                    ],
                )
                current = current.model_copy(update={"fallback_used": True})
            current = current.model_copy(update={"digest": digest, "compressed": True})
        while (
            current.total_char_count > trim_budget
            and current.process_history
        ):
            current = current.model_copy(
                update={"process_history": current.process_history[1:]}
            )
            omissions["process_history"] += 1
            current = _with_context_counts(
                current,
                chars_per_token=self._policy.estimated_chars_per_token,
            )

        # 3. 工作记忆按过程笔记、资源摘要、任务摘要、用户指令的顺序收缩。
        for kind in (
            AgentMemoryKind.WORK_NOTE.value,
            AgentMemoryKind.RESOURCE_SUMMARY.value,
            AgentMemoryKind.TASK_SUMMARY.value,
            AgentMemoryKind.UNRESOLVED_ISSUE.value,
            AgentMemoryKind.USER_INSTRUCTION.value,
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
        while (
            current.total_char_count > trim_budget
            and current.working_memory.node_summaries
        ):
            working = current.working_memory.model_copy(
                update={"node_summaries": current.working_memory.node_summaries[:-1]}
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

        # 4. 稳定背景只在最后收缩，并至少保留核心角色声明。
        while (
            current.total_char_count > trim_budget
            and len(current.stable_background) > 1
        ):
            current = current.model_copy(
                update={"stable_background": current.stable_background[:-1]}
            )
            omissions["stable_background"] += 1
            current = _with_context_counts(
                current,
                chars_per_token=self._policy.estimated_chars_per_token,
            )

        # 5. current_request 永不截断；仍超预算就显式拒绝。
        return current.model_copy(
            update={
                "compressed": current.compressed or any(omissions.values()),
            }
        ), omissions


class ContextAssemblyError(ValueError):
    """在完整保留当前请求的前提下无法满足上下文预算。"""


def _context_memory(entry: AgentMemoryEntry) -> GeneralAgentContextMemory:
    content = entry.content
    if entry.kind is AgentMemoryKind.FACT_REFERENCE:
        content = f"事实引用标签：{content}。使用前必须通过正文或统一召回重新取证。"
    return GeneralAgentContextMemory(
        memory_id=entry.memory_id,
        kind=entry.kind.value,
        content=content,
        source_refs=entry.source_refs,
        artifact_refs=entry.artifact_refs,
        content_sha256=entry.content_sha256,
    )


def _working_entries(
    entries: list[AgentMemoryEntry],
    *,
    char_budget: int,
) -> list[AgentMemoryEntry]:
    limits = {
        AgentMemoryKind.USER_INSTRUCTION: 8,
        AgentMemoryKind.TASK_SUMMARY: 2,
        AgentMemoryKind.RESOURCE_SUMMARY: 5,
        AgentMemoryKind.WORK_NOTE: 3,
        AgentMemoryKind.UNRESOLVED_ISSUE: 5,
        AgentMemoryKind.FACT_REFERENCE: 3,
    }
    counts = {kind: 0 for kind in limits}
    selected: list[AgentMemoryEntry] = []
    used = 0
    for entry in entries:
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


def _process_history(
    run: GeneralAgentRun,
    *,
    limit: int,
    char_budget: int,
) -> tuple[list[GeneralAgentMessage], int]:
    messages = list(run.messages)
    if messages and messages[-1].role == "user" and messages[-1].content == run.user_goal:
        messages = messages[:-1]
    selected: list[GeneralAgentMessage] = []
    used = 0
    for message in reversed(messages):
        if len(selected) >= limit:
            break
        if used + len(message.content) > char_budget:
            continue
        selected.append(message)
        used += len(message.content)
    selected.reverse()
    return selected, len(messages) - len(selected)


def _node_summaries(
    run: GeneralAgentRun,
    *,
    char_budget: int,
) -> tuple[list[dict[str, Any]], int]:
    selected: list[dict[str, Any]] = []
    used = 0
    nodes = _current_nodes(run)
    for node in nodes:
        summary = {
            "node_id": node.node_id,
            "capability_name": node.capability_name,
            "objective": node.objective,
            "status": node.status.value,
            "output_summary": _output_summary(node),
            "source_refs": node.source_refs,
            "artifact_refs": node.artifact_refs,
            "error": node.error_message,
        }
        chars = len(json.dumps(summary, ensure_ascii=False))
        if used + chars > char_budget:
            continue
        selected.append(summary)
        used += chars
    return selected, len(nodes) - len(selected)


def _output_summary(node: GeneralAgentNodeRun) -> str:
    if not node.output:
        return ""
    encoded = json.dumps(node.output, ensure_ascii=False, separators=(",", ":"))
    return encoded if len(encoded) <= 2_000 else f"{encoded[:2_000]}…"


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
            "stable_background",
            len(envelope.stable_background),
            sum(len(item) for item in envelope.stable_background),
        ),
        (
            "working_memory",
            len(envelope.working_memory.memories),
            len(json.dumps(envelope.working_memory.model_dump(mode="json"), ensure_ascii=False)),
        ),
        (
            "related_memories",
            len(envelope.related_memories),
            sum(len(item.content) for item in envelope.related_memories),
        ),
        (
            "process_history",
            len(envelope.process_history),
            sum(len(item.content) for item in envelope.process_history),
        ),
        (
            "current_request",
            1,
            len(json.dumps(envelope.current_request.model_dump(mode="json"), ensure_ascii=False)),
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
                "按固定顺序因总预算收缩。"
                if omissions.get(category, 0) > 0
                else ""
            ),
        )
        for category, count, chars in values
    ]


def _safe_digest(
    run: GeneralAgentRun,
    *,
    memories: list[GeneralAgentContextMemory],
    omitted_message_count: int = 0,
    omitted_node_count: int = 0,
) -> ContextDigest:
    return ContextDigest(
        current_request=run.user_goal,
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
                *[f"node:{node.plan_revision}:{node.node_id}" for node in run.node_runs],
            ]
        ),
    )


def _current_nodes(run: GeneralAgentRun) -> list[GeneralAgentNodeRun]:
    return [node for node in run.node_runs if node.plan_revision == run.plan_revision]


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
        char_count = len(json.dumps(counted.model_dump(mode="json"), ensure_ascii=False))
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
