"""工作记忆当前事实与修复事实的类型化投影策略。"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from taichu.application.agent_memory.models import (
    AgentMemoryDependencyRelation,
    AgentMemoryEntry,
    AgentMemoryModel,
    AgentMemoryValidity,
    memory_source_fingerprint,
    memory_state_sha256,
)


class MemoryProjectionCandidate(AgentMemoryModel):
    """调用方为一条记忆声明本次消费角色。"""

    entry: AgentMemoryEntry
    role: AgentMemoryDependencyRelation


class CurrentFactProjectionItem(AgentMemoryModel):
    memory_id: str = Field(min_length=1, max_length=128)
    producer_ref: str = Field(min_length=1, max_length=256)
    role: Literal[
        AgentMemoryDependencyRelation.BASIS,
        AgentMemoryDependencyRelation.REVIEW_TARGET,
    ]
    validity: Literal[AgentMemoryValidity.ACTIVE]
    content: str = Field(min_length=1, max_length=20_000)
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    repair_only: Literal[False] = False


class CurrentFactProjection(AgentMemoryModel):
    items: tuple[CurrentFactProjectionItem, ...]


class CurrentFactProjectionPolicy:
    """只投影本作用域内、角色明确且仍为 ACTIVE 的 producer 结果。"""

    def project(
        self,
        candidates: tuple[MemoryProjectionCandidate, ...],
        *,
        allowed_producer_refs: frozenset[str],
    ) -> CurrentFactProjection:
        items: list[CurrentFactProjectionItem] = []
        seen_memory_ids: set[str] = set()
        for candidate in candidates:
            entry = candidate.entry
            if (
                entry.memory_id in seen_memory_ids
                or entry.producer_ref is None
                or entry.producer_ref not in allowed_producer_refs
                or entry.validity is not AgentMemoryValidity.ACTIVE
                or candidate.role is AgentMemoryDependencyRelation.REPAIR_SOURCE
            ):
                continue
            seen_memory_ids.add(entry.memory_id)
            items.append(
                CurrentFactProjectionItem(
                    memory_id=entry.memory_id,
                    producer_ref=entry.producer_ref,
                    role=candidate.role,
                    validity=AgentMemoryValidity.ACTIVE,
                    content=entry.content,
                    source_fingerprint=memory_source_fingerprint(entry),
                    state_hash=memory_state_sha256(entry),
                )
            )
        return CurrentFactProjection(items=tuple(items))


class RepairProjectionItem(AgentMemoryModel):
    memory_id: str = Field(min_length=1, max_length=128)
    producer_ref: str | None = Field(default=None, max_length=256)
    role: Literal[AgentMemoryDependencyRelation.REPAIR_SOURCE]
    previous_validity: AgentMemoryValidity | None
    current_validity: Literal[
        AgentMemoryValidity.STALE,
        AgentMemoryValidity.REJECTED,
        AgentMemoryValidity.SUPERSEDED,
    ]
    content: str = Field(min_length=1, max_length=20_000)
    transition_reason: str = Field(min_length=1, max_length=2_000)
    transition_source_memory_id: str | None = Field(default=None, max_length=128)
    supersedes_memory_id: str | None = Field(default=None, max_length=128)
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    repair_only: Literal[True] = True


class RepairProjection(AgentMemoryModel):
    """失效内容只能经显式 REPAIR_SOURCE 角色进入该隔离投影。"""

    items: tuple[RepairProjectionItem, ...]

    @classmethod
    def from_candidates(
        cls,
        candidates: tuple[MemoryProjectionCandidate, ...],
        *,
        allowed_producer_refs: frozenset[str],
    ) -> RepairProjection:
        items: list[RepairProjectionItem] = []
        seen_memory_ids: set[str] = set()
        for candidate in candidates:
            entry = candidate.entry
            if (
                entry.memory_id in seen_memory_ids
                or (
                    entry.producer_ref is not None
                    and entry.producer_ref not in allowed_producer_refs
                )
                or candidate.role is not AgentMemoryDependencyRelation.REPAIR_SOURCE
                or entry.validity is AgentMemoryValidity.ACTIVE
            ):
                continue
            seen_memory_ids.add(entry.memory_id)
            items.append(
                RepairProjectionItem(
                    memory_id=entry.memory_id,
                    producer_ref=entry.producer_ref,
                    role=AgentMemoryDependencyRelation.REPAIR_SOURCE,
                    previous_validity=entry.previous_validity,
                    current_validity=entry.validity,
                    content=entry.content,
                    transition_reason=entry.invalidation_reason,
                    transition_source_memory_id=entry.invalidated_by_memory_id,
                    supersedes_memory_id=entry.supersedes_memory_id,
                    source_fingerprint=memory_source_fingerprint(entry),
                    state_hash=memory_state_sha256(entry),
                )
            )
        return cls(items=tuple(items))
