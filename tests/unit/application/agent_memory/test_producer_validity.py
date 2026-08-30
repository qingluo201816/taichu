"""需求 14.1—14.20：producer 工作记忆有效性证明。"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import TypeVar

import pytest

from taichu.application.agent_memory.models import (
    AgentMemoryDependency,
    AgentMemoryDependencyRelation,
    AgentMemoryKind,
    AgentMemoryValidity,
    MemoryWriteCandidate,
)
from taichu.application.general_agent.memory_policy import AgentMemoryPolicy
from taichu.application.general_agent.models import (
    GeneralAgentNodeKind,
    GeneralAgentNodeRun,
    GeneralAgentNodeStatus,
    GeneralAgentRun,
)
from taichu.application.services.agent_memory_service import (
    AgentMemoryService,
    AgentMemoryServiceError,
)
from tests.fakes.agent_memory import in_memory_agent_memory_repository

_ResultT = TypeVar("_ResultT")


def _run(awaitable: Coroutine[object, object, _ResultT]) -> _ResultT:
    return asyncio.run(awaitable)


def _service(root: Path) -> AgentMemoryService:
    return AgentMemoryService(
        repository=in_memory_agent_memory_repository(root),
        policy=AgentMemoryPolicy(),
    )


def _candidate(
    content: str,
    producer_ref: str,
    *,
    dependencies: list[AgentMemoryDependency] | None = None,
    supersedes_memory_id: str | None = None,
) -> MemoryWriteCandidate:
    return MemoryWriteCandidate(
        kind=AgentMemoryKind.WORK_NOTE,
        content=content,
        source_refs=["manuscript:chapter_001"],
        artifact_refs=["artifact:chapter_001"],
        run_ids=["general_run_fixture"],
        conversation_id="conversation_fixture",
        created_request_index=1,
        producer_ref=producer_ref,
        dependencies=dependencies or [],
        supersedes_memory_id=supersedes_memory_id,
    )


def test_producer_proof_preserves_four_states_source_node_and_supersession(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service = _service(tmp_path)
        active = await service.write(
            _candidate("当前有效产物", "node:run_fixture:1:active")
        )
        stale = await service.write(
            _candidate("来源过时产物", "node:run_fixture:1:stale")
        )
        rejected = await service.write(
            _candidate("审查否决产物", "node:run_fixture:1:rejected")
        )
        old = await service.write(_candidate("被替代产物", "node:run_fixture:1:old"))
        replacement = await service.write(
            _candidate(
                "当前替代产物",
                "node:run_fixture:2:replacement",
                dependencies=[
                    AgentMemoryDependency(
                        memory_id=old.memory_id,
                        relation=AgentMemoryDependencyRelation.REPAIR_SOURCE,
                    )
                ],
                supersedes_memory_id=old.memory_id,
            )
        )
        await service.invalidate(
            stale.memory_id,
            validity=AgentMemoryValidity.STALE,
            reason="来源指纹已变化。",
        )
        await service.invalidate(
            rejected.memory_id,
            validity=AgentMemoryValidity.REJECTED,
            reason="审查明确否决。",
        )

        proofs = {
            proof.producer_ref: proof
            for proof in await asyncio.gather(
                *(
                    service.producer_validity_proof(
                        "conversation_fixture",
                        producer_ref,
                    )
                    for producer_ref in (
                        "node:run_fixture:1:active",
                        "node:run_fixture:1:stale",
                        "node:run_fixture:1:rejected",
                        "node:run_fixture:1:old",
                        "node:run_fixture:2:replacement",
                    )
                )
            )
        }

        assert (
            proofs["node:run_fixture:1:active"].validity is AgentMemoryValidity.ACTIVE
        )
        assert proofs["node:run_fixture:1:stale"].validity is AgentMemoryValidity.STALE
        assert (
            proofs["node:run_fixture:1:rejected"].validity
            is AgentMemoryValidity.REJECTED
        )
        assert (
            proofs["node:run_fixture:1:old"].validity is AgentMemoryValidity.SUPERSEDED
        )
        replacement_proof = proofs["node:run_fixture:2:replacement"]
        assert replacement_proof.memory_id == replacement.memory_id
        assert replacement_proof.source_node_id == "replacement"
        assert replacement_proof.supersedes_memory_id == old.memory_id
        assert replacement_proof.source_fingerprint
        assert replacement_proof.dependency_fingerprint
        assert replacement_proof.state_hash

        accepted = await service.require_active_producer(
            "conversation_fixture",
            active.producer_ref or "",
            expected_source_fingerprint=proofs[
                "node:run_fixture:1:active"
            ].source_fingerprint,
            expected_dependency_fingerprint=proofs[
                "node:run_fixture:1:active"
            ].dependency_fingerprint,
        )
        assert accepted.memory_id == active.memory_id

    _run(scenario())


def test_require_active_producer_fails_closed_for_state_drift_and_conflicts(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service = _service(tmp_path)
        upstream = await service.write(
            _candidate("上游依据", "node:run_fixture:1:upstream")
        )
        dependent = await service.write(
            _candidate(
                "修复产物",
                "node:run_fixture:1:dependent",
                dependencies=[
                    AgentMemoryDependency(
                        memory_id=upstream.memory_id,
                        relation=AgentMemoryDependencyRelation.REPAIR_SOURCE,
                    )
                ],
            )
        )
        proof = await service.producer_validity_proof(
            "conversation_fixture",
            dependent.producer_ref or "",
        )
        await service.invalidate(
            upstream.memory_id,
            validity=AgentMemoryValidity.REJECTED,
            reason="上游已否决，但修复来源不传播失效。",
        )

        with pytest.raises(AgentMemoryServiceError, match="依赖指纹"):
            await service.require_active_producer(
                "conversation_fixture",
                dependent.producer_ref or "",
                expected_source_fingerprint=proof.source_fingerprint,
                expected_dependency_fingerprint=proof.dependency_fingerprint,
            )
        with pytest.raises(AgentMemoryServiceError, match="来源指纹"):
            await service.require_active_producer(
                "conversation_fixture",
                dependent.producer_ref or "",
                expected_source_fingerprint="0" * 64,
                expected_dependency_fingerprint=(
                    await service.producer_validity_proof(
                        "conversation_fixture",
                        dependent.producer_ref or "",
                    )
                ).dependency_fingerprint,
            )

        stale = await service.write(
            _candidate("待失效产物", "node:run_fixture:1:stale")
        )
        stale_proof = await service.producer_validity_proof(
            "conversation_fixture",
            stale.producer_ref or "",
        )
        await service.invalidate(
            stale.memory_id,
            validity=AgentMemoryValidity.STALE,
            reason="来源已变化。",
        )
        with pytest.raises(AgentMemoryServiceError, match="不是当前有效状态"):
            await service.require_active_producer(
                "conversation_fixture",
                stale.producer_ref or "",
                expected_source_fingerprint=stale_proof.source_fingerprint,
                expected_dependency_fingerprint=stale_proof.dependency_fingerprint,
            )

        await service.write(_candidate("冲突记录一", "node:run_fixture:1:duplicate"))
        await service.write(_candidate("冲突记录二", "node:run_fixture:1:duplicate"))
        with pytest.raises(AgentMemoryServiceError, match="唯一"):
            await service.producer_validity_proof(
                "conversation_fixture",
                "node:run_fixture:1:duplicate",
            )

    _run(scenario())


def test_record_node_results_creates_a_verifiable_producer_proof(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service = _service(tmp_path)
        timestamp = "2026-07-27T01:02:03Z"
        run = GeneralAgentRun(
            run_id="general_run_20260727_010203_abcdef",
            task_id="task_fixture",
            conversation_id="conversation_fixture",
            request_index=1,
            user_goal="读取第一章并形成摘要。",
            plan_revision=3,
            created_at=timestamp,
            updated_at=timestamp,
            started_at=timestamp,
        )
        node = GeneralAgentNodeRun(
            node_id="chapter_summary",
            plan_revision=3,
            kind=GeneralAgentNodeKind.TOOL,
            capability_name="read_manuscript",
            objective="读取第一章。",
            status=GeneralAgentNodeStatus.SUCCESS,
            output={"summary": "第一章摘要。"},
            source_refs=["manuscript:chapter_001"],
        )

        memory_ids = await service.record_node_results(run, [node])
        proof = await service.producer_validity_proof(
            "conversation_fixture",
            "node:general_run_20260727_010203_abcdef:3:chapter_summary",
            current_request_index=1,
        )

        assert memory_ids == [proof.memory_id]
        assert proof.validity is AgentMemoryValidity.ACTIVE
        assert proof.source_node_id == "chapter_summary"

    _run(scenario())
