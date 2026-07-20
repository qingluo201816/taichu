"""自动运行记忆与五层上下文预算测试。"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, Never, TypeVar

import pytest

from taichu.application.agent_memory.models import (
    AgentMemoryEntry,
    AgentMemoryKind,
    AgentMemoryQuery,
    MemoryWriteCandidate,
)
from taichu.application.general_agent.context import (
    ContextAssembler,
    ContextAssemblyError,
    ContextCompactor,
    GeneralAgentContextPolicy,
)
from taichu.application.general_agent.models import (
    GeneralAgentMessage,
    GeneralAgentNodeKind,
    GeneralAgentNodeRun,
    GeneralAgentNodeStatus,
    GeneralAgentRun,
    GeneralAgentScope,
)
from taichu.application.general_agent.orchestrator import (
    OrchestratorPlanError,
    _complete_capability_index,
    _json_char_count,
    _selected_capability_contracts,
)
from taichu.application.general_agent.request_analysis import (
    explicit_chapter_orders,
    is_explicit_chapter_content_request,
)
from taichu.application.general_agent.service import _chapter_source_quality_issues
from taichu.application.services.agent_memory_service import AgentMemoryService
from taichu.infrastructure.agent_memory import (
    JsonAgentMemoryLexicalIndex,
    JsonAgentMemoryRepository,
)

_ResultT = TypeVar("_ResultT")


def _run(awaitable: Coroutine[object, object, _ResultT]) -> _ResultT:
    return asyncio.run(awaitable)


def test_memory_is_automatic_isolated_relevant_and_request_expiring(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service = _memory_service(tmp_path)
        instruction = await _write(
            service,
            conversation_id="conversation_a",
            kind=AgentMemoryKind.USER_INSTRUCTION,
            content="叙事视角使用第三人称限知。",
            request_index=1,
        )
        resource = await _write(
            service,
            conversation_id="conversation_a",
            kind=AgentMemoryKind.RESOURCE_SUMMARY,
            content="第六章摘要：秦阳发现新的冲突线索。",
            request_index=1,
            expires_after_request_index=3,
        )
        await _write(
            service,
            conversation_id="conversation_b",
            kind=AgentMemoryKind.USER_INSTRUCTION,
            content="另一会话使用第一人称。",
            request_index=1,
        )

        query = AgentMemoryQuery(
            conversation_id="conversation_a",
            current_request_index=2,
            query_text="第六章冲突采用什么叙事视角",
            top_k=10,
            char_budget=2_000,
        )
        first = await service.retrieve(query)
        second = await service.retrieve(query)
        assert first.selected_memory_ids == second.selected_memory_ids
        assert instruction.memory_id in first.selected_memory_ids
        assert resource.memory_id in first.selected_memory_ids
        assert all(item.conversation_id == "conversation_a" for item in first.entries)
        assert all("lifecycle" not in item.model_dump() for item in first.entries)

        expired = await service.retrieve(
            query.model_copy(update={"current_request_index": 4})
        )
        assert resource.memory_id not in expired.selected_memory_ids
        assert instruction.memory_id in expired.selected_memory_ids

    _run(scenario())


def test_five_layers_trim_in_fixed_order_and_keep_current_request_complete(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        service = _memory_service(tmp_path)
        for index in range(12):
            await _write(
                service,
                conversation_id="conversation_long",
                kind=AgentMemoryKind.RESOURCE_SUMMARY,
                content=f"资源 {index} 摘要：" + "章节线索" * 80,
                request_index=1,
                expires_after_request_index=8,
            )
        run = _long_run(round_count=30)
        policy = GeneralAgentContextPolicy(
            total_char_budget=18_000,
            related_memory_top_k=12,
            related_memory_char_budget=8_000,
            working_memory_char_budget=8_000,
            process_history_limit=10,
            process_history_char_budget=5_000,
            node_summary_char_budget=4_000,
            plan_summary_char_budget=3_000,
            message_compaction_threshold=8,
            node_output_compaction_threshold=1_000,
        )
        result = await ContextAssembler(
            memory_service=service,
            policy=policy,
        ).assemble(run, phase="verify")
        envelope = result.snapshot.envelope

        assert envelope.total_char_count <= policy.total_char_budget
        assert envelope.current_request.content == run.user_goal
        assert envelope.current_request.scope["direct_context"] == run.scope.direct_context
        assert envelope.current_request.user_constraints == run.author_constraints
        assert envelope.stable_background
        assert envelope.digest is not None
        assert [item.category for item in envelope.category_stats] == [
            "stable_background",
            "working_memory",
            "related_memories",
            "process_history",
            "current_request",
        ]
        assert envelope.category_stats[-1].omitted_count == 0

        checkpointed = run.model_copy(
            update={
                "context_snapshot_id": result.snapshot.snapshot_id,
                "context_snapshot": result.snapshot,
            }
        )
        repeated = await ContextAssembler(
            memory_service=service,
            policy=policy,
        ).assemble(checkpointed, phase="verify")
        assert repeated.reused_snapshot is True

    _run(scenario())


def test_current_request_is_rejected_instead_of_truncated(tmp_path: Path) -> None:
    run = _long_run(round_count=2).model_copy(
        update={
            "scope": GeneralAgentScope(
                scope_type="selection",
                selection_text="完整选区" * 2_000,
            )
        }
    )
    assembler = ContextAssembler(
        memory_service=_memory_service(tmp_path),
        policy=GeneralAgentContextPolicy(total_char_budget=2_000),
    )
    with pytest.raises(ContextAssemblyError, match="不会截断当前请求"):
        _run(assembler.assemble(run, phase="plan"))


def test_compaction_failure_uses_safe_nonempty_digest(tmp_path: Path) -> None:
    assembler = ContextAssembler(
        memory_service=_memory_service(tmp_path),
        policy=GeneralAgentContextPolicy(
            total_char_budget=20_000,
            message_compaction_threshold=1,
        ),
        compactor=_FailingCompactor(),
    )
    result = _run(assembler.assemble(_long_run(round_count=10), phase="plan"))
    assert result.snapshot.envelope.fallback_used is True
    assert result.snapshot.envelope.digest is not None
    assert result.snapshot.envelope.digest.current_request


def test_legacy_run_groups_by_task_id_and_derives_request_index() -> None:
    run = _long_run(round_count=5)
    payload = run.model_dump(mode="json")
    payload.pop("conversation_id")
    payload.pop("request_index")
    migrated = GeneralAgentRun.model_validate(payload)
    assert migrated.conversation_id == migrated.task_id
    assert migrated.request_index == 3


def test_capability_catalog_uses_complete_index_and_progressive_contracts() -> None:
    index = [
        {
            "name": f"capability_{item}",
            "type": "tool",
            "description": f"处理第 {item} 类章节任务",
        }
        for item in range(24)
    ]
    contracts = {
        item["name"]: {
            **item,
            "input_schema": {"description": f"{item['name']}输入"},
            "output_schema": {"description": f"{item['name']}输出"},
        }
        for item in index
    }
    catalog = _complete_capability_index(index=index, char_budget=20_000)
    assert catalog["能力总数"] == 24
    assert {item["name"] for item in catalog["能力索引"]} == set(contracts)
    assert "input_schema" not in str(catalog)

    selected = _selected_capability_contracts(
        selected_names={"capability_7", "capability_23"},
        index=index,
        tool_contracts=contracts,
        subagent_contracts={},
        char_budget=10_000,
    )
    assert {
        item["name"] for item in selected["已选Tool精确契约"]
    } == {"capability_7", "capability_23"}
    assert _json_char_count(selected) <= 10_000


def test_complete_capability_index_never_silently_omits_entries() -> None:
    index = [
        {
            "name": f"capability_{item}",
            "type": "tool",
            "description": "完整能力目录中的稳定职责说明",
        }
        for item in range(28)
    ]
    with pytest.raises(OrchestratorPlanError, match="完整轻量能力目录超过字符预算"):
        _complete_capability_index(index=index, char_budget=100)


def test_explicit_chapter_reference_supports_arabic_chinese_and_ranges() -> None:
    assert explicit_chapter_orders("正文第8章讲的什么") == [8]
    assert explicit_chapter_orders("总结第八章") == [8]
    assert explicit_chapter_orders("概括第8到10章") == [8, 9, 10]
    assert is_explicit_chapter_content_request("正文第8章讲的什么") is True
    assert is_explicit_chapter_content_request("设计第8章的新冲突") is False


def test_explicit_chapter_content_requires_manuscript_source() -> None:
    run = _long_run(round_count=2).model_copy(
        update={
            "user_goal": "正文第8章讲的什么",
            "plan_revision": 1,
            "node_runs": [
                GeneralAgentNodeRun(
                    node_id="canon_chapter",
                    plan_revision=1,
                    kind=GeneralAgentNodeKind.SUBAGENT,
                    capability_name="canon_evidence",
                    objective="概括第8章",
                    status=GeneralAgentNodeStatus.SUCCESS,
                    source_refs=[],
                )
            ],
        }
    )
    assert _chapter_source_quality_issues(run)

    sourced = run.model_copy(
        update={
            "node_runs": [
                run.node_runs[0].model_copy(
                    update={"source_refs": ["manuscript:chapter_008:0-1200"]}
                )
            ]
        }
    )
    assert _chapter_source_quality_issues(sourced) == []


def _memory_service(root: Path) -> AgentMemoryService:
    return AgentMemoryService(
        repository=JsonAgentMemoryRepository(root),
        lexical_index=JsonAgentMemoryLexicalIndex(root),
    )


class _FailingCompactor(ContextCompactor):
    def compact(self, *args: Any, **kwargs: Any) -> Never:
        del args, kwargs
        raise RuntimeError("模拟压缩器失败")


async def _write(
    service: AgentMemoryService,
    *,
    conversation_id: str,
    kind: AgentMemoryKind,
    content: str,
    request_index: int,
    expires_after_request_index: int | None = None,
) -> AgentMemoryEntry:
    return await service.write(
        MemoryWriteCandidate(
            kind=kind,
            content=content,
            source_refs=["run:source:auto"],
            run_ids=["run_source"],
            conversation_id=conversation_id,
            created_request_index=request_index,
            expires_after_request_index=expires_after_request_index,
            retention_priority=80,
        )
    )


def _long_run(*, round_count: int = 30) -> GeneralAgentRun:
    timestamp = "2026-07-19T01:01:01Z"
    messages = [
        GeneralAgentMessage(
            role="user" if index % 2 == 0 else "assistant",
            content=f"第 {index + 1} 次内容：" + "叙事上下文" * 30,
            created_at=f"2026-07-19T01:{index:02d}:01Z",
        )
        for index in range(round_count)
    ]
    nodes = [
        GeneralAgentNodeRun(
            node_id=f"node_{index}",
            plan_revision=1,
            kind=GeneralAgentNodeKind.TOOL,
            capability_name="read_manuscript",
            objective=f"读取并检查第 {index + 1} 个范围。",
            status=GeneralAgentNodeStatus.SUCCESS,
            output={"content": "节点完整输出" * 150},
            source_refs=[f"chapter:chapter_{index + 1}"],
        )
        for index in range(20)
    ]
    return GeneralAgentRun(
        run_id="general_run_20260719_010101_abcdef",
        task_id="conversation_long",
        conversation_id="conversation_long",
        request_index=max(1, (round_count + 1) // 2),
        user_goal="把当前章节统一成第三人称限知视角。",
        author_constraints=["不得改变秦阳的姓名"],
        scope=GeneralAgentScope(
            scope_type="chapter",
            current_chapter_id="chapter_001",
            chapter_ids=["chapter_001"],
            direct_context="正文直接上下文" * 500,
        ),
        messages=messages,
        plan_revision=1,
        node_runs=nodes,
        created_at=timestamp,
        updated_at=timestamp,
        started_at=timestamp,
    )
