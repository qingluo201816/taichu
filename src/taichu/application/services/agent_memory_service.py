"""通用 Runtime 自动工作记忆的写入、过期与检索服务。"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from taichu.application.agent_memory.models import (
    AgentMemoryEntry,
    AgentMemoryKind,
    AgentMemoryQuery,
    AgentMemorySelection,
    AgentMemorySensitivity,
    MemoryWriteCandidate,
    memory_content_sha256,
    memory_now_iso,
)
from taichu.application.contracts.agent_memory import (
    AgentMemoryLexicalIndex,
    AgentMemoryRepository,
)
from taichu.application.general_agent.memory_policy import AgentMemoryPolicy

if TYPE_CHECKING:
    from taichu.application.general_agent.models import (
        GeneralAgentExecutionPlan,
        GeneralAgentNodeRun,
        GeneralAgentRun,
        GeneralAgentVerification,
    )

_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)\b(api[_ -]?key|authorization|bearer)\s*[:=]\s*\S+"),
)


class AgentMemoryService:
    """记忆由 Runtime 自动维护，不经过作者确认，也不是模型可调用的 Tool。"""

    def __init__(
        self,
        *,
        repository: AgentMemoryRepository,
        lexical_index: AgentMemoryLexicalIndex,
        policy: AgentMemoryPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._lexical_index = lexical_index
        self._policy = policy or AgentMemoryPolicy()

    async def write(self, candidate: MemoryWriteCandidate) -> AgentMemoryEntry:
        normalized = candidate.content.strip()
        self._validate_candidate(candidate, normalized)
        await self._validate_supersession(candidate)
        existing = await self._repository.query(
            conversation_id=candidate.conversation_id,
            kinds=(candidate.kind,),
            include_deleted=False,
        )
        content_hash = memory_content_sha256(normalized)
        duplicate = next(
            (entry for entry in existing if entry.content_sha256 == content_hash),
            None,
        )
        now = memory_now_iso()
        if duplicate is not None:
            updated = duplicate.model_copy(
                update={
                    "source_refs": _deduplicate(
                        [*duplicate.source_refs, *candidate.source_refs]
                    ),
                    "artifact_refs": _deduplicate(
                        [*duplicate.artifact_refs, *candidate.artifact_refs]
                    ),
                    "run_ids": _deduplicate([*duplicate.run_ids, *candidate.run_ids]),
                    "created_request_index": min(
                        duplicate.created_request_index,
                        candidate.created_request_index,
                    ),
                    "expires_after_request_index": _later_request_expiry(
                        duplicate.expires_after_request_index,
                        candidate.expires_after_request_index,
                    ),
                    "retention_priority": max(
                        duplicate.retention_priority,
                        candidate.retention_priority,
                    ),
                    "supersedes_memory_id": (
                        candidate.supersedes_memory_id
                        or duplicate.supersedes_memory_id
                    ),
                    "updated_at": now,
                }
            )
            return await self._repository.save(updated)

        memory_id = (
            f"memory_{now[0:10].replace('-', '')}_"
            f"{now[11:19].replace(':', '')}_{uuid4().hex[:8]}"
        )
        entry = AgentMemoryEntry(
            memory_id=memory_id,
            kind=candidate.kind,
            content=normalized,
            source_refs=_deduplicate(candidate.source_refs),
            artifact_refs=_deduplicate(candidate.artifact_refs),
            run_ids=_deduplicate(candidate.run_ids),
            conversation_id=candidate.conversation_id,
            created_request_index=candidate.created_request_index,
            expires_after_request_index=candidate.expires_after_request_index,
            retention_priority=candidate.retention_priority,
            created_at=now,
            updated_at=now,
            expires_at=candidate.expires_at,
            supersedes_memory_id=candidate.supersedes_memory_id,
            content_sha256=content_hash,
            sensitivity=candidate.sensitivity,
        )
        return await self._repository.save(entry)

    async def retrieve(self, query: AgentMemoryQuery) -> AgentMemorySelection:
        as_of = query.as_of or memory_now_iso()
        await self._repository.purge_expired(as_of=as_of)
        entries = await self.list_active(
            query.conversation_id,
            current_request_index=query.current_request_index,
            as_of=as_of,
            kinds=tuple(query.kinds),
            run_id=query.run_id,
        )
        scores = await self._lexical_index.scores(entries, query_text=query.query_text)
        return self._policy.select(
            entries,
            lexical_scores=scores,
            top_k=query.top_k,
            char_budget=query.char_budget,
            as_of=as_of,
        )

    async def list_active(
        self,
        conversation_id: str,
        *,
        current_request_index: int,
        as_of: str | None = None,
        kinds: tuple[AgentMemoryKind, ...] = (),
        run_id: str | None = None,
    ) -> list[AgentMemoryEntry]:
        current_time = as_of or memory_now_iso()
        entries = await self._repository.query(
            conversation_id=conversation_id,
            kinds=kinds,
            run_id=run_id,
            include_deleted=False,
        )
        return [
            entry
            for entry in entries
            if entry.is_active(
                as_of=current_time,
                request_index=current_request_index,
            )
        ]

    async def list_for_conversation(
        self,
        conversation_id: str,
        *,
        include_deleted: bool = False,
    ) -> list[AgentMemoryEntry]:
        await self._repository.purge_expired(as_of=memory_now_iso())
        return await self._repository.query(
            conversation_id=conversation_id,
            include_deleted=include_deleted,
        )

    async def get(self, memory_id: str) -> AgentMemoryEntry | None:
        return await self._repository.get(memory_id)

    async def delete(self, memory_id: str) -> AgentMemoryEntry:
        entry = await self._repository.delete(memory_id, deleted_at=memory_now_iso())
        if entry is None:
            raise AgentMemoryNotFoundError(memory_id)
        return entry

    async def delete_conversation_memories(self, conversation_id: str) -> int:
        entries = await self._repository.query(
            conversation_id=conversation_id,
            include_deleted=False,
        )
        for entry in entries:
            await self._repository.delete(entry.memory_id, deleted_at=memory_now_iso())
        return len(entries)

    async def record_user_instructions(self, run: GeneralAgentRun) -> list[str]:
        memory_ids: list[str] = []
        for constraint in run.author_constraints:
            entry = await self.write(
                MemoryWriteCandidate(
                    kind=AgentMemoryKind.USER_INSTRUCTION,
                    content=_compact_text(constraint, 2_000),
                    source_refs=[f"run:{run.run_id}:user_constraints"],
                    run_ids=[run.run_id],
                    conversation_id=run.conversation_id,
                    created_request_index=run.request_index,
                    retention_priority=100,
                )
            )
            memory_ids.append(entry.memory_id)
        return memory_ids

    async def record_human_correction(
        self,
        run: GeneralAgentRun,
        *,
        content: str,
    ) -> str:
        entry = await self.write(
            MemoryWriteCandidate(
                kind=AgentMemoryKind.USER_INSTRUCTION,
                content=_compact_text(content, 2_000),
                source_refs=[f"run:{run.run_id}:user_reply"],
                run_ids=[run.run_id],
                conversation_id=run.conversation_id,
                created_request_index=run.request_index,
                retention_priority=95,
            )
        )
        return entry.memory_id

    async def record_plan(
        self,
        run: GeneralAgentRun,
        plan: GeneralAgentExecutionPlan,
    ) -> list[str]:
        if not plan.requires_clarification or not plan.clarification_question.strip():
            return []
        entry = await self.write(
            MemoryWriteCandidate(
                kind=AgentMemoryKind.UNRESOLVED_ISSUE,
                content=_compact_text(plan.clarification_question, 1_500),
                source_refs=[f"run:{run.run_id}:clarification"],
                run_ids=[run.run_id],
                conversation_id=run.conversation_id,
                created_request_index=run.request_index,
                expires_after_request_index=run.request_index + 3,
                retention_priority=90,
            )
        )
        return [entry.memory_id]

    async def record_node_results(
        self,
        run: GeneralAgentRun,
        nodes: list[GeneralAgentNodeRun],
    ) -> list[str]:
        memory_ids: list[str] = []
        for node in nodes:
            output_summary = _summarize_output(node.output)
            if not output_summary and not node.source_refs and not node.artifact_refs:
                continue
            has_resource = bool(node.source_refs or node.artifact_refs)
            kind = (
                AgentMemoryKind.RESOURCE_SUMMARY
                if has_resource
                else AgentMemoryKind.WORK_NOTE
            )
            label = "资源摘要" if has_resource else "过程摘要"
            content = _compact_text(
                f"{label}：{node.objective}。{output_summary}",
                1_800,
            )
            entry = await self.write(
                MemoryWriteCandidate(
                    kind=kind,
                    content=content,
                    source_refs=node.source_refs,
                    artifact_refs=node.artifact_refs,
                    run_ids=[run.run_id],
                    conversation_id=run.conversation_id,
                    created_request_index=run.request_index,
                    expires_after_request_index=(
                        run.request_index + 5 if has_resource else run.request_index + 3
                    ),
                    retention_priority=60 if has_resource else 50,
                )
            )
            memory_ids.append(entry.memory_id)
        return memory_ids

    async def record_verification(
        self,
        run: GeneralAgentRun,
        verification: GeneralAgentVerification,
    ) -> list[str]:
        summary = await self.write(
            MemoryWriteCandidate(
                kind=AgentMemoryKind.TASK_SUMMARY,
                content=_compact_text(
                    f"请求：{run.user_goal}\n结果：{verification.final_answer}",
                    2_400,
                ),
                source_refs=[f"run:{run.run_id}:verification"],
                run_ids=[run.run_id],
                conversation_id=run.conversation_id,
                created_request_index=run.request_index,
                retention_priority=75,
            )
        )
        memory_ids = [summary.memory_id]
        for issue in verification.issues:
            if not issue.strip():
                continue
            entry = await self.write(
                MemoryWriteCandidate(
                    kind=AgentMemoryKind.UNRESOLVED_ISSUE,
                    content=_compact_text(issue, 1_200),
                    source_refs=[f"run:{run.run_id}:verification_issue"],
                    run_ids=[run.run_id],
                    conversation_id=run.conversation_id,
                    created_request_index=run.request_index,
                    expires_after_request_index=run.request_index + 5,
                    retention_priority=90,
                )
            )
            memory_ids.append(entry.memory_id)
        return memory_ids

    async def _validate_supersession(self, candidate: MemoryWriteCandidate) -> None:
        superseded_id = candidate.supersedes_memory_id
        if superseded_id is None:
            return
        superseded = await self._repository.get(superseded_id)
        if superseded is None or superseded.deleted_at is not None:
            raise AgentMemoryServiceError("被替代的运行记忆不存在或已经删除。")
        if superseded.conversation_id != candidate.conversation_id:
            raise AgentMemoryServiceError("运行记忆不能替代其他会话中的记忆。")
        if superseded.kind is not candidate.kind:
            raise AgentMemoryServiceError("运行记忆只能替代同一类型的旧记忆。")

    def _validate_candidate(
        self,
        candidate: MemoryWriteCandidate,
        normalized: str,
    ) -> None:
        if not normalized:
            raise AgentMemoryServiceError("运行记忆内容不能为空。")
        if candidate.sensitivity is AgentMemorySensitivity.RESTRICTED:
            raise AgentMemoryServiceError("受限敏感内容不得写入运行记忆。")
        if any(pattern.search(normalized) for pattern in _SECRET_PATTERNS):
            raise AgentMemoryServiceError("运行记忆疑似包含密钥或鉴权信息，已拒绝写入。")
        if candidate.kind is AgentMemoryKind.FACT_REFERENCE and not candidate.source_refs:
            raise AgentMemoryServiceError("事实引用记忆必须携带稳定来源。")


class AgentMemoryServiceError(ValueError):
    """自动运行记忆不符合安全写入或来源约束。"""


class AgentMemoryNotFoundError(AgentMemoryServiceError):
    def __init__(self, memory_id: str) -> None:
        super().__init__(f"运行记忆“{memory_id}”不存在。")


def _compact_text(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}…"


def _summarize_output(output: dict[str, Any]) -> str:
    if not output:
        return ""
    selected: dict[str, Any] = {}
    for key, value in output.items():
        if key.lower() in {"content", "text", "manuscript", "chapter_text", "raw"}:
            selected[key] = _compact_text(str(value), 500)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            selected[key] = value
        elif isinstance(value, list):
            selected[key] = value[:5]
        elif isinstance(value, dict):
            selected[key] = dict(list(value.items())[:5])
        if len(selected) >= 8:
            break
    encoded = json.dumps(selected, ensure_ascii=False, separators=(",", ":"))
    return f"结果摘要：{_compact_text(encoded, 900)}" if encoded else ""


def _later_request_expiry(left: int | None, right: int | None) -> int | None:
    if left is None or right is None:
        return None
    return max(left, right)


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
