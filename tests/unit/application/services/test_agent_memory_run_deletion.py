"""运行级记忆删除只解除目标运行所有权，并保持依赖有效性。"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import TypeVar

from taichu.application.agent_memory.models import (
    AgentMemoryDependency,
    AgentMemoryDependencyRelation,
    AgentMemoryEntry,
    AgentMemoryKind,
    AgentMemoryValidity,
    MemoryWriteCandidate,
    memory_state_sha256,
)
from taichu.application.services.agent_memory_service import AgentMemoryService
from taichu.infrastructure.agent_memory import (
    JsonAgentMemoryLexicalIndex,
    JsonAgentMemoryRepository,
)

_ResultT = TypeVar("_ResultT")
_CONVERSATION_ID = "conversation_run_deletion"
_TARGET_RUN_ID = "run_to_delete"
_OTHER_RUN_ID = "run_to_keep"


def _run(awaitable: Coroutine[object, object, _ResultT]) -> _ResultT:
    return asyncio.run(awaitable)


def _service(root: Path) -> tuple[AgentMemoryService, JsonAgentMemoryRepository]:
    repository = JsonAgentMemoryRepository(root)
    return (
        AgentMemoryService(
            repository=repository,
            lexical_index=JsonAgentMemoryLexicalIndex(root),
        ),
        repository,
    )


async def _write(
    service: AgentMemoryService,
    content: str,
    *,
    run_ids: list[str],
    conversation_id: str = _CONVERSATION_ID,
    dependencies: list[AgentMemoryDependency] | None = None,
    supersedes_memory_id: str | None = None,
) -> AgentMemoryEntry:
    return await service.write(
        MemoryWriteCandidate(
            kind=AgentMemoryKind.WORK_NOTE,
            content=content,
            source_refs=[f"source:{content}"],
            run_ids=run_ids,
            conversation_id=conversation_id,
            created_request_index=1,
            dependencies=dependencies or [],
            supersedes_memory_id=supersedes_memory_id,
        )
    )


def test_delete_run_memories_unlinks_shared_soft_deletes_exclusive_and_is_idempotent(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service, repository = _service(tmp_path)
        shared = await _write(
            service,
            "两个运行共同使用的记忆",
            run_ids=[_TARGET_RUN_ID, _OTHER_RUN_ID],
        )
        exclusive = await _write(
            service,
            "只属于待删除运行的记忆",
            run_ids=[_TARGET_RUN_ID],
        )
        unrelated = await _write(
            service,
            "只属于保留运行的记忆",
            run_ids=[_OTHER_RUN_ID],
        )
        shared_state_hash = memory_state_sha256(shared)

        assert await service.delete_run_memories(_CONVERSATION_ID, _TARGET_RUN_ID) == 2

        saved_shared = await repository.get(shared.memory_id)
        saved_exclusive = await repository.get(exclusive.memory_id)
        saved_unrelated = await repository.get(unrelated.memory_id)
        assert saved_shared is not None
        assert saved_shared.run_ids == [_OTHER_RUN_ID]
        assert saved_shared.deleted_at is None
        assert saved_shared.basis_sha256 == shared.basis_sha256
        assert memory_state_sha256(saved_shared) == shared_state_hash
        assert saved_exclusive is not None
        assert saved_exclusive.deleted_at is not None
        assert saved_unrelated == unrelated

        assert await service.delete_run_memories(_CONVERSATION_ID, _TARGET_RUN_ID) == 0
        assert await repository.get(shared.memory_id) == saved_shared
        assert await repository.get(exclusive.memory_id) == saved_exclusive

    _run(scenario())


def test_delete_run_memories_marks_retained_propagating_dependents_stale(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service, repository = _service(tmp_path)
        basis = await _write(
            service,
            "待删除的事实依据",
            run_ids=[_TARGET_RUN_ID],
        )
        review_target = await _write(
            service,
            "待删除的审查目标",
            run_ids=[_TARGET_RUN_ID],
        )
        repair_source = await _write(
            service,
            "待删除但仅供修复参考的记录",
            run_ids=[_TARGET_RUN_ID],
        )
        basis_dependent = await _write(
            service,
            "依赖事实依据的保留结论",
            run_ids=[_OTHER_RUN_ID],
            dependencies=[
                AgentMemoryDependency(
                    memory_id=basis.memory_id,
                    relation=AgentMemoryDependencyRelation.BASIS,
                )
            ],
        )
        review_dependent = await _write(
            service,
            "依赖审查目标的保留结论",
            run_ids=[_OTHER_RUN_ID],
            dependencies=[
                AgentMemoryDependency(
                    memory_id=review_target.memory_id,
                    relation=AgentMemoryDependencyRelation.REVIEW_TARGET,
                )
            ],
        )
        repair_dependent = await _write(
            service,
            "只把旧记录作为修复参考的保留结论",
            run_ids=[_OTHER_RUN_ID],
            dependencies=[
                AgentMemoryDependency(
                    memory_id=repair_source.memory_id,
                    relation=AgentMemoryDependencyRelation.REPAIR_SOURCE,
                )
            ],
        )

        await service.delete_run_memories(_CONVERSATION_ID, _TARGET_RUN_ID)

        saved_basis_dependent = await repository.get(basis_dependent.memory_id)
        saved_review_dependent = await repository.get(review_dependent.memory_id)
        saved_repair_dependent = await repository.get(repair_dependent.memory_id)
        assert saved_basis_dependent is not None
        assert saved_basis_dependent.validity is AgentMemoryValidity.STALE
        assert saved_basis_dependent.invalidated_by_memory_id == basis.memory_id
        assert saved_review_dependent is not None
        assert saved_review_dependent.validity is AgentMemoryValidity.STALE
        assert (
            saved_review_dependent.invalidated_by_memory_id == review_target.memory_id
        )
        assert saved_repair_dependent is not None
        assert saved_repair_dependent.validity is AgentMemoryValidity.ACTIVE

    _run(scenario())


def test_delete_run_memories_marks_retained_superseding_memory_stale(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service, repository = _service(tmp_path)
        superseded = await _write(
            service,
            "待删除运行产生的旧结论",
            run_ids=[_TARGET_RUN_ID],
        )
        superseding = await _write(
            service,
            "其他运行产生的新结论",
            run_ids=[_OTHER_RUN_ID],
            supersedes_memory_id=superseded.memory_id,
        )

        await service.delete_run_memories(_CONVERSATION_ID, _TARGET_RUN_ID)

        saved_superseding = await repository.get(superseding.memory_id)
        assert saved_superseding is not None
        assert saved_superseding.validity is AgentMemoryValidity.STALE
        assert saved_superseding.invalidated_by_memory_id == superseded.memory_id

    _run(scenario())


def test_delete_run_memories_repairs_validity_after_prior_partial_deletion(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service, repository = _service(tmp_path)
        upstream = await _write(
            service,
            "已被上一次删除尝试软删除的上游",
            run_ids=[_TARGET_RUN_ID],
        )
        downstream = await _write(
            service,
            "仍在使用被删除上游的结论",
            run_ids=[_OTHER_RUN_ID],
            dependencies=[
                AgentMemoryDependency(
                    memory_id=upstream.memory_id,
                    relation=AgentMemoryDependencyRelation.BASIS,
                )
            ],
        )
        await repository.delete(upstream.memory_id, deleted_at="2026-07-30T08:00:00Z")

        assert await service.delete_run_memories(_CONVERSATION_ID, _TARGET_RUN_ID) == 0

        saved_downstream = await repository.get(downstream.memory_id)
        assert saved_downstream is not None
        assert saved_downstream.validity is AgentMemoryValidity.STALE
        assert saved_downstream.invalidated_by_memory_id == upstream.memory_id

    _run(scenario())


def test_delete_run_memories_is_scoped_to_conversation(tmp_path: Path) -> None:
    async def scenario() -> None:
        service, repository = _service(tmp_path)
        other_conversation = await _write(
            service,
            "另一个会话中的同名运行记忆",
            run_ids=[_TARGET_RUN_ID],
            conversation_id="conversation_other",
        )

        assert await service.delete_run_memories(_CONVERSATION_ID, _TARGET_RUN_ID) == 0
        assert await repository.get(other_conversation.memory_id) == other_conversation

    _run(scenario())
