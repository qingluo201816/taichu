"""需求 14.14、14.18：节点复用必须在复制前复核 producer proof。"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import TypeVar

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from taichu.application.agent_memory.models import (
    AgentMemoryValidity,
    ProducerMemoryValidityProof,
)
from taichu.application.general_agent.executor import (
    DynamicDagExecutionError,
    DynamicDagExecutor,
)
from taichu.application.general_agent.models import (
    GeneralAgentExecutionPlan,
    GeneralAgentNodeKind,
    GeneralAgentNodeRun,
    GeneralAgentNodeStatus,
    GeneralAgentPlanNode,
    GeneralAgentRun,
)
from taichu.application.services.agent_memory_service import AgentMemoryServiceError
from tests.fakes import InMemoryGeneralAgentEffectRepository

_ResultT = TypeVar("_ResultT")


def _run(awaitable: Coroutine[object, object, _ResultT]) -> _ResultT:
    return asyncio.run(awaitable)


class _DriftingProducerValidity:
    async def producer_validity_proof(
        self,
        conversation_id: str,
        producer_ref: str,
        *,
        current_request_index: int | None = None,
    ) -> ProducerMemoryValidityProof:
        del current_request_index
        return ProducerMemoryValidityProof(
            conversation_id=conversation_id,
            producer_ref=producer_ref,
            source_node_id="source",
            memory_id="memory_20260727_010203_abcdef12",
            validity=AgentMemoryValidity.ACTIVE,
            state_hash="a" * 64,
            source_fingerprint="b" * 64,
            dependency_fingerprint="c" * 64,
            observed_at="2026-07-27T01:02:03Z",
        )

    async def require_active_producer(
        self,
        conversation_id: str,
        producer_ref: str,
        *,
        expected_source_fingerprint: str,
        expected_dependency_fingerprint: str,
        current_request_index: int | None = None,
    ) -> ProducerMemoryValidityProof:
        del (
            conversation_id,
            producer_ref,
            expected_source_fingerprint,
            expected_dependency_fingerprint,
            current_request_index,
        )
        raise AgentMemoryServiceError("producer 运行记忆不是当前有效状态。")


def test_executor_stops_reuse_when_producer_proof_changes_before_copy() -> None:
    async def scenario() -> None:
        timestamp = "2026-07-27T01:02:03Z"
        source = GeneralAgentNodeRun(
            node_id="source",
            plan_revision=1,
            kind=GeneralAgentNodeKind.TOOL,
            capability_name="read_manuscript",
            objective="读取正文。",
            status=GeneralAgentNodeStatus.SUCCESS,
            output={"content": "旧结果"},
        )
        reused = GeneralAgentPlanNode(
            node_id="source_reused",
            kind=GeneralAgentNodeKind.TOOL,
            capability_name="read_manuscript",
            objective="复用正文读取结果。",
            reuse_from_node_id="source",
        )
        run = GeneralAgentRun(
            run_id="general_run_20260727_010203_abcdef",
            task_id="task_fixture",
            conversation_id="conversation_fixture",
            request_index=2,
            user_goal="继续处理。",
            plan=GeneralAgentExecutionPlan(
                rationale="复用上一修订的读取结果。",
                nodes=[reused],
            ),
            plan_revision=2,
            node_runs=[source],
            created_at=timestamp,
            updated_at=timestamp,
            started_at=timestamp,
        )
        executor = DynamicDagExecutor(
            tool_registry=object(),  # type: ignore[arg-type]
            subagent_registry=object(),  # type: ignore[arg-type]
            policy_service=object(),  # type: ignore[arg-type]
            capability_result_repository=object(),  # type: ignore[arg-type]
            capability_handler_identities={},
            effect_repository=InMemoryGeneralAgentEffectRepository(),
            memory_validity_provider=_DriftingProducerValidity(),
        )

        with pytest.raises(DynamicDagExecutionError, match="producer"):
            await executor.execute(
                run,
                checkpoint=lambda current, _reason: asyncio.sleep(
                    0,
                    result=current,
                ),
                checkpointer=InMemorySaver(),
            )

    _run(scenario())
